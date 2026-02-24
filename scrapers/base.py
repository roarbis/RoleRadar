from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import requests
import logging

logger = logging.getLogger(__name__)


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    salary: Optional[str] = None
    date_posted: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary or "Not specified",
            "date_posted": self.date_posted or "Not specified",
            "source": self.source,
            "url": self.url,
            "description_preview": (self.description or "")[:300],
            "scraped_at": self.scraped_at,
        }


class BaseScraper:
    SOURCE_NAME = "Unknown"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-AU,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",  # omit 'br' — requests can't decompress Brotli natively
                "Connection": "keep-alive",
            }
        )

    def search(self, roles: list, location: str = "Australia") -> list:
        """Search for jobs matching the given roles in the given location."""
        raise NotImplementedError
