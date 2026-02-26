"""
RoleRadar — UI Components & Theme
LinkedIn-inspired professional light theme.

Usage in app.py:
    from utils.ui_components import inject_css, render_job_card, page_header
"""

import streamlit as st
from html import escape as _esc

# ── Source brand colours ───────────────────────────────────────────────────
SOURCE_COLORS: dict[str, dict] = {
    "Seek":           {"bg": "#E3EFFE", "text": "#1557B0", "border": "#B3CCFC"},
    "LinkedIn":       {"bg": "#E8F3FC", "text": "#0A66C2", "border": "#A9CDED"},
    "Indeed":         {"bg": "#E3E9FF", "text": "#003A9B", "border": "#AABAF8"},
    "Jora":           {"bg": "#FDEEEE", "text": "#B91C1C", "border": "#FCA5A5"},
    "Adzuna":         {"bg": "#FEF0E8", "text": "#C44B10", "border": "#FDBA74"},
    "GradConnection": {"bg": "#F3E8FF", "text": "#6B21A8", "border": "#D8B4FE"},
    "CareerOne":      {"bg": "#ECFDF5", "text": "#065F46", "border": "#6EE7B7"},
}
_DEFAULT_COLOR = {"bg": "#F1F5F9", "text": "#475569", "border": "#CBD5E1"}


def get_source_badge_html(source: str) -> str:
    c = SOURCE_COLORS.get(source, _DEFAULT_COLOR)
    return (
        f'<span style="'
        f'background:{c["bg"]};color:{c["text"]};'
        f'border:1px solid {c["border"]};'
        f'padding:2px 10px;border-radius:20px;'
        f'font-size:0.7rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.6px;'
        f'white-space:nowrap;display:inline-block">{source}</span>'
    )


def render_job_card(job, score_data: dict | None = None) -> str:
    """Return the full HTML string for one job card.
    All user data is HTML-escaped to prevent injection / broken layouts.
    All styles are inline to guarantee they apply regardless of Streamlit
    CSS scoping behaviour.
    """
    # Escape every piece of user-supplied text
    title    = _esc((job.title    or "Untitled").strip())
    company  = _esc((job.company  or "Unknown").strip())
    location = _esc((job.location or "").strip())
    salary   = _esc((job.salary   or "").strip())
    source   = (job.source or "").strip()          # used only for badge lookup
    url      = (job.url    or "").strip()           # used in href, not displayed
    raw_desc = (job.description or "").strip()
    raw_desc = raw_desc[:160] + ("…" if len(raw_desc) > 160 else "")
    desc     = _esc(raw_desc)
    date_lbl = _esc(str(job.date_posted)[:10]) if job.date_posted else ""

    source_badge = get_source_badge_html(source)

    # ── AI score bubble ────────────────────────────────────────────────
    score_html = ""
    if score_data and score_data.get("score", -1) >= 0:
        s = score_data["score"]
        reason = _esc((score_data.get("reason") or "")[:140])
        if s >= 80:
            sc, bg, bd = "#057642", "#DCFCE7", "#86EFAC"
        elif s >= 60:
            sc, bg, bd = "#92400E", "#FEF3C7", "#FCD34D"
        elif s >= 40:
            sc, bg, bd = "#9A3412", "#FFF7ED", "#FDBA74"
        else:
            sc, bg, bd = "#64748B", "#F8FAFC", "#CBD5E1"
        score_html = (
            f'<span title="{reason}" style="background:{bg};color:{sc};'
            f'border:1.5px solid {bd};width:36px;height:36px;border-radius:50%;'
            f'display:inline-flex;align-items:center;justify-content:center;'
            f'font-weight:700;font-size:0.82rem;flex-shrink:0;cursor:help">{s}</span>'
        )

    # ── Meta row ───────────────────────────────────────────────────────
    meta_items = []
    if location:
        meta_items.append(f'<span>📍 {location}</span>')
    if salary:
        meta_items.append(f'<span>💰 {salary}</span>')
    if date_lbl:
        meta_items.append(f'<span>🗓 {date_lbl}</span>')
    meta_html = ""
    if meta_items:
        meta_html = (
            '<div style="display:flex;flex-wrap:wrap;gap:0.8rem;'
            'font-size:0.8rem;color:#6B7280;margin:0.35rem 0 0.5rem 0">'
            + "".join(meta_items) + "</div>"
        )

    # ── Description snippet ────────────────────────────────────────────
    desc_html = (
        f'<div style="font-size:0.8rem;color:#6B7280;line-height:1.5;'
        f'margin-bottom:0.6rem;overflow:hidden;'
        f'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">'
        f'{desc}</div>'
    ) if desc else ""

    # ── Action button ──────────────────────────────────────────────────
    safe_url = _esc(url)
    action = (
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" '
        f'style="display:inline-block;background:#0A66C2;color:#fff !important;'
        f'text-decoration:none;padding:6px 20px;border-radius:20px;'
        f'font-size:0.8rem;font-weight:600;letter-spacing:0.1px;'
        f'white-space:nowrap">View Job →</a>'
    ) if url else (
        '<span style="font-size:0.8rem;color:#94A3B8;font-style:italic">No link</span>'
    )

    # Card — all layout is inline to guarantee rendering in Streamlit markdown
    return (
        '<div style="background:#fff;border:1px solid #E2E0DB;border-radius:12px;'
        'padding:1.1rem 1.4rem;margin-bottom:0.65rem;'
        'box-shadow:0 1px 3px rgba(0,0,0,0.07);">'

        # Header row: title+company on left, badges on right
        '<div style="display:flex;justify-content:space-between;'
        'align-items:flex-start;gap:0.75rem;width:100%">'

        # Left column — title + company (overflow-safe)
        '<div style="flex:1 1 auto;overflow:hidden;min-width:0">'
        f'<div style="font-size:1.02rem;font-weight:700;color:#0F172A;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
        f'max-width:100%" title="{title}">{title}</div>'
        f'<div style="font-size:0.87rem;font-weight:500;color:#374151;'
        f'margin-top:0.15rem;overflow:hidden;text-overflow:ellipsis;'
        f'white-space:nowrap">{company}</div>'
        '</div>'

        # Right column — source badge + score (never shrinks)
        '<div style="display:flex;align-items:center;gap:0.4rem;'
        'flex-shrink:0;flex:0 0 auto;padding-top:2px">'
        f'{source_badge}{score_html}'
        '</div>'
        '</div>'  # end header row

        f'{meta_html}'
        f'{desc_html}'

        # Footer row — action button
        '<div style="display:flex;align-items:center">'
        f'{action}'
        '</div>'

        '</div>'  # end card
    )


