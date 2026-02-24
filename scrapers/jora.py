"""
Jora AU scraper — tries RSS feed first (cloud-friendly), falls back to
curl_cffi HTML scraping if the RSS feed is unavailable or empty.

Why RSS-first?
  Jora (owned by Seek) blocks datacenter/cloud IP ranges at the HTML level.
  Their RSS endpoint is less restricted and works reliably from Render/cloud hosts.
"""

import logging
import re
import time
from html import unescape
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

BASE_URL = "https://au.jora.com"

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


class JoraScraper(BaseScraper):
    SOURCE_NAME = "Jora"

    def search(self, roles: list, location: str = "Australia") -> list:
        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"Jora: {len(jobs)} jobs for '{role}' in '{location}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Jora error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # ── 1. Try RSS feed first (works on cloud, avoids IP blocking) ─────
        if FEEDPARSER_AVAILABLE:
            rss_url = f"{BASE_URL}/j?q={quote_plus(role)}&l={quote_plus(location)}&type=rss"
            try:
                feed = feedparser.parse(rss_url)
                if feed.entries:
                    logger.info(f"Jora RSS: {len(feed.entries)} entries for '{role}'")
                    return [j for j in (self._parse_rss_entry(e) for e in feed.entries) if j]
                else:
                    logger.info("Jora RSS: 0 entries — falling back to HTML scraper")
            except Exception as e:
                logger.warning(f"Jora RSS failed ({e}), trying HTML scraper")

        # ── 2. Fall back to curl_cffi HTML scraping ──────────────────────
        if not CURL_CFFI_AVAILABLE:
            logger.error("Jora: feedparser returned no results and curl_cffi is not installed")
            return []

        url = f"{BASE_URL}/j?q={quote_plus(role)}&l={quote_plus(location)}"
        try:
            response = cf_requests.get(
                url,
                headers=HTML_HEADERS,
                impersonate="chrome131",
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Jora HTML request failed: {e}")
            return []

        if response.status_code != 200:
            logger.warning(f"Jora HTML returned HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_html(soup)

    # ── RSS entry parser ────────────────────────────────────────────────────

    def _parse_rss_entry(self, entry) -> Job | None:
        raw_title = unescape(entry.get("title", "")).strip()
        if not raw_title:
            return None

        title = raw_title
        company = "Unknown"
        # RSS titles are often "Job Title - Company Name"
        if " - " in raw_title:
            parts = raw_title.rsplit(" - ", 1)
            title = parts[0].strip()
            company = parts[1].strip()

        link = entry.get("link", "")

        summary_html = entry.get("summary", "")

        loc_match = re.search(r"<b>Location:\s*</b>\s*([^<]+)", summary_html, re.I)
        job_location = unescape(loc_match.group(1).strip()) if loc_match else "Australia"

        co_match = re.search(r"<b>Company:\s*</b>\s*([^<]+)", summary_html, re.I)
        if co_match:
            company = unescape(co_match.group(1).strip())

        description = re.sub(r"<[^>]+>", " ", summary_html)
        description = re.sub(r"\s+", " ", description).strip()[:400]

        date_posted = entry.get("published") or None

        return Job(
            title=title,
            company=company,
            location=job_location,
            url=link,
            source=self.SOURCE_NAME,
            description=description,
            date_posted=date_posted,
        )

    # ── HTML parser (fallback) ──────────────────────────────────────────────

    def _parse_html(self, soup: BeautifulSoup) -> list:
        jobs = []

        job_cards = soup.find_all("div", class_="job-card")
        logger.info(f"Jora HTML: {len(job_cards)} job cards")

        for card in job_cards:
            try:
                title_el = (
                    card.find("a", class_=lambda c: c and "job-title" in str(c))
                    or card.find("h2")
                    or card.find("h3")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                link = title_el if title_el.name == "a" else title_el.find("a")
                url = ""
                if link and link.get("href"):
                    href = link["href"]
                    url = href if href.startswith("http") else BASE_URL + href

                company_el = (
                    card.find(class_=lambda c: c and "company" in str(c).lower())
                    or card.find("span", class_=lambda c: c and "employer" in str(c).lower())
                )
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                location_el = card.find(class_=lambda c: c and "location" in str(c).lower())
                location = location_el.get_text(strip=True) if location_el else "Australia"
                if not location:
                    location = "Australia"

                abstract_el = card.find(class_=lambda c: c and "abstract" in str(c).lower())
                description = abstract_el.get_text(strip=True) if abstract_el else ""

                date_el = card.find("time") or card.find(
                    class_=lambda c: c and "date" in str(c).lower()
                )
                date_posted = (
                    date_el.get("datetime") or date_el.get_text(strip=True)
                    if date_el
                    else None
                )

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        source=self.SOURCE_NAME,
                        description=description[:400],
                        date_posted=date_posted,
                    )
                )
            except Exception as e:
                logger.debug(f"Jora HTML card parse error: {e}")
                continue

        return jobs
