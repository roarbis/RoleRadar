# Job Hunter Australia

A personal job-board scraper that searches Seek, Indeed, Jora, CareerOne, and LinkedIn
for roles you specify, deduplicates results, and lets you export a CSV at any time.

---

## Requirements

- Python 3.10 or later
- Internet connection

---

## Setup (one-time)

### 1. Open a terminal in this folder

If you're on **Linux / WSL**:
```bash
cd /path/to/job-scraper
```

If you're on **Windows (Command Prompt or PowerShell)**:
```
cd C:\path\to\job-scraper
```

---

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

Activate it:

- Linux / WSL / Mac:
  ```bash
  source venv/bin/activate
  ```
- Windows CMD:
  ```
  venv\Scripts\activate.bat
  ```
- Windows PowerShell:
  ```
  venv\Scripts\Activate.ps1
  ```

You should see `(venv)` at the start of your prompt.

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This takes 1–2 minutes the first time.

---

### 4. Run the app

```bash
streamlit run app.py
```

Your browser will open automatically at `http://localhost:8501`.

---

## How to use

1. **Add roles** in the sidebar — one per line (e.g. `Project Manager`)
2. **Choose match type**
   - *Exact* — title must contain your role name
   - *Similar* — also matches related titles (e.g. Delivery Manager, Program Manager)
3. **Select sources** — tick the job boards you want to search
4. **Click Run Now** — searches all selected boards and saves results
5. **Export CSV** — downloads all saved jobs as a spreadsheet

---

## Project structure

```
job-scraper/
├── app.py                  ← Streamlit UI (start here)
├── requirements.txt
├── scrapers/
│   ├── base.py             ← Job dataclass + base scraper
│   ├── seek.py
│   ├── indeed.py
│   ├── jora.py
│   ├── careerone.py
│   └── linkedin.py
├── utils/
│   ├── database.py         ← SQLite storage
│   ├── matcher.py          ← Role matching logic
│   └── exporter.py         ← CSV export
└── data/                   ← Created automatically
    ├── jobs.db             ← Local database
    ├── config.json         ← Your saved settings
    └── exports/            ← CSV exports saved here
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | Make sure the virtual environment is activated |
| A scraper returns 0 jobs | The site may have changed its HTML structure — open an issue |
| LinkedIn always returns 0 | Expected — LinkedIn blocks unauthenticated scraping heavily |
| CSV opens with garbled characters | Open with Excel → Data → From Text/CSV, choose UTF-8 |

---

## Planned features (future versions)

- [ ] Email digest with new listings
- [ ] Resume and cover letter upload
- [ ] AI-powered relevance scoring (using Ollama locally — free)
- [ ] Auto-generated custom cover letters per job application
- [ ] Cloud deployment (always-on, no need to leave laptop running)