def page_header(subtitle: str = "Scan every Australian job board. Find your next role.") -> None:
    """Render the branded gradient page header."""
    st.markdown(f"""
<div class="rr-hero">
  <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.35rem">
    <span style="font-size:2rem;line-height:1">📡</span>
    <h1 style="margin:0;font-size:1.9rem;font-weight:800;
               color:#fff;letter-spacing:-0.5px">RoleRadar</h1>
  </div>
  <p style="margin:0;font-size:0.95rem;color:rgba(255,255,255,0.82);
            font-weight:400;max-width:520px">{subtitle}</p>
</div>
""", unsafe_allow_html=True)


def stat_cards(last_run_label: str, jobs_found, jobs_new, total_in_db) -> None:
    """Render four metric stat cards in a row."""
    cols = st.columns(4)
    _cards = [
        ("🕐", "Last Run",          last_run_label,        "#0A66C2"),
        ("📋", "Jobs (Last Run)",   str(jobs_found or "—"), "#059669"),
        ("✨", "New (Last Run)",    str(jobs_new   or "—"), "#D97706"),
        ("🗄", "Total in Database", str(total_in_db),      "#7C3AED"),
    ]
    for col, (icon, label, value, color) in zip(cols, _cards):
        with col:
            st.markdown(f"""
<div class="rr-stat">
  <div style="font-size:1.5rem;margin-bottom:0.3rem">{icon}</div>
  <div style="font-size:1.5rem;font-weight:800;color:{color};line-height:1.1">{value}</div>
  <div style="font-size:0.73rem;color:#6B7280;font-weight:500;
              text-transform:uppercase;letter-spacing:0.5px;margin-top:0.2rem">{label}</div>
</div>""", unsafe_allow_html=True)


def empty_state(message: str = "No jobs yet", hint: str = "Click **▶ Run Now** to start scanning job boards.") -> None:
    st.markdown(f"""
<div class="rr-empty">
  <div style="font-size:3.5rem;margin-bottom:1rem">📡</div>
  <div style="font-size:1.1rem;font-weight:700;color:#374151;margin-bottom:0.4rem">{message}</div>
  <div style="font-size:0.88rem;color:#6B7280">{hint}</div>
</div>""", unsafe_allow_html=True)


