import time
import logging
import requests
from urllib.parse import quote_plus
from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

ADZUNA_SIGNUP_URL = "https://developer.adzuna.com/signup"


class AdzunaScraper(BaseScraper):
    """
    Uses the Adzuna Jobs API to search Australian job listings.

    Adzuna aggregates data from Seek, Indeed, and many other boards,
    making it an excellent single-API replacement for blocked scrapers.

    Free tier: 250 API calls/month (plenty for personal use).

    Setup:
      1. Register at https://developer.adzuna.com/signup (free)
      2. Copy your app_id and app_key
      3. Enter them in the app sidebar under Adzuna API Settings
    """

    SOURCE_NAME = "Adzuna"
    API_BASE = "https://api.adzuna.com/v1/api/jobs/au/search"
    RESULTS_PER_PAGE = 20

    def __init__(self, app_id: str = "", app_key: str = ""):
        super().__init__()
        self.app_id = app_id.strip()
        self.app_key = app_key.strip()

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def search(self, roles: list) -> list:
        if not self.is_configured():
            logger.warning("Adzuna: API credentials not set — skipping.")
            return []

        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role)
                all_jobs.extend(jobs)
                logger.info(f"Adzuna: {len(jobs)} jobs for '{role}'")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Adzuna error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str) -> list:
        url = f"{self.API_BASE}/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": self.RESULTS_PER_PAGE,
            "what": role,
            "where": "Australia",
            "content-type": "application/json",
            "sort_by": "date",
        }

        try:
            response = requests.get(url, params=params, timeout=20)
        except Exception as e:
            logger.error(f"Adzuna request failed: {e}")
            return []

        if response.status_code == 401:
            logger.error("Adzuna: Invalid API credentials.")
            return []

        if response.status_code != 200:
            logger.warning(f"Adzuna returned HTTP {response.status_code}: {response.text[:200]}")
            return []

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Adzuna: Failed to parse JSON: {e}")
            return []

        jobs = []
        for item in data.get("results", []):
            try:
                title = item.get("title", "")
                if not title:
                    continue

                company = item.get("company", {}).get("display_name", "Unknown")
                location_obj = item.get("location", {})
                location_parts = location_obj.get("area", [])
                location = ", ".join(location_parts[-2:]) if location_parts else "Australia"

                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                salary = None
                if salary_min and salary_max:
                    salary = f"${salary_min:,.0f}–${salary_max:,.0f}"
                elif salary_min:
                    salary = f"From ${salary_min:,.0f}"

                url_link = item.get("redirect_url", "")
                description = item.get("description", "")[:300]
                date_posted = item.get("created", None)

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url_link,
                        source=self.SOURCE_NAME,
                        description=description,
                        salary=salary,
                        date_posted=date_posted,
                    )
                )
            except Exception as e:
                logger.debug(f"Adzuna item parse error: {e}")
                continue

        return jobs
