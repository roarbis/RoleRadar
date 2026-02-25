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

    Uses multiple CSS selector fallbacks to handle site redesigns gracefully.
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
        url = f"{self.BASE_URL}/jobs/?q={quote_plus(role)}"
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

        # ── Card detection: try multiple selector patterns ───────────────────
        # GradConnection has redesigned a few times; fall through each strategy.
        job_cards = (
            soup.find_all("div", class_="campaign-listing-box")                 # original
            or soup.find_all("div", class_=lambda c: c and "listing-box" in str(c))
            or soup.find_all("div", class_=lambda c: c and "job-card" in str(c).lower())
            or soup.find_all("article", class_=lambda c: c and (
                "job" in str(c).lower() or "listing" in str(c).lower()
            ))
            # Last-resort: any div that directly contains an h3/h2 with an anchor
            or [
                d for d in soup.find_all("div", recursive=True)
                if d.find(["h2", "h3"]) and d.find("a", href=True)
                and len(d.get("class", [])) > 0
                and d.parent and d.parent.name != "div"  # avoid deeply nested wrappers
            ][:30]
        )

        logger.info(f"GradConnection: {len(job_cards)} raw cards found")

        for card in job_cards:
            try:
                # ── Title ──────────────────────────────────────────────────
                title_el = (
                    card.find("a", class_="box-header-title")
                    or card.find("a", class_=lambda c: c and "title" in str(c).lower())
                    or card.find("h3")
                    or card.find("h2")
                    or card.find("a", href=True)
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title:
                    continue

                # ── URL ────────────────────────────────────────────────────
                url = ""
                link_el = title_el if title_el.name == "a" else card.find("a", href=True)
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    url = href if href.startswith("http") else self.BASE_URL + href

                # ── Company ────────────────────────────────────────────────
                company_el = (
                    card.find("div", class_="box-name")
                    or card.find("div", class_=lambda c: c and "employer" in str(c).lower())
                    or card.find("span", class_=lambda c: c and (
                        "company" in str(c).lower() or "employer" in str(c).lower()
                    ))
                    or card.find("a", class_=lambda c: c and "employer" in str(c).lower())
                )
                company = "Unknown"
                if company_el:
                    company_texts = [
                        t.strip()
                        for t in company_el.stripped_strings
                        if t.strip() and t.strip() != title
                    ]
                    company = company_texts[0] if company_texts else "Unknown"

                # ── Location ───────────────────────────────────────────────
                location_el = (
                    card.find(class_=lambda c: c and "location" in str(c).lower())
                    or card.find("span", class_=lambda c: c and "city" in str(c).lower())
                    or card.find("span", class_=lambda c: c and "region" in str(c).lower())
                )
                location = location_el.get_text(strip=True) if location_el else "Australia"
                if not location:
                    location = "Australia"

                # ── Description ────────────────────────────────────────────
                discipline_el = card.find(
                    class_=lambda c: c and (
                        "discipline" in str(c).lower()
                        or "tag" in str(c).lower()
                        or "snippet" in str(c).lower()
                    )
                )
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
