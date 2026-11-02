#!/bin/sh
# Creates deploy/.env from .env.example with fresh random database passwords, readable only by you.
# Run once on the server, from the deploy folder:  sh new-env.sh
set -eu
cd "$(dirname "$0")"
if [ -e .env ]; then
	echo ".env already exists; not overwriting it." >&2
	exit 1
fi
secret() { openssl rand -base64 36 | tr -d '/+=\n' | cut -c1-40; }
umask 077
sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
	-e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$(secret)|" \
	.env.example > .env
echo "Created deploy/.env with new database passwords. Now fill in the rest: nano .env"
