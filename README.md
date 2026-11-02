# Tallyvio

A family finance tracker: budget, income statement, balance sheet, investments, and the companies you own a piece of. Run it on your own computer with no login, or host it with Google sign-in and sharing (see [Hosting](#hosting)).

**Stack:** React + TypeScript (Vite, Mantine) · FastAPI · PostgreSQL · Docker Compose

## Running it

Requires Docker Desktop.

```powershell
docker compose up -d          # start (first run builds the images)
docker compose down           # stop (your data is kept)
docker compose logs -f backend   # watch backend logs
```

| What | URL |
|---|---|
| App | http://localhost:5180 |
| API docs | http://localhost:8100/docs |
| Postgres | `localhost:5433` (user/password/db: `tallyvio`) |

Everything is bound to `127.0.0.1`, so it's only reachable from this computer. By default (`AUTH_MODE=none`) there's no login: one automatic user owns everything.

## Tabs

- **Budget** holds expected income and expenses at any frequency (weekly, biweekly, monthly, yearly…), normalized to a monthly amount, including paychecks broken down from gross to take-home.
- **Income Statement** holds the month's transactions, imported from a bank statement PDF (SoFi) or entered by hand, with unexpected items, notes, and budget vs. actual.
- **Balance Sheet** records month-end balances for each account and debt, with net worth over time. **Copy from last month** fills in balances that haven't changed. Accounts that sync from Investments are valued automatically from their holdings.
- **Investments** covers stocks, ETFs, crypto (`BTC` is saved as `BTC-USD`) and cash, with gains, allocation and history.
- **Credit Card Info** keeps each card's payment site, benefits and annual fee (never card numbers).
- **Companies** tracks businesses you have a stake in: owners, income and expenses, revenue shares, and year-end statements.
- **Categories** lets you add, rename, recolor, or archive categories.
- **Export & import** downloads everything to a file, or brings in a file from another Tallyvio.
- **Sharing** (with sign-in only) shares your household with family and each company with its partners, separately.

### Price refresh

Prices refresh automatically **every day at 5:30 PM Eastern** (after the US market close; daily rather than weekdays so crypto stays current). If the computer was off at that time, the backend catches up when it next starts. You can also click **Refresh prices** on the Investments tab at any time.

During each refresh, accounts set to sync from Investments get their **current month** balance updated. Earlier months keep the last value recorded in that month.

Prices come from Yahoo Finance (`PRICE_PROVIDER=yahoo`, no account needed, personal use) or Tiingo (`PRICE_PROVIDER=tiingo` with `TIINGO_API_KEY`). See `.env.example`.

## Backups

Your data lives in the Docker volume `tallyvio_pgdata`. It survives restarts and rebuilds, but **`docker compose down -v` deletes it.** Back up regularly:

```powershell
.\scripts\backup.ps1                                          # writes backups\tallyvio-<date>.dump
.\scripts\restore.ps1 backups\tallyvio-2026-10-22_1700.dump  # replaces ALL current data
```

If PowerShell blocks the scripts, run them with `powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1`. Copy the `backups` folder somewhere off this machine (cloud drive, USB) now and then.

## Configuration

Copy `.env.example` to `.env` to change ports, the database password, the refresh time, or the timezone. `TZ` decides which month "today" falls in. It defaults to `America/Phoenix`.

### Using it from your phone (same Wi-Fi)

With `AUTH_MODE=none` the app has no login, so only do this on a home network you trust. (Google sign-in can't work over a LAN address; it needs `localhost` or a real domain.)

1. Set `FRONTEND_BIND=0.0.0.0` in `.env` and run `docker compose up -d frontend`. Only the frontend opens up: it forwards `/api` to the backend itself, so the API and database stay local.
2. Allow the port through Windows Firewall on private networks only. Run this in an **admin** PowerShell:
   ```powershell
   New-NetFirewallRule -DisplayName "Tallyvio (LAN)" -Direction Inbound -Protocol TCP -LocalPort 5180 -Action Allow -Profile Private
   ```
   Your Wi-Fi must be set to **Private** (Settings → Network & internet → Wi-Fi → your network). On a Public network the rule doesn't apply, which is what you want away from home.
3. Find the PC's IPv4 address with `ipconfig` (the Wi-Fi adapter) and open `http://<that address>:5180` on your phone. A DHCP reservation on your router keeps the address from changing.

## Hosting

[`deploy/README.md`](deploy/README.md) walks through running Tallyvio on a server (AWS Lightsail) with HTTPS, Google sign-in, nightly encrypted backups, and images built by GitHub Actions.

## Development

Source folders are mounted into the containers, so code changes hot-reload. The UI follows the design system in [`DESIGN.md`](DESIGN.md) (tokens live in `frontend/src/theme.ts` and `frontend/src/styles.css`). [`CLAUDE.md`](CLAUDE.md) has project notes and rules for Claude Code, including: never commit directly to `main`.

```powershell
docker compose exec backend python -m pytest            # backend tests (use a separate tallyvio_test DB)
docker compose exec frontend npx tsc --noEmit           # frontend type check

# after changing backend/app/models.py:
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose restart backend                          # applies migrations on startup
```

After changing `frontend/package.json`, rebuild with `docker compose up -d --build --renew-anon-volumes frontend`.

### Layout

```
backend/
  app/models.py        database tables
  app/routers/         API endpoints per tab
  app/services/        budget math, price fetching, portfolio valuation, scheduler
  alembic/versions/    database migrations
  tests/
frontend/src/
  pages/               one file per tab
  components/          shared UI pieces
  api.ts, types.ts     API client and types
scripts/               backup / restore (local install)
deploy/                production: compose file, Caddy, backups, server setup
```
