# Single-image build: React UI + API in one container on port 8000.
#   docker build -t repoxray . && docker run -p 8000:8000 -v repoxray:/data repoxray
FROM node:22-alpine AS web
WORKDIR /web
ENV NODE_OPTIONS=--max-old-space-size=3072
COPY frontend/ .
# use the pre-built interface shipped in frontend/dist when present (no heavy build)
RUN if [ -f dist/index.html ]; then echo ">>> Using pre-built interface"; \
    else (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build; fi

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 REPOXRAY_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist ./static
RUN useradd -m repoxray && mkdir -p /data && chown -R repoxray /data /app
USER repoxray
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
