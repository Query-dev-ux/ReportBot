#!/usr/bin/env bash
# Восстановление базы из бэкапа: scripts/restore.sh backups/reportbot_....sql.gz
# ВНИМАНИЕ: текущие данные в базе будут удалены
set -euo pipefail
cd "$(dirname "$0")/.."

file="${1:?Укажите файл бэкапа}"
read -rp "Текущая база будет перезаписана из $file. Продолжить? [y/N] " answer
[[ "$answer" == "y" ]] || exit 1

docker compose stop bot
docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
gunzip -c "$file" | docker compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose start bot
echo "Restored from $file"
