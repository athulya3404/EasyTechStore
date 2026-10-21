#!/usr/bin/env bash
# ==============================================================================
# EasyTech Store - Automated Expired Order Cleanup Scheduler (Linux / Crontab)
# Recommended Crontab configuration:
# */10 * * * * /path/to/EasyTechStore/scripts/schedule_cleanup.sh >> /var/log/easytech_cleanup.log 2>&1
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "[$(date -u +"%Y-%m-%d %H:%M:%SZ")] Executing expired order cleanup..."
python manage.py cleanup_expired_orders
echo "[$(date -u +"%Y-%m-%d %H:%M:%SZ")] Cleanup sweep completed."
