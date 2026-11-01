#!/bin/sh
# Runs backup.sh once a day at BACKUP_TIME (HH:MM, in TZ). A plain loop rather than cron, so the job sees
# the container's environment.
set -eu
: "${BACKUP_TIME:=02:15}"

echo "Backups run daily at $BACKUP_TIME ($TZ). Run one now with: docker compose exec backup backup.sh"
while true; do
	now=$(date +%s)
	next=$(date -d "$(date +%Y-%m-%d) $BACKUP_TIME" +%s)
	[ "$next" -le "$now" ] && next=$((next + 86400))
	sleep $((next - now))
	backup.sh || echo "Backup failed; trying again tomorrow." >&2
done
