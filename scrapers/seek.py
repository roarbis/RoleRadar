"""
Seek scraper — uses curl_cffi to bypass Cloudflare, then calls
Seek's internal search API for clean structured JSON job data.
"""

import time
import logging
from urllib.parse import quote_plus

try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

API_URL = "https://www.seek.com.au/api/jobsearch/v5/search"
JOB_URL = "https://www.seek.com.au/job/{id}"

API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.seek.com.au/",
    "X-Seek-Site": "Chalice",
    "seek-request-brand": "seek",
    "seek-request-country": "AU",
}


class SeekScraper(BaseScraper):
    SOURCE_NAME = "Seek"

    def search(self, roles: list, location: str = "Australia") -> list:
        if not CURL_CFFI_AVAILABLE:
            logger.error("Seek: curl_cffi not installed. Run: pip install curl_cffi")
            return []

        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"Seek: {len(jobs)} jobs for '{role}' in '{location}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Seek error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # Seek accepts plain location strings — "All Australia", "Melbourne VIC", etc.
        seek_where = "All Australia" if location.lower() in ("australia", "all australia", "") else location
        params = {
            "siteKey": "AU-Main",
            "where": seek_where,
            "page": 1,
            "keywords": role,
            "seekSelectAllPages": "true",
            "sortMode": "ListedDate",
        }
        param_str = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        url = f"{API_URL}?{param_str}"

        try:
            response = cf_requests.get(
                url,
                headers=API_HEADERS,
                impersonate="chrome124",
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Seek API request failed: {e}")
            return []

        if response.status_code != 200:
            logger.warning(f"Seek API returned HTTP {response.status_code}")
            return []

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Seek: failed to parse JSON: {e}")
            return []

        # 'data' is the standard key; log top-level keys on miss so we can
        # adapt quickly if Seek changes their API response structure.
        job_list = data.get("data") or data.get("jobs") or data.get("results") or []
        if not job_list:
            logger.warning(
                f"Seek: no jobs in response — top-level keys: {list(data.keys())[:10]}"
            )
        return self._parse_jobs(job_list)

    def _parse_jobs(self, job_list: list) -> list:
        jobs = []
        for item in job_list:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Try multiple field names — Seek has used 'id', 'jobId', 'listingId'
                job_id = (
                    item.get("id")
                    or item.get("jobId")
                    or item.get("listingId")
                    or ""
                )
                url = JOB_URL.format(id=job_id) if job_id else ""

                # Company — prefer companyName, fall back to advertiser.description
                company = item.get("companyName") or ""
                if not company:
                    advertiser = item.get("advertiser", {})
                    company = advertiser.get("description", "Unknown") if isinstance(advertiser, dict) else "Unknown"

                # Location — locations is a list of dicts
                location = "Australia"
                locations = item.get("locations", [])
                if locations and isinstance(locations[0], dict):
                    parts = [
                        locations[0].get("suburb", ""),
                        locations[0].get("area", ""),
                        locations[0].get("state", ""),
                    ]
                    location = ", ".join(p for p in parts if p) or "Australia"

                salary = item.get("salaryLabel") or None
                date_posted = item.get("listingDate") or item.get("listingDateDisplay")

                # Description from teaser or bullet points
                description = item.get("teaser", "")
                if not description:
                    bullets = item.get("bulletPoints", [])
                    description = " | ".join(bullets) if bullets else ""

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        source=self.SOURCE_NAME,
                        description=description[:400],
                        salary=str(salary) if salary else None,
                        date_posted=str(date_posted) if date_posted else None,
                    )
                )
            except Exception as e:
                logger.debug(f"Seek item parse error: {e}")
                continue

        return jobs
