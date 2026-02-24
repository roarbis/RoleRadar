import time
import logging
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import BaseScraper, Job

logger = logging.getLogger(__name__)


class GradConnectionScraper(BaseScraper):
    """
    Scrapes GradConnection Australia — a well-known AU job board covering
    both graduate roles and experienced professional positions.
    Accessible via plain HTTP requests (no Cloudflare protection).
    """

    SOURCE_NAME = "GradConnection"
    BASE_URL = "https://au.gradconnection.com"

    def search(self, roles: list, location: str = "Australia") -> list:
        all_jobs = []
        for role in roles:
            try:
                jobs = self._search_role(role, location)
                all_jobs.extend(jobs)
                logger.info(f"GradConnection: {len(jobs)} jobs for '{role}' in '{location}'")
                time.sleep(2)
            except Exception as e:
                logger.error(f"GradConnection error for '{role}': {e}")
        return all_jobs

    def _search_role(self, role: str, location: str = "Australia") -> list:
        # GradConnection doesn't have a location URL param — we pass it as part of the query
        # and post-filter by location keyword in the result set
        url = f"{self.BASE_URL}/jobs/?q={quote_plus(role)}"
        self._location_filter = location  # stored for use in _parse_html
        try:
            response = self.session.get(url, timeout=30)
        except Exception as e:
            logger.error(f"GradConnection request failed: {e}")
            return []

        if response.status_code != 200:
            logger.warning(f"GradConnection returned HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        return self._parse_html(soup)

    def _parse_html(self, soup: BeautifulSoup) -> list:
        jobs = []
        location_filter = getattr(self, "_location_filter", "Australia").lower()

        # GradConnection uses div.campaign-listing-box for each job card
        job_cards = soup.find_all("div", class_="campaign-listing-box")
        logger.info(f"GradConnection: {len(job_cards)} raw cards")

        for card in job_cards:
            try:
                # Title — inside <a class="box-header-title">
                title_el = card.find("a", class_="box-header-title")
                if not title_el:
                    title_el = card.find("h3") or card.find("h2") or card.find("a", href=True)
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if not title:
                    continue

                # URL
                url = ""
                link = title_el if title_el.name == "a" else card.find("a", href=True)
                if link and link.get("href"):
                    href = link["href"]
                    url = href if href.startswith("http") else self.BASE_URL + href

                # Company — inside div.box-name or nearby employer link
                company_el = (
                    card.find("div", class_="box-name")
                    or card.find("a", class_=lambda c: c and "employer" in str(c).lower())
                    or card.find("span", class_=lambda c: c and "company" in str(c).lower())
                )
                # box-name often contains both title link and company name; get second text node
                company = "Unknown"
                if company_el:
                    # Try to get the employer name text (skip the job title link text)
                    company_texts = [
                        t.strip()
                        for t in company_el.stripped_strings
                        if t.strip() and t.strip() != title
                    ]
                    company = company_texts[0] if company_texts else "Unknown"

                # Location
                location_el = card.find(class_=lambda c: c and "location" in str(c).lower())
                if not location_el:
                    location_el = card.find("span", class_=lambda c: c and "city" in str(c).lower())
                location = location_el.get_text(strip=True) if location_el else "Australia"
                if not location:
                    location = "Australia"

                # Location post-filter: skip jobs not matching the requested location
                # (GradConnection has no URL location param so we filter here)
                if location_filter not in ("australia", "all australia", ""):
                    if location_filter not in location.lower():
                        continue

                # Work type / discipline tags (treat as description snippet)
                discipline_el = card.find(class_=lambda c: c and "discipline" in str(c).lower())
                description = discipline_el.get_text(strip=True) if discipline_el else ""

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        source=self.SOURCE_NAME,
                        description=description,
                    )
                )
            except Exception as e:
                logger.debug(f"GradConnection card parse error: {e}")
                continue

        return jobs
