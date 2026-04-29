#!/bin/bash
# Одноразовий скрипт: ставить крон для щоденного бекапу о 04:00 (Київський час сервера).
# Ідемпотентний — повторний запуск нічого не зламає.
set -euo pipefail

SCRIPT_PATH=/opt/magic_vibes_bot/scripts/backup_db.sh
LOG_PATH=/var/log/magic_vibes_backup.log
CRON_LINE="0 4 * * * $SCRIPT_PATH >> $LOG_PATH 2>&1"
CRON_TAG="# magic-vibes-backup"

chmod +x "$SCRIPT_PATH"

# Створюємо файл логу і даємо права
touch "$LOG_PATH"
chmod 644 "$LOG_PATH"

# Видаляємо старий запис (якщо є) і додаємо свіжий
( crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true ; echo "$CRON_LINE $CRON_TAG" ) | crontab -

echo "✅ Крон встановлено:"
crontab -l | grep "$CRON_TAG"
echo
echo "📂 Лог:  $LOG_PATH"
echo "🕒 Час: щодня о 04:00 (за часом сервера VPS)"
echo
echo "Перевірити крон:    crontab -l"
echo "Подивитись лог:     tail -50 $LOG_PATH"
echo "Запустити вручну:   $SCRIPT_PATH"
