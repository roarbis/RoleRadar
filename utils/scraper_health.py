"""
RoleRadar — scraper health-check utility.

Performs lightweight HTTP connectivity checks for each supported job source,
running them concurrently so the whole check completes in a few seconds.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

# Lightweight URL to ping for each source (homepage or API root)
SOURCE_URLS: dict[str, str] = {
    "Seek": "https://www.seek.com.au",
    "Indeed": "https://au.indeed.com",
    "Jora": "https://au.jora.com",
    "LinkedIn": "https://www.linkedin.com",
    "GradConnection": "https://au.gradconnection.com",
    "Adzuna": "https://www.adzuna.com.au",
}

_TIMEOUT = 10  # seconds per source
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def check_source(source_name: str) -> dict:
    """
    Ping a single source URL and return a health dict:
      {
        online:      bool,
        latency_ms:  int,
        status_code: int | None,
        note:        str,        # short human-readable description
      }
    """
    url = SOURCE_URLS.get(source_name)
    if not url:
        return {
            "online": False,
            "latency_ms": 0,
            "status_code": None,
            "note": "Unknown source",
        }

    start = time.time()
    try:
        r = requests.get(
            url,
            headers=_HEADERS,
            timeout=_TIMEOUT,
            allow_redirects=True,
        )
        latency_ms = int((time.time() - start) * 1000)

        # LinkedIn returns 999 for bot-detected requests but the site is up.
        # Any status < 500 (or 999) means the server responded.
        if r.status_code == 999:
            return {
                "online": True,
                "latency_ms": latency_ms,
                "status_code": 999,
                "note": "Reachable (bot-detection active)",
            }
        if r.status_code < 400:
            return {
                "online": True,
                "latency_ms": latency_ms,
                "status_code": r.status_code,
                "note": "OK",
            }
        # 4xx — site is up but returned an error (unlikely for homepage)
        return {
            "online": True,
            "latency_ms": latency_ms,
            "status_code": r.status_code,
            "note": f"HTTP {r.status_code}",
        }

    except requests.exceptions.Timeout:
        return {
            "online": False,
            "latency_ms": int((time.time() - start) * 1000),
            "status_code": None,
            "note": "Timeout",
        }
    except requests.exceptions.ConnectionError:
        return {
            "online": False,
            "latency_ms": int((time.time() - start) * 1000),
            "status_code": None,
            "note": "Connection refused",
        }
    except Exception as e:
        return {
            "online": False,
            "latency_ms": int((time.time() - start) * 1000),
            "status_code": None,
            "note": str(e)[:60],
        }


def check_all_sources(sources: list) -> dict:
    """
    Check connectivity for a list of source names concurrently.

    Returns:
        dict of { source_name: health_dict }
    All checks run in parallel — total time ≈ slowest single source.
    """
    results: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(sources), 8)) as executor:
        future_map = {executor.submit(check_source, s): s for s in sources}
        for future in as_completed(future_map):
            source = future_map[future]
            try:
                results[source] = future.result()
            except Exception as e:
                results[source] = {
                    "online": False,
                    "latency_ms": 0,
                    "status_code": None,
                    "note": str(e)[:60],
                }
    return results
