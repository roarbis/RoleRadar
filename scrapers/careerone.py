import logging
from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

BLOCKED_MSG = (
    "CareerOne renders job listings via JavaScript (shimmer/skeleton loading). "
    "Plain HTTP requests only receive empty placeholder cards, not actual jobs. "
    "Tip: Enable Adzuna (free API) in the sidebar — it aggregates CareerOne data."
)


class CareerOneScraper(BaseScraper):
    SOURCE_NAME = "CareerOne"

    def search(self, roles: list) -> list:
        logger.warning(f"CareerOne scraper: {BLOCKED_MSG}")
        return []
