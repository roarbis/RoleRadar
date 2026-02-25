"""
Indeed AU scraper — uses curl_cffi to bypass Cloudflare, then parses
the standard HTML job card structure.

Note: Indeed's RSS feed was discontinued (returns 404 as of Feb 2026).
curl_cffi HTML scraping is the only working approach.
On cloud hosting (Render/AWS), Indeed blocks datacenter IPs — this scraper
works best when running locally. On Render, use Adzuna API as a substitute.
"""

import time
import re
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

BASE_URL = "https://au.indeed.com"
SEARCH_URL = f"{BASE_URL}/jobs"

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


class IndeedScraper(BaseScraper):
    SOURCE_NAME = "Indeed"

    def search(self, roles: list, location: str = "Australia") -> list:
        if not CURL_CFFI_AVAILABLE:
            logger.error("Indeed: curl_cffi not installed. Run: pip install curl_cffi")
            return []

        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"Indeed: {len(jobs)} jobs for '{role}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Indeed error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # No location param — au.indeed.com is AU-specific already
        url = f"{SEARCH_URL}?q={quote_plus(role)}&sort=date"
        logger.info(f"Indeed HTML: {url}")

        try:
            response = cf_requests.get(
                url,
                headers=HEADERS,
                impersonate="chrome124",
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Indeed request failed: {e}")
            return []

        if response.status_code != 200:
            logger.warning(f"Indeed returned HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_html(soup)

    def _parse_html(self, soup: BeautifulSoup) -> list:
        jobs = []

        # Indeed job cards: div.job_seen_beacon > table > tbody > tr > td.resultContent
        beacons = soup.find_all("div", class_=lambda c: c and "job_seen_beacon" in str(c))
        logger.info(f"Indeed: {len(beacons)} job cards in HTML")

        for beacon in beacons:
            try:
                # Title
                title_el = (
                    beacon.find("h2", class_=lambda c: c and "jobTitle" in str(c))
                    or beacon.find("h2")
                )
                if not title_el:
                    continue
                title_link = title_el.find("a") or title_el
                title = title_link.get_text(strip=True)
                if not title:
                    continue

                # URL — data-jk is the job key
                jk = title_link.get("data-jk") or beacon.find(attrs={"data-jk": True})
                if jk:
                    job_key = jk if isinstance(jk, str) else jk.get("data-jk", "")
                    url = f"{BASE_URL}/viewjob?jk={job_key}" if job_key else ""
                else:
                    href = title_link.get("href", "")
                    url = href if href.startswith("http") else BASE_URL + href

                # Company
                company_el = (
                    beacon.find("span", attrs={"data-testid": "company-name"})
                    or beacon.find("span", class_=lambda c: c and "companyName" in str(c))
                    or beacon.find("a", attrs={"data-testid": "company-name"})
                )
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                location_el = (
                    beacon.find("div", attrs={"data-testid": "text-location"})
                    or beacon.find("div", class_=lambda c: c and "companyLocation" in str(c))
                )
                location = location_el.get_text(strip=True) if location_el else "Australia"

                # Salary
                salary_el = beacon.find(
                    attrs={"data-testid": "attribute_snippet_testid"}
                ) or beacon.find(class_=lambda c: c and "salary" in str(c).lower())
                salary = salary_el.get_text(strip=True) if salary_el else None

                # Snippet / description
                snippet_el = beacon.find(class_=lambda c: c and "job-snippet" in str(c))
                description = snippet_el.get_text(strip=True) if snippet_el else ""

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        source=self.SOURCE_NAME,
                        description=description[:400],
                        salary=salary,
                    )
                )
            except Exception as e:
                logger.debug(f"Indeed card parse error: {e}")
                continue

        return jobs
