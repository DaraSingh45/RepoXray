#!/usr/bin/env bash
# RepoXray one-command start for macOS / Linux (Docker). Opens the browser when ready.
set -e
cd "$(dirname "$0")"
URL="http://localhost:3000"
command -v docker >/dev/null || { echo "Docker is not installed: https://www.docker.com/products/docker-desktop/"; exit 1; }
if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker..."; (open -a Docker 2>/dev/null || true)
  for i in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
fi
[ -f .env ] || cp .env.example .env
echo "Building and starting RepoXray (first run takes 5-10 minutes)..."
docker compose up -d --build
echo "Waiting for RepoXray..."
for i in $(seq 1 90); do curl -sf -m 2 "$URL/api/health" >/dev/null && break; sleep 2; done
curl -sf -m 2 "$URL/api/health" >/dev/null || { docker compose logs --tail 40 api; exit 1; }
echo "RepoXray is running at $URL"
if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1; fi
echo "Stop it with: docker compose stop"
