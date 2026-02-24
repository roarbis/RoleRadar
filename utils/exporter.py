import os
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).parent.parent / "data" / "exports"


def jobs_to_dataframe(jobs: list) -> pd.DataFrame:
    """Convert a list of Job objects into a display-ready DataFrame."""
    if not jobs:
        return pd.DataFrame()

    data = [job.to_dict() for job in jobs]
    df = pd.DataFrame(data)

    # Column order for display
    preferred_order = [
        "title",
        "company",
        "location",
        "salary",
        "date_posted",
        "source",
        "url",
        "description_preview",
        "scraped_at",
    ]
    existing = [c for c in preferred_order if c in df.columns]
    df = df[existing]

    # Human-readable column headers
    df.columns = [c.replace("_", " ").title() for c in df.columns]
    return df


def export_to_csv(jobs: list, filename: str = None) -> str:
    """
    Export a list of Job objects to a CSV file.
    Returns the full path to the created file, or None on failure.
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if not jobs:
        logger.warning("No jobs to export.")
        return None

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"jobs_{timestamp}.csv"

    filepath = EXPORTS_DIR / filename
    df = jobs_to_dataframe(jobs)

    # utf-8-sig ensures Excel on Windows opens the file correctly
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    logger.info(f"Exported {len(jobs)} jobs → {filepath}")
    return str(filepath)


def get_csv_as_bytes(jobs: list) -> bytes:
    """Return CSV content as bytes, ready for Streamlit download_button."""
    df = jobs_to_dataframe(jobs)
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
