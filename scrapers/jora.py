"""
Jora AU scraper — uses curl_cffi to bypass Cloudflare, then parses HTML.

Note: Jora has no RSS feed (the ?type=rss param returns a Cloudflare 403).
curl_cffi HTML scraping is the only working approach.
On cloud hosting (Render/AWS), Jora blocks datacenter IPs — this scraper
works best when running locally. On Render, use Adzuna API as a substitute.
"""

import time
import logging
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

BASE_URL = "https://au.jora.com"

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


class JoraScraper(BaseScraper):
    SOURCE_NAME = "Jora"

    def search(self, roles: list, location: str = "Australia") -> list:
        if not CURL_CFFI_AVAILABLE:
            logger.error("Jora: curl_cffi not installed. Run: pip install curl_cffi")
            return []

        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"Jora: {len(jobs)} jobs for '{role}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Jora error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # No location param — au.jora.com is AU-specific
        url = f"{BASE_URL}/j?q={quote_plus(role)}"
        logger.info(f"Jora HTML: {url}")

        try:
            response = cf_requests.get(
                url,
                headers=HEADERS,
                impersonate="chrome124",
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Jora request failed: {e}")
            return []

        if response.status_code != 200:
            logger.warning(f"Jora returned HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_html(soup)

    def _parse_html(self, soup: BeautifulSoup) -> list:
        jobs = []

        # Jora job cards use class="job-card result ..."
        job_cards = soup.find_all("div", class_="job-card")
        logger.info(f"Jora: {len(job_cards)} job cards in HTML")

        for card in job_cards:
            try:
                # Title — <h2> or <h3> with a link inside, or <a class="job-title">
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

                # URL
                link = title_el if title_el.name == "a" else title_el.find("a")
                url = ""
                if link and link.get("href"):
                    href = link["href"]
                    url = href if href.startswith("http") else BASE_URL + href

                # Company
                company_el = (
                    card.find(class_=lambda c: c and "company" in str(c).lower())
                    or card.find("span", class_=lambda c: c and "employer" in str(c).lower())
                )
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                location_el = card.find(
                    class_=lambda c: c and "location" in str(c).lower()
                )
                location = location_el.get_text(strip=True) if location_el else "Australia"
                if not location:
                    location = "Australia"

                # Abstract / description
                abstract_el = card.find(class_=lambda c: c and "abstract" in str(c).lower())
                description = abstract_el.get_text(strip=True) if abstract_el else ""

                # Date
                date_el = card.find("time") or card.find(
                    class_=lambda c: c and "date" in str(c).lower()
                )
                date_posted = (
                    date_el.get("datetime") or date_el.get_text(strip=True)
                    if date_el else None
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
                logger.debug(f"Jora card parse error: {e}")
                continue

        return jobs
