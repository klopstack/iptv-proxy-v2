FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including xmltv tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    xmltv \
    xmltv-util \
    libxmltv-perl \
    curl \
    ca-certificates \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory and make entrypoint executable
RUN mkdir -p /app/data && \
    chmod +x /app/entrypoint.sh

# Set working directory for data storage
WORKDIR /app

# Environment variables
ENV DATABASE_URL=sqlite:////app/data/iptv_proxy.db
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/', timeout=5)"

# Run with entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
