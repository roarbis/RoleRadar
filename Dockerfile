# ── RoleRadar — Dockerfile ──────────────────────────────────────────────────
# Multi-stage build keeps the final image lean.
# Build:  docker build -t roleradar .
# Run:    docker run -p 8501:8501 -v $(pwd)/data:/app/data roleradar
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS base

# System deps needed by curl_cffi (libcurl) and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libcurl4 \
        libxml2 \
        libxslt1.1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first — layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure the data directory exists (it's gitignored but must exist at runtime)
RUN mkdir -p /app/data /app/data/uploads

# Streamlit config
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

# Health check — Streamlit's /_stcore/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