def section_header(icon: str, title: str, badge: str = "") -> None:
    badge_html = f'<span class="rr-section-badge">{badge}</span>' if badge else ""
    st.markdown(f"""
<div class="rr-section-header">
  <span style="font-size:1.15rem">{icon}</span>
  <span style="font-size:1.05rem;font-weight:700;color:#111827">{title}</span>
  {badge_html}
</div>""", unsafe_allow_html=True)


def inject_css() -> None:
    """Inject the full RoleRadar LinkedIn-inspired CSS into the page."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ── CSS ────────────────────────────────────────────────────────────────────
_CSS = """<style>
/* ═══════════════════════════════════════════════════════════════════════════
   RoleRadar — LinkedIn-inspired Professional Light Theme
   ═══════════════════════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Design tokens ──────────────────────────────────────────────────────── */
:root {
  --rr-bg:          #F3F2EE;
  --rr-surface:     #FFFFFF;
  --rr-border:      #E2E0DB;
  --rr-blue:        #0A66C2;
  --rr-blue-dark:   #004182;
  --rr-blue-light:  #EBF3FB;
  --rr-text:        #0F172A;
  --rr-text-2:      #374151;
  --rr-text-3:      #6B7280;
  --rr-radius:      12px;
  --rr-shadow-sm:   0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.05);
  --rr-shadow:      0 4px 12px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.05);
  --rr-shadow-lg:   0 10px 30px rgba(0,0,0,0.10), 0 4px 8px rgba(0,0,0,0.06);
  --rr-font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ── Base ────────────────────────────────────────────────────────────────── */
.stApp,
[data-testid="stAppViewContainer"] {
  background-color: var(--rr-bg) !important;
  font-family: var(--rr-font) !important;
}

.main .block-container {
  padding-top: 1.25rem !important;
  padding-bottom: 3rem !important;
  max-width: 1120px !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
  background-color: var(--rr-surface) !important;
  border-right: 1px solid var(--rr-border) !important;
}

[data-testid="stSidebar"] .block-container {
  padding-top: 1rem !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  font-family: var(--rr-font) !important;
  font-weight: 700 !important;
  color: var(--rr-text) !important;
  font-size: 0.95rem !important;
}

[data-testid="stSidebar"] hr {
  border-color: var(--rr-border) !important;
  margin: 0.65rem 0 !important;
}

[data-testid="stSidebar"] .stCaption {
  color: var(--rr-text-3) !important;
}

/* ── Headings ─────────────────────────────────────────────────────────────── */
h1, h2, h3, h4 {
  font-family: var(--rr-font) !important;
  color: var(--rr-text) !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */

/* Primary */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, #0A66C2 0%, #0073B1 100%) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 24px !important;
  font-family: var(--rr-font) !important;
  font-weight: 600 !important;
  font-size: 0.9rem !important;
  letter-spacing: 0.1px !important;
  padding: 0.55rem 1.8rem !important;
  box-shadow: 0 2px 8px rgba(10,102,194,0.3) !important;
  transition: all 0.2s ease !important;
}

.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(135deg, #004182 0%, #0A66C2 100%) !important;
  box-shadow: 0 4px 18px rgba(10,102,194,0.45) !important;
  transform: translateY(-1px) !important;
}

/* Secondary */
.stButton > button[kind="secondary"],
.stButton > button[data-testid="baseButton-secondary"],
.stButton > button:not([kind]) {
  background: var(--rr-surface) !important;
  color: var(--rr-blue) !important;
  border: 1.5px solid var(--rr-blue) !important;
  border-radius: 24px !important;
  font-family: var(--rr-font) !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  padding: 0.5rem 1.5rem !important;
  transition: all 0.2s ease !important;
}

.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind]):hover {
  background: var(--rr-blue-light) !important;
  border-color: var(--rr-blue-dark) !important;
}

/* Download button */
.stDownloadButton > button {
  background: var(--rr-surface) !important;
  color: var(--rr-blue) !important;
  border: 1.5px solid var(--rr-blue) !important;
  border-radius: 24px !important;
  font-family: var(--rr-font) !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  transition: all 0.2s ease !important;
}

.stDownloadButton > button:hover {
  background: var(--rr-blue-light) !important;
}

