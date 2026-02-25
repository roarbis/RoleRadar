"""
Job title matching logic.

Two modes:
  exact   — the searched role name must appear as a substring of the job title
  similar — also checks a dictionary of related/alternative role titles
"""

from typing import List

# ---------------------------------------------------------------------------
# Related role families
# Add entries here over time as you discover gaps.
# Keys are lowercase; values are lists of alternative titles to also accept.
# ---------------------------------------------------------------------------
RELATED_ROLES: dict = {
    # Project / Delivery
    "project manager": [
        "program manager",
        "project lead",
        "delivery manager",
        "delivery lead",
        "technical delivery lead",
        "project coordinator",
        "project officer",
        "project administrator",
        "pmo",
        "project director",
        "it project manager",
        "technical project manager",
        "agile project manager",
        "project specialist",
        "project consultant",
        "engagement manager",
        "implementation manager",
    ],
    "program manager": [
        "project manager",
        "portfolio manager",
        "delivery manager",
        "program director",
        "programme manager",
    ],
    "delivery manager": [
        "project manager",
        "program manager",
        "engineering manager",
        "release manager",
        "scrum master",
    ],
    # Agile / Product
    "scrum master": [
        "agile coach",
        "agile lead",
        "product owner",
        "delivery lead",
        "iteration manager",
    ],
    "product manager": [
        "product owner",
        "product director",
        "head of product",
        "digital product manager",
        "technical product manager",
        "vp product",
    ],
    "product owner": [
        "product manager",
        "scrum master",
        "business analyst",
    ],
    # Business Analysis
    "business analyst": [
        "systems analyst",
        "functional analyst",
        "solution analyst",
        "process analyst",
        "requirements analyst",
        "product analyst",
        "ba",
    ],
    # Engineering
    "software engineer": [
        "software developer",
        "programmer",
        "full stack developer",
        "full-stack developer",
        "backend developer",
        "front-end developer",
        "frontend developer",
        "software architect",
        "application developer",
        "developer",
    ],
    "software developer": [
        "software engineer",
        "programmer",
        "developer",
        "full stack developer",
    ],
    "devops engineer": [
        "site reliability engineer",
        "sre",
        "infrastructure engineer",
        "cloud engineer",
        "platform engineer",
        "build engineer",
        "release engineer",
    ],
    # Data
    "data scientist": [
        "machine learning engineer",
        "ml engineer",
        "ai engineer",
        "data analyst",
        "research scientist",
        "data engineer",
    ],
    "data analyst": [
        "business intelligence analyst",
        "bi analyst",
        "reporting analyst",
        "analytics engineer",
        "insights analyst",
        "data specialist",
    ],
    "data engineer": [
        "analytics engineer",
        "etl developer",
        "data architect",
        "database developer",
    ],
    # Design
    "ux designer": [
        "ui designer",
        "ux/ui designer",
        "product designer",
        "interaction designer",
        "user experience designer",
        "user interface designer",
        "visual designer",
    ],
    # Sales / Account
    "account manager": [
        "client manager",
        "key account manager",
        "national account manager",
        "customer success manager",
        "relationship manager",
        "sales manager",
    ],
    # Marketing
    "marketing manager": [
        "digital marketing manager",
        "content marketing manager",
        "brand manager",
        "growth marketing manager",
        "campaign manager",
        "marketing specialist",
    ],
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def get_related_roles(role: str) -> List[str]:
    """Return a list of alternative role titles related to the given role."""
    role_lower = _normalize(role)

    # Direct lookup
    if role_lower in RELATED_ROLES:
        return RELATED_ROLES[role_lower]

    # Partial key match (e.g. "Senior Project Manager" → "project manager")
    for key, related in RELATED_ROLES.items():
        if key in role_lower or role_lower in key:
            return related

    # Generic variations: add common level prefixes / strip them
    level_words = {"senior", "junior", "lead", "principal", "staff", "associate", "head", "chief"}
    words = role_lower.split()
    base_words = [w for w in words if w not in level_words]
    variations = []

    if len(base_words) < len(words):
        variations.append(" ".join(base_words))  # stripped base role

    # Add common level variants of the stripped base
    base = " ".join(base_words) if base_words else role_lower
    for prefix in ("senior", "lead", "principal"):
        variations.append(f"{prefix} {base}")

    return variations


def matches_role(job_title: str, role: str, match_type: str = "exact") -> bool:
    """
    Return True if job_title is considered a match for role.

    match_type='exact'   : role must appear as a substring in title (case-insensitive)
    match_type='similar' : also checks related role names AND word-level matching
    """
    title_lower = _normalize(job_title)
    role_lower = _normalize(role)

    # Direct substring match
    if role_lower in title_lower:
        return True

    # Common abbreviation match (e.g. "PM" for "Project Manager")
    abbreviation = "".join(w[0] for w in role_lower.split())
    if len(abbreviation) >= 2 and title_lower == abbreviation:
        return True

    if match_type == "similar":
        # Check related/alternative role titles
        for alt in get_related_roles(role):
            if _normalize(alt) in title_lower:
                return True

        # Word-level matching: if ALL significant words (4+ chars) from the
        # role appear anywhere in the title, it's a match.
        # e.g. "project manager" matches "Project Risk Manager | Defence"
        #       because both "project" and "manager" are in the title.
        role_words = [w for w in role_lower.split() if len(w) >= 4]
        if role_words and all(w in title_lower for w in role_words):
            return True

        # Partial word match: if ANY significant role word appears in
        # the title AND the title also contains a management/leadership
        # keyword, count it. This catches titles like "Project Engineer",
        # "Project Coordinator", "Project Officer" etc.
        _mgmt_keywords = {
            "manager", "lead", "director", "coordinator", "officer",
            "head", "chief", "specialist", "consultant", "analyst",
            "administrator", "supervisor", "executive", "partner",
            "architect", "advisor", "engineer", "associate",
        }
        title_words = set(title_lower.split())
        for rw in role_words:
            if rw in title_lower and title_words & _mgmt_keywords:
                return True

    return False


def filter_jobs(jobs: list, roles: List[str], match_type: str = "exact") -> list:
    """
    Return only jobs whose title matches at least one of the given roles.
    Deduplicates: the same job is only included once even if it matches several roles.

    IMPORTANT: only deduplicate on URL when the URL is non-empty.
    Using an empty string as a dedup key causes all URL-less jobs to collapse to
    a single result — we use title+company as a fallback key instead.
    """
    seen: set = set()
    filtered = []

    for job in jobs:
        # Build a stable dedup key — prefer URL, fall back to title|company
        dedup_key = (
            job.url
            if job.url
            else f"{(job.title or '').lower().strip()}|{(job.company or '').lower().strip()}"
        )
        if dedup_key in seen:
            continue
        for role in roles:
            if matches_role(job.title, role, match_type):
                filtered.append(job)
                seen.add(dedup_key)
                break

    return filtered
