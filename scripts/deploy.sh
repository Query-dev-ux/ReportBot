#!/usr/bin/env bash
# Обновление бота: подтянуть код из GitHub и пересобрать контейнер
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only
docker compose up -d --build
docker image prune -f
docker compose ps
