# Deploying Tallyvio

One server runs everything in Docker: Postgres, the backend, Caddy (HTTPS and the built frontend) and a
nightly backup job. These steps use AWS Lightsail and the domain tallyvio.com; any Ubuntu 24.04 server and
domain work the same way.

## What you need

- A **Lightsail instance**: Linux, **Ubuntu 24.04**, the **2 GB** plan (the images are built on the server,
  and building the frontend needs it).
- The **domain** (tallyvio.com) and access to its DNS settings.
- A **Google OAuth client** (the same kind as for local testing; see the root `.env.example`).
- For backups: an **S3 bucket** with an access key, and an **age key pair** (made on your own computer).
- Optional: a **Tiingo API key** for prices (see [Prices](#prices-and-licensing)).

## 1. Create the server

1. Lightsail → Create instance → Linux/Unix → OS only → **Ubuntu 24.04 LTS** → the 2 GB plan. Name it
   `tallyvio`.
2. Networking → **Create static IP** and attach it to the instance.
3. Instance → Networking → IPv4 firewall: allow **HTTP (80)**, **HTTPS (443)**, and add a custom rule for
   **UDP 443** (HTTP/3). Restrict **SSH (22)** to your own IP address if you can.
4. At your domain's DNS: an **A record** for `tallyvio.com` and one for `www.tallyvio.com`, both pointing
   to the static IP. Wait until `nslookup tallyvio.com` shows it (minutes to an hour).

## 2. Set up the server

Connect with Lightsail's browser SSH or `ssh ubuntu@<static IP>` with the key Lightsail gave you, then:

```sh
git clone https://github.com/jareddalessandro/tallyvio.git   # your repository's address
cd tallyvio
sudo sh deploy/setup-server.sh
exit                                                          # log back in so docker works without sudo
```

The script installs Docker, adds 2 GB of swap, turns on automatic security updates, and sets the
firewall to SSH, HTTP and HTTPS only.

## 3. Configure

```sh
cd ~/tallyvio/deploy
sh new-env.sh      # creates .env with random database passwords, readable only by you
nano .env          # fill in the rest
```

In `.env`:

- `DOMAIN`, `ACME_EMAIL` (Let's Encrypt writes here about certificate trouble), `TZ`.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`. In Google Cloud Console, add the authorized redirect URI
  `https://tallyvio.com/api/auth/callback` to the OAuth client. While the consent screen is in **Testing**,
  only the test users you list there can sign in; switch it to **In production** when you open sign-ups.
- `ALLOWED_EMAILS`: keep it to your family and partner until you're ready for strangers.
- `OPERATOR_NAME`, `CONTACT_EMAIL`, `GOVERNING_LAW`: shown on the landing, Privacy and Terms pages.
- Prices and backups: see the sections below.

`.env` holds every secret. Don't copy it anywhere else; back it up in your password manager.

## 4. Start

The images are built on the server from this checkout. The first build takes a few minutes.

```sh
docker compose build --pull
docker compose up -d
docker compose ps            # all four running; db healthy
docker compose logs -f backend
```

Open https://tallyvio.com. The first visit can take a few seconds while Caddy gets the certificate.

## 5. Move your data in

Your local install's data belongs to its offline user, so bring it in through your account:

1. Locally: **Export & import → Download export**.
2. At https://tallyvio.com: sign in, finish setup, then **Export & import → Choose a file → Import**.
3. Delete the export file afterwards; it isn't encrypted.

## Updating

```sh
cd ~/tallyvio && git pull            # the new code and deploy files
cd deploy
docker compose exec backup backup.sh # a fresh backup first
docker compose build --pull          # rebuilds the images (--pull also fetches newer base images)
docker compose pull db               # the newest Postgres 17 patch release
docker compose up -d                 # restarts whatever changed
docker image prune -f                # optional: deletes the old images
```

Database changes apply automatically when the backend starts.

## Backups

Every night at `BACKUP_TIME`, the `backup` container dumps the database, encrypts it to your age public
key, uploads it, and deletes backups older than `BACKUP_KEEP_DAYS` (30, which the Privacy Policy
promises). The private key never touches the server, so someone who gets into the server or the bucket
can't read old backups.

**Set it up:**

1. On your own computer, install age (Windows: `winget install FiloSottile.age`) and run
   `age-keygen -o tallyvio-backup-key.txt`. Store that file in your password manager and somewhere offline:
   **without it, the backups can't be restored.** Put the public key it prints (`age1…`) in
   `BACKUP_AGE_RECIPIENT`.
2. Lightsail → Storage → **Create bucket** (the smallest plan is plenty), then on the bucket's
   Permissions tab create an **access key**. Fill in `BACKUP_S3_BUCKET`, `BACKUP_AWS_REGION` (the bucket's
   region, e.g. `us-east-1`), `BACKUP_AWS_ACCESS_KEY_ID` and `BACKUP_AWS_SECRET_ACCESS_KEY`. Amazon S3
   works the same way. Leave `BACKUP_S3_ENDPOINT` empty for either.
3. `docker compose up -d backup`, then run one now and check it appears in the bucket:
   `docker compose exec backup backup.sh`.

**Restore** (practice this once, before you need it):

```sh
# On your computer: download a backup from the bucket (Lightsail console → bucket → Objects), then
age -d -i tallyvio-backup-key.txt tallyvio-2026-11-02_0215.dump.age > restore.dump
# Copy restore.dump to the server (scp), then on the server, in ~/tallyvio/deploy:
docker compose stop backend
docker compose cp restore.dump db:/tmp/restore.dump
docker compose exec db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges /tmp/restore.dump && rm /tmp/restore.dump'
docker compose start backend
rm restore.dump
```

Lightsail's automatic snapshots (instance → Snapshots) are a good second layer; they keep 7 days, inside
the 30-day promise.

## Prices and licensing

Showing investment prices to other people is "display" or "redistribution" under every market-data
provider's terms, and free or cheap plans almost never allow it. Options:

| `PRICE_PROVIDER` | Cost | Allowed |
|---|---|---|
| `yahoo` (default) | Free, no account | Unofficial; Yahoo's terms allow personal use only, and it can break or block servers without warning |
| `tiingo` with a free or Power key | Free / about $30 a month | Your own internal or personal use; not redistribution |
| `tiingo` with a redistribution license | Quoted by Tiingo (sales@tiingo.com); their published redistribution plans start around $250 a month | Showing prices to your users |

For you and your family on your own server, a personal Tiingo key is a reasonable start. Before
opening sign-ups to the public, get a redistribution license (or a provider whose terms you've confirmed
in writing allow display to end users). Terms change, so read the current ones.

## Security checklist

- SSH by key only (Lightsail's default), port 22 limited to your IP if possible.
- `deploy/.env` readable only by you (`new-env.sh` does this); secrets nowhere else.
- `ALLOWED_EMAILS` set until the Privacy Policy and Terms have been reviewed and the details above are
  filled in.
- Automatic security updates are on (setup script). Reboot now and then for kernel updates:
  `sudo reboot` (everything restarts on its own).
- The backend isn't reachable from outside Docker; only Caddy (80/443) is. API docs are off in production.
- Requests are rate limited per visitor (sign-in, invites, uploads, and overall).

## Troubleshooting

- **Certificate errors or the site doesn't load:** check DNS points at the static IP, ports 80 and 443
  are open in the Lightsail firewall, and `docker compose logs web`.
- **"Bad gateway" (502):** the backend is starting or failed; `docker compose logs backend`.
- **Sign-in fails with redirect_uri_mismatch:** the Google client's redirect URI must be exactly
  `https://<DOMAIN>/api/auth/callback`.
- **Memory:** `docker stats` shows each container's use against its limit; `free -h` shows swap.
