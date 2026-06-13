FROM python:3.11-slim

WORKDIR /app

ARG TARGETARCH

# Install system dependencies including xmltv tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    xmltv \
    xmltv-util \
    libxmltv-perl \
    curl \
    ca-certificates \
    ffmpeg \
    vainfo \
    git \
    && if [ "$TARGETARCH" = "amd64" ]; then \
         apt-get install -y --no-install-recommends intel-media-va-driver; \
       fi \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

RUN python -c "from services.sportsipy_service import SPORTSIPY_AVAILABLE; assert SPORTSIPY_AVAILABLE, 'sportsipy team imports failed'"

# Create data directory, non-root user (aligns with compose PUID/PGID), entrypoint
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app && \
    chmod +x /app/entrypoint.sh

USER appuser

WORKDIR /app

# Environment variables
ENV DATABASE_URL=sqlite:////app/data/iptv_proxy.db
ENV PORT=8000
ENV SPORTSIPY_REQUEST_INTERVAL=3.0
ENV SPORTSIPY_MAX_REQUESTS_PER_MINUTE=20
ENV SPORTSIPY_CIRCUIT_COOLDOWN_SECONDS=900

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/', timeout=5)"

# Run with entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
