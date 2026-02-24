import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def init_db():
    """Create database tables if they don't exist."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            company     TEXT,
            location    TEXT,
            salary      TEXT,
            date_posted TEXT,
            url         TEXT    UNIQUE,
            source      TEXT,
            description TEXT,
            scraped_at  TEXT,
            first_seen  TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at     TEXT,
            roles      TEXT,
            jobs_found INTEGER,
            jobs_new   INTEGER
        )
    """
    )

    conn.commit()
    conn.close()


def save_jobs(jobs: list) -> tuple:
    """
    Save a list of Job objects to the database.
    Returns (total_processed, new_count).
    """
    if not jobs:
        return 0, 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    new_count = 0

    for job in jobs:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (title, company, location, salary, date_posted, url,
                     source, description, scraped_at, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    job.title,
                    job.company,
                    job.location,
                    job.salary,
                    job.date_posted,
                    job.url,
                    job.source,
                    job.description,
                    job.scraped_at,
                    now,
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1
        except Exception as e:
            logger.debug(f"DB save error: {e}")

    conn.commit()
    conn.close()
    return len(jobs), new_count


def get_recent_jobs(limit: int = 500, source_filter: str = None) -> list:
    """Fetch recent jobs from the database."""
    from scrapers.base import Job

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if source_filter:
        cursor.execute(
            """
            SELECT title, company, location, salary, date_posted,
                   url, source, description, scraped_at
            FROM jobs
            WHERE source = ?
            ORDER BY first_seen DESC
            LIMIT ?
        """,
            (source_filter, limit),
        )
    else:
        cursor.execute(
            """
            SELECT title, company, location, salary, date_posted,
                   url, source, description, scraped_at
            FROM jobs
            ORDER BY first_seen DESC
            LIMIT ?
        """,
            (limit,),
        )

    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        jobs.append(
            Job(
                title=row[0] or "",
                company=row[1] or "",
                location=row[2] or "",
                salary=row[3],
                date_posted=row[4],
                url=row[5] or "",
                source=row[6] or "",
                description=row[7] or "",
                scraped_at=row[8] or "",
            )
        )
    return jobs


def log_run(roles: list, jobs_found: int, jobs_new: int):
    """Record a scrape run in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scrape_runs (run_at, roles, jobs_found, jobs_new)
        VALUES (?, ?, ?, ?)
    """,
        (datetime.now().isoformat(), ", ".join(roles), jobs_found, jobs_new),
    )
    conn.commit()
    conn.close()


def get_last_run_info() -> dict:
    """Return metadata about the most recent scrape run, or None."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT run_at, roles, jobs_found, jobs_new FROM scrape_runs ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "run_at": row[0],
            "roles": row[1],
            "jobs_found": row[2],
            "jobs_new": row[3],
        }
    return None


def get_all_sources() -> list:
    """Return list of distinct sources currently in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT source FROM jobs ORDER BY source")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def clear_jobs_only():
    """Delete all job records but keep the scrape run history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def clear_all_jobs():
    """Delete all job records AND run history (for full reset)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM scrape_runs")
    conn.commit()
    conn.close()
