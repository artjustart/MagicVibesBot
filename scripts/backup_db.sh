#!/bin/bash
# Автоматичний бекап БД magic_vibes_bot.
# Запускається щодня з cron — див. scripts/install_cron.sh.
# Дамп зберігається в /opt/magic_vibes_bot/backups/, файли старші за 30 днів видаляються.
set -euo pipefail

PROJECT_DIR=/opt/magic_vibes_bot
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS=30

cd "$PROJECT_DIR"

# Зчитуємо креди з .env
if [ ! -f .env ]; then
    echo "[ERROR] $PROJECT_DIR/.env not found" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="$BACKUP_DIR/magic_vibes_bot_${TIMESTAMP}.sql.gz"

# pg_dump із паролем через env — і одразу стискаємо
PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --no-owner --no-privileges --clean --if-exists \
    | gzip -6 > "$FILENAME"

SIZE=$(du -h "$FILENAME" | cut -f1)
echo "$(date -Iseconds) [OK] backup created: $FILENAME ($SIZE)"

# Ротація — видаляємо старі бекапи
DELETED=$(find "$BACKUP_DIR" -name 'magic_vibes_bot_*.sql.gz' -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "$(date -Iseconds) [OK] removed $DELETED old backups (>${RETENTION_DAYS} days)"
fi
