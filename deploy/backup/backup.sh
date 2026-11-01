#!/bin/sh
# One backup: pg_dump, encrypted with age to BACKUP_AGE_RECIPIENT (a public key; the private key never
# touches the server), uploaded to s3://BACKUP_S3_BUCKET/BACKUP_S3_PREFIX/. Then backups older than
# BACKUP_KEEP_DAYS are deleted, which keeps the Privacy Policy's promise that deleted data leaves backups
# within 30 days.
set -eu
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET isn't set}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT isn't set}"
: "${BACKUP_S3_PREFIX:=tallyvio}"
: "${BACKUP_KEEP_DAYS:=30}"

endpoint=""
[ -n "${BACKUP_S3_ENDPOINT:-}" ] && endpoint="--endpoint-url $BACKUP_S3_ENDPOINT"
stamp=$(date -u +%Y-%m-%d_%H%M)
name="tallyvio-$stamp.dump.age"
tmp="/tmp/$name"
trap 'rm -f "$tmp"' EXIT

# Compressed custom-format dump, encrypted as it streams; nothing unencrypted is written to disk.
pg_dump -Fc | age -r "$BACKUP_AGE_RECIPIENT" > "$tmp"
# shellcheck disable=SC2086
aws s3 cp $endpoint --only-show-errors "$tmp" "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$name"
echo "Backed up $name ($(du -h "$tmp" | cut -f1))"

# Names start with the UTC date, so comparing them as text finds the old ones.
cutoff=$(date -u -d "@$(( $(date +%s) - BACKUP_KEEP_DAYS * 86400 ))" +%Y-%m-%d)
# shellcheck disable=SC2086
aws s3 ls $endpoint "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/" | while read -r _ _ _ file; do
	case "$file" in
		tallyvio-*.dump.age) ;;
		*) continue ;;
	esac
	day=$(echo "$file" | cut -c10-19)
	if [ "$day" \< "$cutoff" ]; then
		aws s3 rm $endpoint --only-show-errors "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$file"
		echo "Deleted $file (older than $BACKUP_KEEP_DAYS days)"
	fi
done
