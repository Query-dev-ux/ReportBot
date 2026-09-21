#!/usr/bin/env bash
# Бэкап базы в backups/, хранятся последние KEEP_DAYS дней
set -euo pipefail
cd "$(dirname "$0")/.."

KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p backups
file="backups/reportbot_$(date +%Y-%m-%d_%H-%M).sql.gz"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$file"
find backups -name 'reportbot_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "Backup saved: $file"
