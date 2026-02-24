"""
AI-powered job analysis utilities.

Functions:
  score_job(job, resume_text, provider)            → {score, reason}
  tailor_resume_suggestions(job, resume_text, provider)  → str (numbered list)
  customize_cover_letter(job, resume_text, template, provider)  → str (cover letter)

All functions accept any AIProvider instance.
Cover letter customization works best with Gemini Flash (premium) but functions
correctly with Groq or Ollama as well.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# Character limits sent to the AI — keep prompts tight to save tokens and time
_RESUME_CHARS = 3500
_JOB_DESC_CHARS = 1200
_TEMPLATE_CHARS = 2000


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SCORE_PROMPT = """\
You are a professional recruitment analyst. Score how well this job matches the candidate's resume.

RESUME (candidate background):
{resume_text}

JOB TO EVALUATE:
Title: {title}
Company: {company}
Location: {location}
Description: {description}

Scoring guide:
  90–100 = Excellent match — candidate is highly qualified, meets most/all requirements
  70–89  = Good match — candidate meets the core requirements with minor gaps
  50–69  = Moderate match — relevant experience but notable gaps exist
  30–49  = Weak match — limited relevant experience
  0–29   = Poor match — little to no relevant background

Respond with ONLY valid JSON and nothing else:
{{"score": <integer 0-100>, "reason": "<one concise sentence explaining the score>"}}"""


_TAILOR_PROMPT = """\
You are a professional resume consultant helping a candidate target a specific job.

CANDIDATE RESUME:
{resume_text}

TARGET JOB:
Title: {title}
Company: {company}
Description: {description}

Provide exactly 4–5 specific, actionable suggestions to tailor the resume for this role.
For each suggestion explain:
  (a) What to change, add, or highlight
  (b) Why it helps for THIS specific role

Format as a numbered list (1. 2. 3. etc). Be concrete and specific — avoid generic advice."""


_COVER_LETTER_PROMPT = """\
You are an expert career coach. Write a tailored cover letter for this specific job application.

CANDIDATE RESUME:
{resume_text}

COVER LETTER TEMPLATE / STYLE GUIDE:
{cover_letter_section}

TARGET JOB:
Title: {title}
Company: {company}
Description: {description}

Instructions:
- Highlight the most relevant experience and skills from the resume that match this role
- Mention the company name and role title specifically in the opening
- Keep it to 3–4 short paragraphs, professional and confident tone
- Do NOT use placeholder text like [Your Name] — infer candidate details from the resume
- End with a clear call to action
- Return ONLY the cover letter text, no preamble or explanation

Write the tailored cover letter now:"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_job(job, resume_text: str, provider) -> dict:
    """
    Score a single job's relevance against the candidate's resume.

    Args:
        job:         Job dataclass instance.
        resume_text: Plain text resume content.
        provider:    AIProvider instance.

    Returns:
        {"score": int (0–100 or -1 on error), "reason": str}
    """
    if not resume_text.strip():
        return {"score": -1, "reason": "No resume uploaded."}

    description = (job.description or "").strip()
    if not description:
        description = f"Job title: {job.title} at {job.company} ({job.location})"

    prompt = _SCORE_PROMPT.format(
        resume_text=resume_text[:_RESUME_CHARS],
        title=job.title,
        company=job.company or "Unknown",
        location=job.location or "Australia",
        description=description[:_JOB_DESC_CHARS],
    )

    try:
        raw = provider.generate(prompt, max_tokens=160)
        return _parse_score_response(raw)
    except Exception as e:
        logger.warning(f"Score error for '{job.title}': {e}")
        return {"score": -1, "reason": f"Error: {str(e)[:120]}"}


def tailor_resume_suggestions(job, resume_text: str, provider) -> str:
    """
    Generate actionable resume tailoring suggestions for a specific job.

    Args:
        job:         Job dataclass instance.
        resume_text: Plain text resume content.
        provider:    AIProvider instance (Ollama or Groq recommended — free).

    Returns:
        Numbered list of suggestions as a plain text string.
    """
    if not resume_text.strip():
        raise ValueError("No resume text available. Please upload your resume first.")

    description = (job.description or "").strip()
    if not description:
        description = f"Role: {job.title} at {job.company} ({job.location})"

    prompt = _TAILOR_PROMPT.format(
        resume_text=resume_text[:_RESUME_CHARS],
        title=job.title,
        company=job.company or "Unknown",
        description=description[:_JOB_DESC_CHARS],
    )

    return provider.generate(prompt, max_tokens=900)


def customize_cover_letter(
    job,
    resume_text: str,
    cover_letter_template: str,
    provider,
) -> str:
    """
    Generate a tailored cover letter for a specific job.

    Best quality with Gemini Flash (cost attached), but works with Groq or Ollama too.

    Args:
        job:                    Job dataclass instance.
        resume_text:            Plain text resume content.
        cover_letter_template:  Optional template/style guide. Pass "" for scratch generation.
        provider:               AIProvider instance.

    Returns:
        Generated cover letter as a plain text string.
    """
    if not resume_text.strip():
        raise ValueError("No resume text available. Please upload your resume first.")

    template = (cover_letter_template or "").strip()
    if template:
        cover_section = (
            "Use the following as a structural/style guide (do NOT copy it verbatim):\n\n"
            + template[:_TEMPLATE_CHARS]
        )
    else:
        cover_section = (
            "No template provided — write a professional cover letter from scratch "
            "based on the resume and job details."
        )

    description = (job.description or "").strip()
    if not description:
        description = f"Role: {job.title} at {job.company} ({job.location})"

    prompt = _COVER_LETTER_PROMPT.format(
        resume_text=resume_text[:_RESUME_CHARS],
        cover_letter_section=cover_section,
        title=job.title,
        company=job.company or "Unknown",
        description=description[:_JOB_DESC_CHARS],
    )

    return provider.generate(prompt, max_tokens=1400)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_score_response(raw: str) -> dict:
    """
    Extract score/reason from an AI response that should be JSON.

    Falls back to regex parsing if JSON decode fails (common with smaller models).
    """
    text = raw.strip()

    # Some models wrap JSON in ```json ... ``` — strip it
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Attempt direct JSON parse
    try:
        data = json.loads(text)
        score = int(data.get("score", -1))
        reason = str(data.get("reason", "")).strip()
        return {"score": max(0, min(100, score)), "reason": reason}
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Regex fallback — find score number anywhere in the response
    score_match = re.search(r'"?score"?\s*[=:]\s*(\d{1,3})', text, re.IGNORECASE)
    if score_match:
        score = min(100, max(0, int(score_match.group(1))))
        reason_match = re.search(r'"?reason"?\s*[=:]\s*"([^"]{5,})"', text, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else text[:120].replace("\n", " ")
        return {"score": score, "reason": reason}

    # Last resort — try to find any standalone number
    num_match = re.search(r'\b(\d{1,3})\b', text)
    if num_match:
        score = min(100, max(0, int(num_match.group(1))))
        return {"score": score, "reason": f"Parsed from: {text[:100]}"}

    return {"score": -1, "reason": f"Could not parse AI response: {text[:120]}"}