/* ── Metrics ──────────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
  background: var(--rr-surface) !important;
  border: 1px solid var(--rr-border) !important;
  border-radius: var(--rr-radius) !important;
  padding: 1rem 1.25rem !important;
  box-shadow: var(--rr-shadow-sm) !important;
}

[data-testid="stMetricLabel"] {
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  color: var(--rr-text-3) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.5px !important;
}

[data-testid="stMetricValue"] {
  font-size: 1.6rem !important;
  font-weight: 800 !important;
  color: var(--rr-text) !important;
  line-height: 1.2 !important;
}

/* ── Expanders ────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  background: var(--rr-surface) !important;
  border: 1px solid var(--rr-border) !important;
  border-radius: var(--rr-radius) !important;
  box-shadow: var(--rr-shadow-sm) !important;
  overflow: hidden !important;
}

[data-testid="stExpander"] > details > summary {
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  color: var(--rr-text-2) !important;
  padding: 0.75rem 1rem !important;
  background: var(--rr-surface) !important;
}

[data-testid="stExpander"] > details[open] > summary {
  border-bottom: 1px solid var(--rr-border) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  background: var(--rr-surface) !important;
  border-radius: var(--rr-radius) var(--rr-radius) 0 0 !important;
  padding: 0 0.75rem !important;
  gap: 0 !important;
  border-bottom: 2px solid var(--rr-border) !important;
  box-shadow: var(--rr-shadow-sm) !important;
}

.stTabs [data-baseweb="tab"] {
  font-family: var(--rr-font) !important;
  font-weight: 600 !important;
  font-size: 0.87rem !important;
  color: var(--rr-text-3) !important;
  padding: 0.75rem 1.25rem !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -2px !important;
  letter-spacing: 0.1px !important;
  background: transparent !important;
}

.stTabs [data-baseweb="tab"]:hover {
  color: var(--rr-blue) !important;
  background: var(--rr-blue-light) !important;
  border-radius: 8px 8px 0 0 !important;
}

.stTabs [aria-selected="true"] {
  color: var(--rr-blue) !important;
  border-bottom: 2.5px solid var(--rr-blue) !important;
}

.stTabs [data-baseweb="tab-panel"] {
  background: var(--rr-surface) !important;
  border: 1px solid var(--rr-border) !important;
  border-top: none !important;
  border-radius: 0 0 var(--rr-radius) var(--rr-radius) !important;
  padding: 1.5rem !important;
  box-shadow: var(--rr-shadow-sm) !important;
}

/* ── Dataframe ────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--rr-border) !important;
  border-radius: var(--rr-radius) !important;
  overflow: hidden !important;
  box-shadow: var(--rr-shadow-sm) !important;
}

/* ── Inputs ───────────────────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
  border-radius: 8px !important;
  border: 1.5px solid var(--rr-border) !important;
  font-family: var(--rr-font) !important;
  font-size: 0.9rem !important;
  background: var(--rr-surface) !important;
  color: var(--rr-text) !important;
  transition: border-color 0.18s, box-shadow 0.18s !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
  border-color: var(--rr-blue) !important;
  box-shadow: 0 0 0 3px rgba(10,102,194,0.12) !important;
  outline: none !important;
}

/* ── Select ───────────────────────────────────────────────────────────────── */
.stSelectbox > div > div,
.stMultiSelect > div > div {
  border-radius: 8px !important;
  border: 1.5px solid var(--rr-border) !important;
  font-family: var(--rr-font) !important;
  background: var(--rr-surface) !important;
}

