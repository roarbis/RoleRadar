"""
Indeed AU scraper — uses the public RSS feed to avoid cloud/datacenter IP blocking.
feedparser handles the XML parsing; no curl_cffi dependency needed for this scraper.

Why RSS instead of HTML scraping?
  Indeed aggressively blocks requests from cloud provider IP ranges (AWS, GCP, Render).
  RSS endpoints are far less restricted and work reliably from hosted environments.
"""

import logging
import re
import time
from html import unescape
from urllib.parse import quote_plus

import requests as _requests

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

from .base import BaseScraper, Job

# Browser-like headers for the RSS request.
# feedparser's default "python-feedparser/X.Y" user-agent is blocked by Indeed.
_RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

logger = logging.getLogger(__name__)

BASE_URL = "https://au.indeed.com"
RSS_URL = f"{BASE_URL}/rss"


class IndeedScraper(BaseScraper):
    SOURCE_NAME = "Indeed"

    def search(self, roles: list, location: str = "Australia") -> list:
        if not FEEDPARSER_AVAILABLE:
            logger.error("Indeed: feedparser not installed. Run: pip install feedparser")
            return []

        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"Indeed: {len(jobs)} jobs for '{role}' in '{location}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Indeed error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # For AU-wide searches, omit the `l` parameter entirely.
        # au.indeed.com is already AU-specific, and `l=Australia` doesn't match
        # Indeed's internal location database — it returns 0 results.
        if location.lower() in ("australia", "all australia", ""):
            url = f"{RSS_URL}?q={quote_plus(role)}&sort=date"
        else:
            url = f"{RSS_URL}?q={quote_plus(role)}&l={quote_plus(location)}&sort=date"
        logger.info(f"Indeed RSS: {url}")

        try:
            # Fetch with browser headers first — feedparser's default user-agent
            # ("python-feedparser/X.Y") is blocked by Indeed.
            resp = _requests.get(url, headers=_RSS_HEADERS, timeout=20)
            feed = feedparser.parse(resp.content)
        except Exception as e:
            logger.warning(f"Indeed: browser-header fetch failed ({e}), retrying with feedparser")
            try:
                feed = feedparser.parse(url)
            except Exception as e2:
                logger.error(f"Indeed RSS parse failed: {e2}")
                return []

        if not feed.entries:
            logger.warning(
                f"Indeed: 0 RSS entries for '{role}' — "
                "may be rate-limited, blocked, or no results for this location."
            )
            return []

        jobs = []
        for entry in feed.entries:
            try:
                job = self._parse_entry(entry)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Indeed entry parse error: {e}")

        return jobs

    def _parse_entry(self, entry) -> Job | None:
        raw_title = unescape(entry.get("title", "")).strip()
        if not raw_title:
            return None

        # Indeed RSS titles are usually "Job Title - Company Name"
        title = raw_title
        company = "Unknown"
        if " - " in raw_title:
            parts = raw_title.rsplit(" - ", 1)
            title = parts[0].strip()
            company = parts[1].strip()

        link = entry.get("link", "")

        # Summary is HTML containing Location, Company, description
        summary_html = entry.get("summary", "")

        # Extract location: <b>Location: </b>City, State
        loc_match = re.search(r"<b>Location:\s*</b>\s*([^<]+)", summary_html, re.I)
        job_location = unescape(loc_match.group(1).strip()) if loc_match else "Australia"

        # Extract company from HTML (overrides title-split if present)
        co_match = re.search(r"<b>Company:\s*</b>\s*([^<]+)", summary_html, re.I)
        if co_match:
            company = unescape(co_match.group(1).strip())

        # Strip HTML tags for plain-text description
        description = re.sub(r"<[^>]+>", " ", summary_html)
        description = re.sub(r"\s+", " ", description).strip()[:400]

        date_posted = entry.get("published") or entry.get("updated") or None

        # Try to extract salary from the summary text
        salary_match = re.search(
            r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*(?:pa|p\.a\.|per year|per hour|/hr|/h))?",
            description,
            re.I,
        )
        salary = salary_match.group(0).strip() if salary_match else None

        return Job(
            title=title,
            company=company,
            location=job_location,
            url=link,
            source=self.SOURCE_NAME,
            description=description,
            salary=salary,
            date_posted=date_posted,
        )
