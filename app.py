"""
RoleRadar — Streamlit Web App
Run with: streamlit run app.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import streamlit as st

from utils.database import (
    init_db,
    save_jobs,
    get_recent_jobs,
    log_run,
    get_last_run_info,
    get_all_sources,
    clear_jobs_only,
    clear_all_jobs,
)
from utils.matcher import filter_jobs
from utils.exporter import jobs_to_dataframe, get_csv_as_bytes
from scrapers.seek import SeekScraper
from scrapers.indeed import IndeedScraper
from scrapers.jora import JoraScraper
from scrapers.careerone import CareerOneScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.gradconnection import GradConnectionScraper
from scrapers.adzuna import AdzunaScraper
from utils.emailer import send_job_digest
from utils.resume_parser import parse_uploaded_file, save_upload_text, load_saved_text
from utils.scraper_health import check_all_sources
from utils.ai_provider import (
    build_provider,
    OllamaProvider,
    OLLAMA_NAME, GROQ_NAME, GEMINI_NAME,
    SCORING_PROVIDERS, GENERATION_PROVIDERS,
    GROQ_MODELS, GEMINI_MODELS,
)
from utils.ai_scorer import score_job, tailor_resume_suggestions, customize_cover_letter
from utils.ui_components import (
    inject_css, page_header, stat_cards,
    render_job_card, empty_state, section_header,
    get_source_badge_html,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------
init_db()

CONFIG_FILE = Path(__file__).parent / "data" / "config.json"
UPLOADS_DIR = Path(__file__).parent / "data" / "uploads"
SCORES_FILE = Path(__file__).parent / "data" / "scores.json"

# Sources that work (curl_cffi bypasses Cloudflare; no API key needed)
WORKING_SOURCES = ["Seek", "Indeed", "Jora", "LinkedIn", "GradConnection"]
# Sources that need full JS execution (Playwright — coming later)
BLOCKED_SOURCES = ["CareerOne"]
# Sources requiring a free API key
API_SOURCES = ["Adzuna"]

ALL_SOURCES = WORKING_SOURCES + BLOCKED_SOURCES + API_SOURCES


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------
def load_config() -> dict:
    defaults = {
        "roles": [],
        "match_type": "exact",
        "schedule_hours": 24,
        "sources": ["Seek", "Indeed", "Jora", "LinkedIn", "GradConnection"],
        "adzuna_app_id": "",
        "adzuna_app_key": "",
        "location": "Australia",
        "email_sender": "",
        "email_password": "",
        "email_recipient": "",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        # AI settings
        "score_provider": OLLAMA_NAME,
        "gen_provider": GROQ_NAME,
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3.2",
        "groq_key": "",
        "groq_model": "llama-3.1-8b-instant",
        "gemini_key": "",
        "gemini_model": "gemini-1.5-flash",
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# AI / scoring helpers
# ---------------------------------------------------------------------------
def _select_index(options: list, value, default: int = 0) -> int:
    """Safe index lookup for selectboxes — returns default if value not found."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def _load_scores() -> dict:
    """Load persisted job scores from disk."""
    if SCORES_FILE.exists():
        try:
            return json.loads(SCORES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_scores(scores: dict):
    """Save job scores to disk for persistence across restarts."""
    SCORES_FILE.parent.mkdir(exist_ok=True)
    SCORES_FILE.write_text(json.dumps(scores, indent=2), encoding="utf-8")


def _score_badge(score: int) -> str:
    """Return a coloured emoji badge for a relevance score."""
    if score < 0:
        return "⚪"
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    if score >= 40:
        return "🟠"
    return "🔴"


def _provider_status(provider_name: str, ollama_url: str, groq_key: str, gemini_key: str) -> str:
    """Return a short ✅/❌ status string for the given provider."""
    if provider_name == OLLAMA_NAME:
        try:
            p = OllamaProvider(base_url=ollama_url)
            return "✅ Ollama running" if p.is_available else "❌ Ollama not detected"
        except Exception:
            return "❌ Ollama not detected"
    elif provider_name == GROQ_NAME:
        return "✅ Groq key set" if groq_key.strip() else "❌ Groq key missing"
    elif provider_name == GEMINI_NAME:
        return "✅ Gemini key set" if gemini_key.strip() else "❌ Gemini key missing"
    return "❓ Unknown provider"


def build_scraper_map(adzuna_id: str, adzuna_key: str) -> dict:
    return {
        "Seek": SeekScraper(),
        "Indeed": IndeedScraper(),
        "Jora": JoraScraper(),
        "CareerOne": CareerOneScraper(),
        "LinkedIn": LinkedInScraper(),
        "GradConnection": GradConnectionScraper(),
        "Adzuna": AdzunaScraper(app_id=adzuna_id, app_key=adzuna_key),
    }


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RoleRadar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject full LinkedIn-inspired theme immediately after page config
inject_css()

page_header()

# ---------------------------------------------------------------------------
# Session state — initialise once per session
# ---------------------------------------------------------------------------
if "resume_text" not in st.session_state:
    st.session_state["resume_text"] = load_saved_text("resume", UPLOADS_DIR)
if "cover_letter_text" not in st.session_state:
    st.session_state["cover_letter_text"] = load_saved_text("cover_letter", UPLOADS_DIR)
if "job_scores" not in st.session_state:
    st.session_state["job_scores"] = _load_scores()
if "ai_output" not in st.session_state:
    st.session_state["ai_output"] = None   # {"type": ..., "text": ..., "job_title": ...}
if "source_health" not in st.session_state:
    st.session_state["source_health"] = {}   # {source_name: health_dict}
if "last_run_source_counts" not in st.session_state:
    st.session_state["last_run_source_counts"] = {}  # {source_name: count}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
cfg = load_config()

with st.sidebar:
    st.header("Configuration")

    # --- Roles ---
    st.subheader("Job Roles")
    roles_text = st.text_area(
        "Enter roles to search (one per line):",
        value="\n".join(cfg.get("roles", [])),
        height=140,
        placeholder="Project Manager\nBusiness Analyst\nScrum Master",
        help="Each line is a separate search term.",
    )
    roles = [r.strip() for r in roles_text.strip().splitlines() if r.strip()]

    # --- Location ---
    location = st.text_input(
        "Location (keyword):",
        value=cfg.get("location", "Australia"),
        placeholder="Australia, Melbourne, Sydney VIC...",
        help=(
            "Leave as 'Australia' for a nationwide search, or enter a "
            "city/state keyword (e.g. 'Melbourne VIC', 'Sydney', 'Brisbane QLD')."
        ),
    )
    if not location.strip():
        location = "Australia"

    # --- Match type ---
    st.subheader("Matching")
    match_options = {
        "Exact match only": "exact",
        "Include similar / related roles": "similar",
    }
    match_label = st.radio(
        "How to match job titles?",
        options=list(match_options.keys()),
        index=0 if cfg.get("match_type", "exact") == "exact" else 1,
        help=(
            "Exact: title must contain your role name.\n"
            "Similar: also includes related titles from a built-in dictionary."
        ),
    )
    match_type = match_options[match_label]

    # --- Sources ---
    st.subheader("Job Sources")
    saved_sources = cfg.get("sources", WORKING_SOURCES)
    selected_sources = []

    st.markdown("**✅ Working now**")
    for src in WORKING_SOURCES:
        if st.checkbox(src, value=src in saved_sources, key=f"src_{src}"):
            selected_sources.append(src)

    st.markdown("**🔑 Adzuna — free API (optional bonus)**")
    st.caption("Adds extra listings from boards not covered above. Free: 250 calls/month.")
    adzuna_enabled = st.checkbox(
        "Adzuna",
        value="Adzuna" in saved_sources,
        key="src_Adzuna",
    )
    if adzuna_enabled:
        selected_sources.append("Adzuna")

    st.markdown("**🚫 Needs full browser (coming later)**")
    for src in BLOCKED_SOURCES:
        st.checkbox(
            src, value=False, disabled=True, key=f"src_{src}_disabled",
            help="Requires JavaScript execution (Playwright). Will be added in a future update."
        )

    # --- Adzuna API credentials ---
    if adzuna_enabled:
        st.divider()
        st.subheader("Adzuna API Settings")
        st.caption(
            "Free at [developer.adzuna.com](https://developer.adzuna.com/signup) — "
            "250 calls/month included."
        )
        adzuna_id = st.text_input(
            "App ID", value=cfg.get("adzuna_app_id", ""), type="default"
        )
        adzuna_key = st.text_input(
            "App Key", value=cfg.get("adzuna_app_key", ""), type="password"
        )
    else:
        adzuna_id = cfg.get("adzuna_app_id", "")
        adzuna_key = cfg.get("adzuna_app_key", "")

    # --- Schedule ---
    st.divider()
    st.subheader("Schedule")
    schedule_options = {
        "Manual only": 0,
        "Every 6 hours": 6,
        "Every 12 hours": 12,
        "Daily": 24,
        "Every 2 days": 48,
        "Weekly": 168,
    }
    saved_hours = cfg.get("schedule_hours", 24)
    schedule_label = st.selectbox(
        "Frequency:",
        options=list(schedule_options.keys()),
        index=(
            list(schedule_options.values()).index(saved_hours)
            if saved_hours in schedule_options.values()
            else 3
        ),
    )
    schedule_hours = schedule_options[schedule_label]

    # --- AI Settings ---
    st.divider()
    st.subheader("🤖 AI Settings")
    with st.expander("Configure AI providers"):
        st.caption(
            "AI features need at least one provider. "
            "**Ollama** is free and runs privately on your machine. "
            "**Groq** is a free cloud option. "
            "**Gemini Flash** is premium — _cost attached_."
        )

        # -- Scoring provider (relevance scoring + resume tips) --
        st.markdown("**Scoring & resume tips** (free):")
        score_provider_name = st.selectbox(
            "Provider:",
            SCORING_PROVIDERS,
            index=_select_index(SCORING_PROVIDERS, cfg.get("score_provider", OLLAMA_NAME)),
            key="ai_score_provider",
        )

        # -- Generation provider (cover letter) --
        st.markdown("**Cover letter generation:**")
        gen_provider_name = st.selectbox(
            "Provider:",
            GENERATION_PROVIDERS,
            index=_select_index(GENERATION_PROVIDERS, cfg.get("gen_provider", GROQ_NAME)),
            key="ai_gen_provider",
            help=(
                "Groq and Ollama are free. "
                "Gemini Flash produces the highest quality output but has a small cost per request."
            ),
        )

        # -- Ollama sub-section --
        needs_ollama = OLLAMA_NAME in (score_provider_name, gen_provider_name)
        if needs_ollama:
            st.markdown(
                "---\n**Ollama — local & free**\n\n"
                "1. Install: [ollama.com/download/windows](https://ollama.com/download/windows)\n"
                "2. In a terminal: `ollama pull llama3.2`\n"
                "3. Ollama auto-starts as a background service.\n\n"
                "_Lighter: `phi3`  |  Heavier/better: `llama3.1:8b`_"
            )
            ollama_url = st.text_input(
                "Ollama URL:",
                value=cfg.get("ollama_url", "http://localhost:11434"),
                key="ai_ollama_url",
            )
            ollama_model = st.text_input(
                "Model name:",
                value=cfg.get("ollama_model", "llama3.2"),
                key="ai_ollama_model",
                help="Run 'ollama list' to see installed models.",
            )
        else:
            ollama_url = cfg.get("ollama_url", "http://localhost:11434")
            ollama_model = cfg.get("ollama_model", "llama3.2")

        # -- Groq sub-section --
        needs_groq = GROQ_NAME in (score_provider_name, gen_provider_name)
        if needs_groq:
            st.markdown(
                "---\n**Groq — free cloud API**\n"
                "Get a free key at [console.groq.com](https://console.groq.com)"
            )
            groq_key = st.text_input(
                "API key:",
                value=cfg.get("groq_key", ""),
                type="password",
                key="ai_groq_key",
            )
            groq_model = st.selectbox(
                "Model:",
                GROQ_MODELS,
                index=_select_index(GROQ_MODELS, cfg.get("groq_model", GROQ_MODELS[0])),
                key="ai_groq_model",
                help="llama-3.1-8b-instant is fastest. llama-3.3-70b-versatile is highest quality.",
            )
        else:
            groq_key = cfg.get("groq_key", "")
            groq_model = cfg.get("groq_model", GROQ_MODELS[0])

        # -- Gemini sub-section (premium) --
        needs_gemini = GEMINI_NAME in (score_provider_name, gen_provider_name)
        if needs_gemini:
            st.markdown(
                "---\n**✨ Gemini Flash — premium _(cost attached)_**\n"
                "Get a key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). "
                "Each request costs a fraction of a cent — very cheap but not free."
            )
            gemini_key = st.text_input(
                "API key:",
                value=cfg.get("gemini_key", ""),
                type="password",
                key="ai_gemini_key",
            )
            gemini_model = st.selectbox(
                "Model:",
                GEMINI_MODELS,
                index=_select_index(GEMINI_MODELS, cfg.get("gemini_model", GEMINI_MODELS[0])),
                key="ai_gemini_model",
            )
        else:
            gemini_key = cfg.get("gemini_key", "")
            gemini_model = cfg.get("gemini_model", GEMINI_MODELS[0])

    # --- Email ---
    st.divider()
    st.subheader("📧 Email Settings")
    with st.expander("Configure email digest (optional)"):
        st.caption(
            "Send your job list by email. For **Gmail**, generate an "
            "[App Password](https://myaccount.google.com/apppasswords) "
            "(requires 2-Step Verification) and paste it below — "
            "do **not** use your regular account password."
        )
        email_sender = st.text_input(
            "Sender email:",
            value=cfg.get("email_sender", ""),
            placeholder="you@gmail.com",
        )
        email_password = st.text_input(
            "App password:",
            value=cfg.get("email_password", ""),
            type="password",
            help=(
                "Gmail: myaccount.google.com/apppasswords  |  "
                "Outlook: use your password with smtp.office365.com port 587"
            ),
        )
        email_recipient = st.text_input(
            "Send digest to:",
            value=cfg.get("email_recipient", ""),
            placeholder="recipient@example.com",
        )
        email_smtp = st.text_input(
            "SMTP server:",
            value=cfg.get("smtp_server", "smtp.gmail.com"),
        )
        email_port = int(
            st.number_input(
                "SMTP port:",
                value=int(cfg.get("smtp_port", 587)),
                min_value=1,
                max_value=65535,
                step=1,
            )
        )

    st.divider()

    if st.button("💾  Save Configuration", use_container_width=True):
        save_config(
            {
                "roles": roles,
                "match_type": match_type,
                "schedule_hours": schedule_hours,
                "sources": selected_sources,
                "adzuna_app_id": adzuna_id,
                "adzuna_app_key": adzuna_key,
                "location": location,
                "email_sender": email_sender,
                "email_password": email_password,
                "email_recipient": email_recipient,
                "smtp_server": email_smtp,
                "smtp_port": email_port,
                "score_provider": score_provider_name,
                "gen_provider": gen_provider_name,
                "ollama_url": ollama_url,
                "ollama_model": ollama_model,
                "groq_key": groq_key,
                "groq_model": groq_model,
                "gemini_key": gemini_key,
                "gemini_model": gemini_model,
            }
        )
        st.success("Saved!")

    st.divider()
    with st.expander("⚠️ Danger Zone"):
        if st.button("🗑  Clear all saved jobs", type="secondary", use_container_width=True):
            clear_all_jobs()
            st.warning("All jobs cleared.")
            st.rerun()

# ---------------------------------------------------------------------------
# Main — Status metrics (plain, no custom CSS to avoid theme conflicts)
# ---------------------------------------------------------------------------
last_run = get_last_run_info()

if last_run:
    try:
        dt = datetime.fromisoformat(last_run["run_at"])
        _last_run_label = dt.strftime("%d %b  %H:%M")
    except Exception:
        _last_run_label = str(last_run["run_at"])[:16]
else:
    _last_run_label = "Never"

_total_in_db = len(get_recent_jobs(limit=9999))
stat_cards(
    last_run_label=_last_run_label,
    jobs_found=last_run["jobs_found"] if last_run else "—",
    jobs_new=last_run["jobs_new"] if last_run else "—",
    total_in_db=_total_in_db,
)

st.divider()

# ---------------------------------------------------------------------------
# Adzuna setup nudge
# ---------------------------------------------------------------------------
if adzuna_enabled and (not adzuna_id or not adzuna_key):
    st.warning(
        "⚠️ Adzuna is enabled but credentials are missing. "
        "Register free at [developer.adzuna.com](https://developer.adzuna.com/signup) "
        "then paste your App ID and App Key in the sidebar.",
    )

# ---------------------------------------------------------------------------
# Action buttons
# ---------------------------------------------------------------------------
if not roles:
    st.warning("Add at least one role name in the sidebar to get started.")

recent_all = get_recent_jobs(limit=1000)

# ── Action bar ──────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:#fff;border:1px solid #E2E0DB;border-radius:12px;
            padding:1rem 1.25rem;margin-bottom:0.75rem;
            box-shadow:0 1px 3px rgba(0,0,0,0.07)">
  <div style="font-size:0.72rem;font-weight:600;color:#6B7280;
              text-transform:uppercase;letter-spacing:0.6px;margin-bottom:0.6rem">
    Quick Actions
  </div>""", unsafe_allow_html=True)

col_run, col_export, col_email, col_spacer = st.columns([2, 2, 2, 1])

with col_run:
    run_clicked = st.button(
        "▶  Run Now",
        type="primary",
        use_container_width=True,
        disabled=(not roles or not selected_sources),
        help="Scan all selected job boards for new listings" if roles else "Add a role in the sidebar first",
    )

with col_export:
    csv_bytes = get_csv_as_bytes(recent_all) if recent_all else None
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="📥  Export CSV",
        data=csv_bytes or b"",
        file_name=f"roleradar_{timestamp_str}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=(not recent_all),
        help="Download all current results as a spreadsheet",
    )

with col_email:
    email_configured = bool(email_sender and email_password and email_recipient)
    send_email_clicked = st.button(
        "📧  Email Digest",
        use_container_width=True,
        disabled=(not email_configured or not recent_all),
        help=(
            "Send all current jobs to your inbox"
            if email_configured
            else "Configure email settings in the sidebar first"
        ),
    )

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Run scraper
# ---------------------------------------------------------------------------
if run_clicked and roles and selected_sources:
    scraper_map = build_scraper_map(adzuna_id, adzuna_key)
    progress = st.progress(0, text="Starting search...")
    all_raw_jobs = []
    source_results = {}
    source_errors = {}

    for i, source in enumerate(selected_sources):
        progress.progress(i / len(selected_sources), text=f"Searching {source}...")
        try:
            scraper = scraper_map[source]
            jobs = scraper.search(roles, location=location)
            all_raw_jobs.extend(jobs)
            source_results[source] = len(jobs)
            if len(jobs) > 0:
                st.toast(f"{source}: {len(jobs)} jobs found", icon="✅")
            else:
                st.toast(f"{source}: 0 jobs found", icon="ℹ️")
        except Exception as e:
            source_results[source] = 0
            source_errors[source] = str(e)[:80]
            st.toast(f"{source}: error — {str(e)[:60]}", icon="⚠️")
            logging.exception(f"Scraper error ({source})")

    progress.progress(1.0, text="Filtering and saving...")

    filtered = filter_jobs(all_raw_jobs, roles, match_type)

    # Clear previous results so each run shows a clean, fresh list
    clear_jobs_only()

    # Also reset scores & AI output since they referenced the old job list
    st.session_state["job_scores"] = {}
    _save_scores({})
    st.session_state["ai_output"] = None

    total_saved, new_count = save_jobs(filtered)
    log_run(roles, len(filtered), new_count)

    progress.empty()

    # Persist per-source counts so the status tracker can show them
    st.session_state["last_run_source_counts"] = {
        src: {"count": source_results.get(src, 0), "error": source_errors.get(src)}
        for src in selected_sources
    }

    # Summary
    working_totals = {k: v for k, v in source_results.items() if v > 0}
    summary_parts = [f"**{v}** from {k}" for k, v in working_totals.items()]
    summary = ", ".join(summary_parts) if summary_parts else "0 matching jobs"

    st.success(
        f"Done! Matched **{len(filtered)}** jobs ({new_count} new). "
        f"Raw totals — {summary}."
    )

    # Per-source breakdown: raw scraped vs 0 / blocked
    with st.expander("📊 Source breakdown", expanded=(len(filtered) < 5)):
        _breakdown_rows = []
        for _src in selected_sources:
            _raw = source_results.get(_src, 0)
            _err = source_errors.get(_src)
            if _err:
                _status = f"⚠️ error: {_err[:60]}"
            elif _raw == 0:
                _status = "❌ 0 jobs — may be blocked on this server"
            else:
                _status = f"✅ {_raw} raw jobs scraped"
            _breakdown_rows.append({"Source": _src, "Result": _status})
        import pandas as pd
        st.dataframe(pd.DataFrame(_breakdown_rows), hide_index=True, use_container_width=True)
        if any(source_results.get(s, 0) == 0 for s in selected_sources if s not in source_errors):
            st.caption(
                "💡 Sources showing 0 may be blocking searches from cloud server IPs. "
                "LinkedIn and GradConnection tend to work best on Render. "
                "Check Render's log tab for detailed error messages."
            )

    if source_errors:
        with st.expander("⚠️ Source errors"):
            for src, err in source_errors.items():
                st.write(f"**{src}:** {err}")

    st.rerun()

# ---------------------------------------------------------------------------
# Send email digest
# ---------------------------------------------------------------------------
if send_email_clicked:
    with st.spinner("Sending email…"):
        jobs_to_email = get_recent_jobs(limit=1000)
        success, message = send_job_digest(
            jobs=jobs_to_email,
            sender_email=email_sender,
            sender_password=email_password,
            recipient_email=email_recipient,
            smtp_server=email_smtp,
            smtp_port=email_port,
        )
    if success:
        st.success(f"✅ {message}")
    else:
        st.error(f"❌ {message}")

# ---------------------------------------------------------------------------
# Source Status Tracker
# ---------------------------------------------------------------------------
with st.expander("🔌  Source Status  —  connectivity check per job board", expanded=False):
    _health_col, _info_col = st.columns([1, 3])
    with _health_col:
        _check_btn = st.button("🔄 Check Now", use_container_width=True,
                               help="Pings each job site to verify it is reachable from this server.")
    with _info_col:
        st.caption(
            "Live connectivity check — confirms each site is reachable from the server "
            "running RoleRadar. **Online ≠ scraper returning results** (a site can respond "
            "to a homepage ping but still block automated searches by cloud IP)."
        )

    if _check_btn:
        _sources_to_check = WORKING_SOURCES + (["Adzuna"] if adzuna_enabled else [])
        with st.spinner(f"Checking {len(_sources_to_check)} sources in parallel…"):
            st.session_state["source_health"] = check_all_sources(_sources_to_check)

    _health = st.session_state.get("source_health", {})
    _run_counts = st.session_state.get("last_run_source_counts", {})

    if _health:
        import pandas as pd

        _hrows = []
        for _src in WORKING_SOURCES + ["Adzuna"]:
            _h = _health.get(_src)
            if _h is None:
                continue
            _status_icon = "✅ Online" if _h["online"] else "❌ Offline"
            _lat = f"{_h['latency_ms']} ms" if _h.get("latency_ms") else "—"
            _code = str(_h["status_code"]) if _h.get("status_code") else "—"
            _note = _h.get("note", "")

            _rc = _run_counts.get(_src)
            if _rc is not None:
                if _rc.get("error"):
                    _last = f"⚠️ error"
                elif _rc["count"] == 0:
                    _last = "0 jobs (blocked?)"
                else:
                    _last = f"✅ {_rc['count']} jobs"
            else:
                _last = "—"

            _hrows.append({
                "Source": _src,
                "Status": _status_icon,
                "Latency": _lat,
                "HTTP": _code,
                "Last Run": _last,
                "Note": _note,
            })

        st.dataframe(
            pd.DataFrame(_hrows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Note": st.column_config.TextColumn("Note", width="medium"),
            },
        )
    else:
        st.info("Click **🔄 Check Now** to ping all sources. Results from the last scrape run will also appear here automatically.")

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
st.subheader("Results")

tab_all, tab_by_source, tab_ai, tab_about = st.tabs(
    ["📋 All Jobs", "🔍 By Source", "🤖 AI Tools", "ℹ️ About"]
)

with tab_all:
    jobs = get_recent_jobs(limit=500)
    if not jobs:
        empty_state()
    else:
        # ── Filter bar + view toggle ─────────────────────────────────────
        _fc, _tc = st.columns([4, 1])
        with _fc:
            search_filter = st.text_input(
                "filter_all",
                placeholder="🔍  Filter by title, company, location, source…",
                label_visibility="collapsed",
            )
        with _tc:
            st.markdown('<div class="rr-toggle-wrap">', unsafe_allow_html=True)
            view_mode = st.radio(
                "view", ["🃏 Cards", "📋 Table"],
                horizontal=True,
                label_visibility="collapsed",
                key="view_toggle_all",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Apply text filter ────────────────────────────────────────────
        df = jobs_to_dataframe(jobs)
        if search_filter:
            mask = df.apply(
                lambda col: col.astype(str).str.contains(search_filter, case=False, na=False)
            ).any(axis=1)
            df = df[mask]
            _sf_lower = search_filter.lower()
            jobs_display = [
                j for j in jobs
                if any(
                    _sf_lower in str(getattr(j, attr, "") or "").lower()
                    for attr in ("title", "company", "location", "source", "description")
                )
            ]
        else:
            jobs_display = jobs

        st.caption(f"Showing **{len(jobs_display)}** jobs")

        # ── Card view ────────────────────────────────────────────────────
        if view_mode == "🃏 Cards":
            _scores = st.session_state.get("job_scores", {})
            for _job in jobs_display[:300]:
                _key = _job.url or f"{_job.title}|{_job.company}"
                st.markdown(
                    render_job_card(_job, _scores.get(_key)),
                    unsafe_allow_html=True,
                )

        # ── Table view ───────────────────────────────────────────────────
        else:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=540,
                column_config={
                    "Url": st.column_config.LinkColumn("URL", display_text="View Job"),
                },
            )

with tab_by_source:
    sources_in_db = get_all_sources()
    if not sources_in_db:
        empty_state("No jobs yet", "Run a search to populate results by source.")
    else:
        _sc1, _sc2 = st.columns([3, 1])
        with _sc1:
            selected_src = st.selectbox(
                "Source:",
                ["All"] + sorted(sources_in_db),
                label_visibility="collapsed",
            )
        with _sc2:
            st.markdown('<div class="rr-toggle-wrap">', unsafe_allow_html=True)
            src_view = st.radio(
                "src_view", ["🃏 Cards", "📋 Table"],
                horizontal=True,
                label_visibility="collapsed",
                key="view_toggle_src",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        src_filter = None if selected_src == "All" else selected_src
        src_jobs = get_recent_jobs(limit=500, source_filter=src_filter)
        df_src = jobs_to_dataframe(src_jobs)

        # Source header with badge
        if selected_src != "All":
            badge = get_source_badge_html(selected_src)
            st.markdown(
                f'<div style="margin:0.5rem 0 0.75rem;display:flex;align-items:center;gap:0.5rem">'
                f'<span style="font-size:0.85rem;color:#6B7280">Showing jobs from</span>'
                f'{badge}</div>',
                unsafe_allow_html=True,
            )
        st.caption(f"**{len(src_jobs)}** jobs from {selected_src}")

        if src_view == "🃏 Cards":
            _scores_src = st.session_state.get("job_scores", {})
            for _j in src_jobs[:300]:
                _k = _j.url or f"{_j.title}|{_j.company}"
                st.markdown(render_job_card(_j, _scores_src.get(_k)), unsafe_allow_html=True)
        else:
            st.dataframe(
                df_src,
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={
                    "Url": st.column_config.LinkColumn("URL", display_text="View Job"),
                },
            )

with tab_ai:
    # ── Helper: build provider kwargs from sidebar config ──────────────────
    _prov_kwargs = dict(
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        groq_key=groq_key,
        groq_model=groq_model,
        gemini_key=gemini_key,
        gemini_model=gemini_model,
    )

    # ── Section 1: Document Uploads ────────────────────────────────────────
    st.subheader("📁 Your Documents")
    col_resume, col_cl = st.columns(2)

    with col_resume:
        st.markdown("**Resume**")
        uploaded_resume = st.file_uploader(
            "Upload (PDF / DOCX / TXT):",
            type=["pdf", "docx", "txt"],
            key="resume_uploader",
            help="Your resume is parsed locally and never sent anywhere (only to the AI provider you choose).",
        )
        if uploaded_resume is not None:
            try:
                _text = parse_uploaded_file(uploaded_resume)
                if _text:
                    st.session_state["resume_text"] = _text
                    save_upload_text(_text, "resume", UPLOADS_DIR)
                    st.success(f"Resume loaded — {len(_text):,} characters")
                else:
                    st.warning("Parsed the file but extracted no text. Is it a scanned image PDF?")
            except Exception as _e:
                st.error(f"Could not parse resume: {_e}")

        resume_text = st.session_state.get("resume_text", "")
        if resume_text:
            st.caption(f"Resume ready ({len(resume_text):,} chars)")
            with st.expander("Preview resume text"):
                st.text(resume_text[:2000] + ("…" if len(resume_text) > 2000 else ""))
            if st.button("🗑 Clear resume", key="clear_resume"):
                st.session_state["resume_text"] = ""
                save_upload_text("", "resume", UPLOADS_DIR)
                st.rerun()
        else:
            st.info("No resume loaded yet.")

    with col_cl:
        st.markdown("**Cover Letter Template** _(optional)_")
        uploaded_cl = st.file_uploader(
            "Upload (PDF / DOCX / TXT):",
            type=["pdf", "docx", "txt"],
            key="cl_uploader",
            help="Optional — provide a template for style/tone. Leave empty to generate from scratch.",
        )
        if uploaded_cl is not None:
            try:
                _text = parse_uploaded_file(uploaded_cl)
                if _text:
                    st.session_state["cover_letter_text"] = _text
                    save_upload_text(_text, "cover_letter", UPLOADS_DIR)
                    st.success(f"Template loaded — {len(_text):,} characters")
                else:
                    st.warning("Parsed but extracted no text.")
            except Exception as _e:
                st.error(f"Could not parse cover letter: {_e}")

        cl_text = st.session_state.get("cover_letter_text", "")
        if cl_text:
            st.caption(f"Template ready ({len(cl_text):,} chars)")
            with st.expander("Preview template text"):
                st.text(cl_text[:2000] + ("…" if len(cl_text) > 2000 else ""))
            if st.button("🗑 Clear template", key="clear_cl"):
                st.session_state["cover_letter_text"] = ""
                save_upload_text("", "cover_letter", UPLOADS_DIR)
                st.rerun()
        else:
            st.info("No template — AI will write cover letters from scratch.")

    if not st.session_state.get("resume_text"):
        st.warning("⬆️ Upload your resume above to unlock AI scoring and cover letter features.")

    # ── Section 2: Relevance Scoring ───────────────────────────────────────
    st.divider()
    _score_status = _provider_status(score_provider_name, ollama_url, groq_key, gemini_key)
    st.subheader(f"🎯 Relevance Scoring — free   ·   {_score_status}")
    st.caption(
        f"Scores each job (0–100) against your resume using **{score_provider_name}**. "
        "Higher = better match."
    )

    _score_col1, _score_col2, _score_col3 = st.columns([2, 1, 1])
    with _score_col1:
        _score_limit = int(
            st.number_input(
                "Jobs to score:",
                value=20,
                min_value=1,
                max_value=100,
                step=10,
                help="Scoring 20 jobs takes ~1–3 min with Ollama, ~30s with Groq.",
            )
        )
    with _score_col2:
        _can_score = bool(
            st.session_state.get("resume_text")
            and score_provider_name in (OLLAMA_NAME, GROQ_NAME)
            and (
                (score_provider_name == OLLAMA_NAME)
                or (score_provider_name == GROQ_NAME and groq_key)
            )
        )
        _score_btn = st.button(
            "🎯 Score Jobs",
            type="primary",
            use_container_width=True,
            disabled=not _can_score,
        )
    with _score_col3:
        _clear_scores_btn = st.button(
            "🗑 Clear scores",
            use_container_width=True,
            disabled=not st.session_state.get("job_scores"),
        )

    if _clear_scores_btn:
        st.session_state["job_scores"] = {}
        _save_scores({})
        st.rerun()

    if _score_btn and _can_score:
        _jobs_to_score = get_recent_jobs(limit=_score_limit)
        if not _jobs_to_score:
            st.warning("No jobs in database. Run a search first.")
        else:
            try:
                _prov = build_provider(score_provider_name, **_prov_kwargs)
                _bar = st.progress(0, text=f"Scoring {len(_jobs_to_score)} jobs…")
                _scores = dict(st.session_state.get("job_scores", {}))
                for _idx, _j in enumerate(_jobs_to_score):
                    _bar.progress(
                        _idx / len(_jobs_to_score),
                        text=f"Scoring {_idx + 1}/{len(_jobs_to_score)}: {_j.title[:40]}…",
                    )
                    _result = score_job(_j, st.session_state["resume_text"], _prov)
                    _scores[_j.url or f"{_j.title}|{_j.company}"] = {
                        "score": _result["score"],
                        "reason": _result["reason"],
                        "provider": score_provider_name,
                        "scored_at": datetime.now().isoformat(),
                        "title": _j.title,
                        "company": _j.company,
                        "location": _j.location,
                        "source": _j.source,
                        "url": _j.url,
                    }
                _bar.empty()
                st.session_state["job_scores"] = _scores
                _save_scores(_scores)
                st.success(f"Scored {len(_jobs_to_score)} jobs!")
                st.rerun()
            except Exception as _e:
                st.error(f"Scoring error: {_e}")

    # Show scoring results
    _scores = st.session_state.get("job_scores", {})
    if _scores:
        import pandas as pd

        _rows = []
        for _url, _s in _scores.items():
            _rows.append(
                {
                    "Match": _score_badge(_s.get("score", -1)),
                    "Score": _s.get("score", -1) if _s.get("score", -1) >= 0 else "—",
                    "Title": _s.get("title", ""),
                    "Company": _s.get("company", ""),
                    "Location": _s.get("location", ""),
                    "Source": _s.get("source", ""),
                    "Why": _s.get("reason", ""),
                    "URL": _url,
                }
            )
        _df_scores = pd.DataFrame(_rows)
        _df_scores = _df_scores.sort_values(
            by="Score",
            key=lambda col: pd.to_numeric(col, errors="coerce").fillna(-1),
            ascending=False,
        )
        st.caption(f"{len(_df_scores)} jobs scored")
        st.dataframe(
            _df_scores,
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "URL": st.column_config.LinkColumn("Link", display_text="View"),
                "Score": st.column_config.NumberColumn("Score", format="%d"),
                "Why": st.column_config.TextColumn("Reason", width="large"),
            },
        )
    elif not _score_btn:
        if not st.session_state.get("resume_text"):
            pass  # already warned above
        else:
            st.info("Click **🎯 Score Jobs** to rank your saved jobs by relevance.")

    # ── Section 3: Per-Job AI Tools ────────────────────────────────────────
    st.divider()
    _gen_status = _provider_status(gen_provider_name, ollama_url, groq_key, gemini_key)
    _gen_premium = gen_provider_name == GEMINI_NAME
    _gen_label = (
        f"✨ Per-Job AI Tools — {gen_provider_name} _(cost attached)_   ·   {_gen_status}"
        if _gen_premium
        else f"✨ Per-Job AI Tools — {gen_provider_name}   ·   {_gen_status}"
    )
    st.subheader(_gen_label)

    _all_jobs_ai = get_recent_jobs(limit=200)
    if not _all_jobs_ai:
        st.info("No jobs yet. Run a search first, then come back here.")
    elif not st.session_state.get("resume_text"):
        st.info("Upload your resume above to use per-job AI tools.")
    else:
        _job_options = {
            f"{_j.title}  —  {_j.company}  ({_j.source})": _j
            for _j in _all_jobs_ai[:100]
        }
        _selected_label = st.selectbox(
            "Select a job to analyse:",
            list(_job_options.keys()),
        )
        _sel_job = _job_options[_selected_label]

        _can_gen = bool(
            (gen_provider_name == OLLAMA_NAME)
            or (gen_provider_name == GROQ_NAME and groq_key)
            or (gen_provider_name == GEMINI_NAME and gemini_key)
        )

        _tips_col, _cl_col = st.columns(2)
        with _tips_col:
            _tips_btn = st.button(
                "📝 Resume Tailoring Tips (free)",
                use_container_width=True,
                disabled=not _can_score,
                help=f"Uses {score_provider_name} — free",
            )
        with _cl_col:
            _cl_label = (
                "✨ Generate Cover Letter _(cost attached)_"
                if _gen_premium
                else "✨ Generate Cover Letter"
            )
            _cl_btn = st.button(
                _cl_label,
                use_container_width=True,
                disabled=not _can_gen,
                help=(
                    f"Uses {gen_provider_name}. "
                    + ("Each request has a small cost." if _gen_premium else "Free.")
                ),
            )

        if _tips_btn:
            with st.spinner(f"Generating resume tips using {score_provider_name}…"):
                try:
                    _prov = build_provider(score_provider_name, **_prov_kwargs)
                    _result = tailor_resume_suggestions(
                        _sel_job, st.session_state["resume_text"], _prov
                    )
                    st.session_state["ai_output"] = {
                        "type": "tips",
                        "text": _result,
                        "job_title": _sel_job.title,
                        "company": _sel_job.company,
                    }
                except Exception as _e:
                    st.error(f"Error: {_e}")

        if _cl_btn:
            with st.spinner(f"Generating cover letter using {gen_provider_name}…"):
                try:
                    _prov = build_provider(gen_provider_name, **_prov_kwargs)
                    _result = customize_cover_letter(
                        _sel_job,
                        st.session_state["resume_text"],
                        st.session_state.get("cover_letter_text", ""),
                        _prov,
                    )
                    st.session_state["ai_output"] = {
                        "type": "cover_letter",
                        "text": _result,
                        "job_title": _sel_job.title,
                        "company": _sel_job.company,
                    }
                except Exception as _e:
                    st.error(f"Error: {_e}")

        # Output display
        _ai_out = st.session_state.get("ai_output")
        if _ai_out:
            _out_type = _ai_out["type"]
            _out_text = _ai_out["text"]
            _out_job = _ai_out.get("job_title", "")
            _out_co = _ai_out.get("company", "")

            if _out_type == "tips":
                st.markdown(f"#### 📝 Resume Tailoring Tips — *{_out_job}* at *{_out_co}*")
            else:
                st.markdown(f"#### ✨ Cover Letter — *{_out_job}* at *{_out_co}*")

            st.text_area(
                "Output — select all & copy:",
                value=_out_text,
                height=380,
                key="ai_output_display",
            )

            if _out_type == "cover_letter":
                _safe_name = _out_job.replace(" ", "_").replace("/", "-")[:40]
                st.download_button(
                    "📥 Download cover letter (.txt)",
                    data=_out_text.encode("utf-8"),
                    file_name=f"cover_letter_{_safe_name}.txt",
                    mime="text/plain",
                )

            if st.button("🗑 Clear output", key="clear_ai_output"):
                st.session_state["ai_output"] = None
                st.rerun()

    # ── Section 4: Package / setup info ────────────────────────────────────
    st.divider()
    with st.expander("📦 Package & setup info"):
        st.markdown(
            """
            **Required packages** (run once in your terminal):
            ```
            C:\\Temp\\ClaudeCode\\python313\\Scripts\\pip.exe install pypdf python-docx groq google-generativeai
            ```

            **Ollama setup (local, free):**
            1. Download installer: [ollama.com/download/windows](https://ollama.com/download/windows)
            2. Run the installer — Ollama starts as a background Windows service automatically
            3. Open Command Prompt and pull a model:
               ```
               ollama pull llama3.2
               ```
            4. The app will detect Ollama at `http://localhost:11434` automatically

            Model options:
            | Model | Size | Speed | Quality |
            |---|---|---|---|
            | `llama3.2` | 3.8GB | Fast | ⭐⭐⭐ (recommended) |
            | `phi3` | 3.8GB | Very fast | ⭐⭐ |
            | `llama3.1:8b` | 8GB | Medium | ⭐⭐⭐⭐ |
            | `mistral` | 7.2GB | Medium | ⭐⭐⭐⭐ |

            **Groq setup (free cloud):**
            1. Sign up free at [console.groq.com](https://console.groq.com)
            2. Create an API key
            3. Paste it into AI Settings → Groq API key in the sidebar

            **Gemini Flash setup _(cost attached)_:**
            1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
            2. Create an API key
            3. Paste it into AI Settings → Gemini API key in the sidebar
            4. Cost: ~$0.075 per 1M input tokens — a cover letter costs ~$0.0001
            """
        )

with tab_about:
    st.markdown(
        """
        ### RoleRadar — v1.3

        **Job source status**

        **Job source status**

        | Source | Local | Cloud (Render) | Method |
        |---|---|---|---|
        | **LinkedIn** | ✅ ~60/query | ✅ ~60/query | Public HTML |
        | **GradConnection** | ✅ ~20/query | ✅ ~20/query | Public HTML |
        | **Seek** | ✅ ~20/query | ⚠️ 2–5/query | curl_cffi → JSON API |
        | **Indeed** | ✅ ~16/query | ❌ Blocked | curl_cffi → HTML |
        | **Jora** | ✅ ~15/query | ❌ 403 | curl_cffi → HTML |
        | **Adzuna** | ✅ API | ✅ API | Free API key (recommended for cloud) |
        | **CareerOne** | 🚫 — | 🚫 — | Needs Playwright (coming later) |

        **⚡ Running on cloud (Render)?**
        Seek, Indeed, and Jora block datacenter IP ranges. For best results
        on cloud hosting, **enable Adzuna** (free API, works everywhere) and
        rely on LinkedIn + GradConnection. Running locally gives full coverage.

        **Getting Adzuna (recommended)**
        1. Register free at [developer.adzuna.com](https://developer.adzuna.com/signup)
        2. Create an app — you get an **App ID** and **App Key**
        3. Paste both into the Adzuna API Settings section in the sidebar
        4. Free tier: 250 API calls/month (plenty for daily use)

        **Email digest setup (Gmail)**
        1. Enable 2-Step Verification on your Google account
        2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
        3. Generate an App Password for "Mail"
        4. Paste that 16-character password into **App password** in the sidebar
        5. Fill in your sender email, recipient email, and click **📧 Send Email Digest**

        **Matching modes**
        - **Exact** — job title must contain your role name (case-insensitive)
        - **Similar** — also matches related titles from a built-in dictionary

        **Location search**
        - Leave as `Australia` for nationwide results
        - Enter a city/state to narrow results (e.g. `Melbourne VIC`, `Sydney`, `Brisbane QLD`)

        **Data storage**
        All jobs saved in `data/jobs.db` (SQLite). Re-running never creates duplicates.

        **AI features (🤖 AI Tools tab)**
        - Upload resume (PDF / DOCX / TXT) — stored locally, never shared except with your chosen AI
        - **Relevance scoring** — ranks jobs 0–100 against your resume (Ollama free / Groq free)
        - **Resume tailoring tips** — per-job suggestions (Ollama free / Groq free)
        - **Cover letter generation** — tailored per job (Groq free / Gemini Flash _cost attached_)

        **AI provider options**
        | Provider | Cost | Privacy | Speed |
        |---|---|---|---|
        | Ollama (local) | Free | 100% private | Medium |
        | Groq | Free tier | Cloud (US) | Fast |
        | Gemini Flash | Cost attached | Cloud (Google) | Fast |

        **Coming next**
        - Browser mode for CareerOne (Playwright headless Chrome)
        - Auto-email new jobs + AI digest summary
        """
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
if schedule_hours > 0:
    st.caption(
        f"⏱ Auto-run set to every {schedule_hours}h. "
        "Keep this tab open for automatic searches."
    )