/* ── Progress bar ─────────────────────────────────────────────────────────── */
.stProgress > div > div > div > div {
  background: linear-gradient(90deg, #0A66C2, #0073B1) !important;
  border-radius: 4px !important;
}

/* ── Alerts ───────────────────────────────────────────────────────────────── */
.stAlert, [data-testid="stAlert"] {
  border-radius: var(--rr-radius) !important;
  font-family: var(--rr-font) !important;
  font-size: 0.88rem !important;
}

/* ── Checkboxes ───────────────────────────────────────────────────────────── */
input[type="checkbox"]:checked {
  accent-color: var(--rr-blue) !important;
}

/* ── Divider ──────────────────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid var(--rr-border) !important;
  margin: 0.9rem 0 !important;
}

/* ── Caption ──────────────────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaption"], small {
  color: var(--rr-text-3) !important;
  font-size: 0.8rem !important;
  font-family: var(--rr-font) !important;
}

/* ── Spinner ──────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
  border-top-color: var(--rr-blue) !important;
}

/* ── Toasts ───────────────────────────────────────────────────────────────── */
[data-testid="stToast"] {
  border-radius: var(--rr-radius) !important;
  box-shadow: var(--rr-shadow) !important;
  font-family: var(--rr-font) !important;
  font-size: 0.85rem !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   RoleRadar Custom Components
   ═══════════════════════════════════════════════════════════════════════════ */

/* Hero banner */
.rr-hero {
  background: linear-gradient(135deg, #0A66C2 0%, #0073B1 55%, #004182 100%);
  border-radius: var(--rr-radius);
  padding: 1.6rem 2rem;
  margin-bottom: 1.25rem;
  box-shadow: 0 6px 24px rgba(10,102,194,0.28);
  position: relative;
  overflow: hidden;
}

.rr-hero::before {
  content: "";
  position: absolute;
  top: -40%;
  right: -10%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
  pointer-events: none;
}

/* Stat cards */
.rr-stat {
  background: var(--rr-surface);
  border: 1px solid var(--rr-border);
  border-radius: var(--rr-radius);
  padding: 1.1rem 1rem;
  box-shadow: var(--rr-shadow-sm);
  text-align: center;
  transition: box-shadow 0.2s, transform 0.15s;
}

.rr-stat:hover {
  box-shadow: var(--rr-shadow);
  transform: translateY(-1px);
}

/* Job cards */
.rr-card {
  background: var(--rr-surface);
  border: 1px solid var(--rr-border);
  border-radius: var(--rr-radius);
  padding: 1.15rem 1.4rem;
  margin-bottom: 0.65rem;
  box-shadow: var(--rr-shadow-sm);
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
}

.rr-card:hover {
  box-shadow: var(--rr-shadow);
  border-color: var(--rr-blue);
  transform: translateY(-1px);
}

.rr-job-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--rr-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
}

.rr-job-company {
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--rr-text-2);
  margin-top: 0.15rem;
}

/* Section header */
.rr-section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.25rem 0 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--rr-border);
}

.rr-section-badge {
  background: var(--rr-blue);
  color: white;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 20px;
  letter-spacing: 0.4px;
}

/* Empty state */
.rr-empty {
  text-align: center;
  padding: 3.5rem 1.5rem;
  color: var(--rr-text-3);
}

/* Action bar */
.rr-action-bar {
  background: var(--rr-surface);
  border: 1px solid var(--rr-border);
  border-radius: var(--rr-radius);
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
  box-shadow: var(--rr-shadow-sm);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

/* View toggle pills */
.rr-toggle-wrap .stRadio > div {
  display: flex !important;
  flex-direction: row !important;
  gap: 0 !important;
  background: #F1F5F9;
  border-radius: 24px;
  padding: 3px;
}

.rr-toggle-wrap .stRadio > div > label {
  border-radius: 20px !important;
  padding: 4px 16px !important;
  font-size: 0.82rem !important;
  font-weight: 600 !important;
  cursor: pointer !important;
  transition: all 0.18s !important;
  color: var(--rr-text-3) !important;
  margin: 0 !important;
}

.rr-toggle-wrap .stRadio [aria-checked="true"] + div {
  background: var(--rr-surface) !important;
  color: var(--rr-blue) !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
  border-radius: 20px !important;
}

/* Info / warning boxes */
.rr-info-box {
  background: #EBF5FB;
  border: 1px solid #BFDBF7;
  border-left: 3px solid var(--rr-blue);
  border-radius: 8px;
  padding: 0.65rem 1rem;
  font-size: 0.85rem;
  color: #1E3A5F;
  margin: 0.5rem 0;
}

/* Sidebar navigation labels */
[data-testid="stSidebar"] .stMarkdown h3 {
  font-size: 0.78rem !important;
  text-transform: uppercase !important;
  letter-spacing: 0.7px !important;
  color: var(--rr-text-3) !important;
  font-weight: 600 !important;
  margin-bottom: 0.25rem !important;
}

/* Floating scroll-to-top feel — add subtle top border accent */
.main .block-container::before {
  content: "";
  display: block;
  height: 3px;
  background: linear-gradient(90deg, #0A66C2, #0073B1, #004182);
  border-radius: 0 0 4px 4px;
  margin-bottom: 0.5rem;
}
</style>"""
