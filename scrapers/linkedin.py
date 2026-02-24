import time
import logging
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import BaseScraper, Job

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    """
    Scrapes LinkedIn's public job search page (no login required).
    Uses a fresh requests.get() per call with full browser-like headers
    to avoid the HTTP 999 bot-detection response.
    Results are limited to ~25 per search (LinkedIn cap for unauthenticated users).
    """

    SOURCE_NAME = "LinkedIn"
    BASE_URL = "https://www.linkedin.com"

    # Full set of headers that mimic a real Chrome browser visit
    _BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    def search(self, roles: list, location: str = "Australia") -> list:
        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"LinkedIn: {len(jobs)} jobs for '{role}' in '{location}'")
                time.sleep(3)
            except Exception as e:
                logger.error(f"LinkedIn error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        url = (
            f"{self.BASE_URL}/jobs/search/"
            f"?keywords={quote_plus(role)}"
            f"&location={quote_plus(location)}"
            f"&f_TPR=r604800"   # last 7 days
            f"&sortBy=DD"       # newest first
        )

        try:
            # Use a fresh session per call — LinkedIn tracks session behaviour
            response = requests.get(url, headers=self._BROWSER_HEADERS, timeout=30)
        except Exception as e:
            logger.error(f"LinkedIn request failed: {e}")
            return []

        if response.status_code == 999:
            logger.warning("LinkedIn returned 999 — bot detection triggered. Skipping.")
            return []

        if response.status_code != 200:
            logger.warning(f"LinkedIn returned HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_html(soup)

    def _parse_html(self, soup: BeautifulSoup) -> list:
        jobs = []

        # LinkedIn public search wraps each job in a <div class="base-card ...">
        job_cards = soup.find_all("div", class_="base-card")

        if not job_cards:
            # Fallback for possible layout change
            job_cards = soup.find_all(
                "li", class_=lambda c: c and "job-search-card" in str(c)
            )

        logger.info(f"LinkedIn: {len(job_cards)} raw cards in HTML")

        for card in job_cards:
            try:
                # Title
                title_el = (
                    card.find("h3", class_="base-search-card__title")
                    or card.find("h3")
                    or card.find("h2")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Company
                company_el = (
                    card.find("h4", class_="base-search-card__subtitle")
                    or card.find("a", class_="hidden-nested-link")
                )
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                location_el = card.find("span", class_="job-search-card__location")
                location = location_el.get_text(strip=True) if location_el else "Australia"

                # URL — strip tracking parameters
                link_el = card.find("a", class_="base-card__full-link") or card.find(
                    "a", href=lambda h: h and "/jobs/view/" in str(h)
                )
                url = ""
                if link_el and link_el.get("href"):
                    url = link_el["href"].split("?")[0]

                # Date posted
                date_el = card.find("time")
                date_posted = date_el.get("datetime") if date_el else None

                if title:
                    jobs.append(
                        Job(
                            title=title,
                            company=company,
                            location=location,
                            url=url,
                            source=self.SOURCE_NAME,
                            date_posted=date_posted,
                        )
                    )
            except Exception as e:
                logger.debug(f"LinkedIn card parse error: {e}")
                continue

        return jobs
