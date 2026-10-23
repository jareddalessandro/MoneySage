# MoneySage

A family finance tracker that runs locally in Docker. Single household, no login.

## Rules

- **Never commit directly to `main`.** Before committing, check `git branch --show-current`. If you're on `main`, create a branch first (`git checkout -b <short-topic>`), commit there, push the branch, and open a PR (or tell the user it's ready to merge). Never push to `main`, merge into it, or rebase it unless the user explicitly asks for that specific action.
- Commit or push only when the user asks.
- Follow `DESIGN.md` for all UI work (details below).
- Don't touch the user's data. The main DB (`moneysage`) holds real family finances. Use the `moneysage_test` DB (tests create it) for experiments. If you add demo data to the main DB to look at the UI, check it was empty first and delete exactly what you added afterwards.
- Pushing to GitHub: plain HTTPS fails with "SSL certificate problem: unable to get local issuer certificate" (something on this machine intercepts TLS). Use `git -c http.sslBackend=schannel push`, unless the user has set that in config.

## Running

```powershell
docker compose up -d                      # app http://localhost:5180, API docs http://localhost:8100/docs
docker compose exec backend python -m pytest
docker compose exec frontend npx tsc --noEmit
```

- **Ports:** 5180 (frontend), 8100 (backend), 5433 (Postgres). The user's other project (nominalfactor) already uses 5173, 8000 and 5432, so don't move to those. They're configurable in `.env` and bound to 127.0.0.1.
- **Hot reload:** source is bind-mounted, so code changes reload on their own. Windows bind mounts need polling (`WATCHFILES_FORCE_POLLING`, Vite `usePolling`).
- **Frontend dependencies:** `node_modules` lives in an anonymous volume. After changing `frontend/package.json`, either run `npm install` inside the container or `docker compose up -d --build --renew-anon-volumes frontend`. Pin exact versions.
- **Migrations:** after editing `backend/app/models.py`, run `docker compose exec backend alembic revision --autogenerate -m "..."` and review the file. Migrations apply on backend start (`alembic upgrade head` in the Dockerfile CMD).
- **Data volume:** `moneysage_pgdata`. **`docker compose down -v` deletes it**, so never run it. Backups: `scripts/backup.ps1` / `scripts/restore.ps1`.

## Architecture

**Backend:** FastAPI + SQLAlchemy 2 + Alembic + psycopg 3, Python 3.12, in `backend/app/`.

- **`models.py`:** Category, BudgetItem, Account, BalanceSnapshot, Transaction, Holding, PriceQuote, PriceRefreshRun. Enums are stored as VARCHAR (`native_enum=False`).
- **`routers/`:** one router per tab (`budget`, `transactions` for the income statement, `balance_sheet`, `stocks`, `categories`, `dashboard`).
- **`services/`:**
  - `budget.py`: normalizes frequencies to monthly amounts.
  - `prices.py`: yfinance fetching and refresh runs.
  - `portfolio.py`: valuation, holdings → balance-sheet sync, history.
  - `scheduler.py`: APScheduler.
- **`months.py`:** months are `"YYYY-MM"` in the API and the 1st of the month in the DB.
- **`seed.py`:** inserts the 26 default categories when the table is empty.

**Frontend:** React 19 + TypeScript + Vite + Mantine 8 + TanStack Query + recharts 3, in `frontend/src/`.

- `pages/` has one file per tab.
- `components/common.tsx` holds the shared pieces: PageHeader, StatCard, HeroStat, SectionCard, Delta, MonthSwitcher, `useAppMutation`, `confirmDelete`.
- `api.ts` / `types.ts` are the typed client. `format.ts` holds the money and month formatters.
- `theme.ts` + `styles.css` hold the design tokens.
- Vite proxies `/api` to the backend container.

### Domain rules that aren't obvious from the code

- **Money:** `NUMERIC(14,2)` / `Decimal` on the backend. Output schemas use the `Num` serializer so values reach JSON as numbers, not strings. Quantities use `Numeric(24,8)`.
- **Signs are stored positive:** transaction amounts are positive, and category kind (income/expense) decides the sign. Liability balances are also stored positive and subtracted for net worth.
- **Unexpected items:** `is_unexpected` on a transaction puts it in the "Unexpected items" card on the Income Statement.
- **Balance snapshots:** one per (account, month). A `null` balance in `PUT /api/balance-sheet` deletes the snapshot.
- **Synced accounts:** accounts with `sync_from_holdings` get their **current-month** snapshot overwritten from linked holdings' value on every price refresh, holding change, and current-month balance-sheet read. Past months freeze. A synced account can't be edited manually in the current month (the API returns 400).
- **Price refresh:**
  - Runs daily at 17:30 America/New_York, every day so crypto stays current.
  - On startup it catches up if the last successful run is more than 20h old.
  - yfinance often has a NaN close for today right after the market closes; `fetch_history` fills it from `fast_info["last_price"]`. Keep that.
  - Crypto price dates are UTC days.
- **Tickers:** `normalize_ticker` uppercases, and crypto without `-` gets `-USD` (BTC → BTC-USD). New tickers are validated by fetching them, which returns 400 if Yahoo has no data.
- **Timezone:** the container `TZ` (default America/Phoenix, the user's zone) decides which month "today" is in.
- **Statement import (planned, not built):** the user wants to upload checking/savings statements and have them parsed into transactions. `Transaction` already has `account_id`, `source` and `import_hash` (unique) for this. Don't build it until the user asks.

### Tests

- `backend/tests/` run against the `moneysage_test` DB, which conftest creates and resets.
- The scheduler is disabled (`ENABLE_SCHEDULER=false`) and `fetch_history` is monkeypatched, so there's no network.
- Add tests alongside backend changes.

## Design system

`DESIGN.md` ("The Quantitative Archive") is the source of truth for the UI. It's implemented in `frontend/src/theme.ts` (Mantine theme + `cssVariablesResolver`) and `frontend/src/styles.css` (CSS tokens + component overrides). Keep the two files' tokens in sync.

- **Dark only.** `MantineProvider` uses `forceColorScheme="dark"`, so there's no light-mode toggle. Don't add light-mode styles unless asked.
- **Surfaces (layering, no borders):**
  - Page: `surface` #10131a.
  - Sidebar: `surface_container_low` #191c22.
  - Cards: `surface_container_high` #272a31.
  - Hover, table group rows and table totals: `surface_container_highest` #32353c.
- **No-line rule:**
  - No 1px borders or dividers for sectioning or between list or table rows. Separate them with a tone change, spacing, or hover (`.list-row`, `withRowBorders: false` by default).
  - Input borders use `outline_variant`. Floating panels may use a 15% ghost border.
- **Glass:** modals, popovers, menus, combobox dropdowns and chart tooltips use rgba(29,32,38,0.7) with a 24px backdrop blur and the ambient shadow `0 12px 32px rgba(4,6,10,.4)`.
- **Buttons:**
  - `<Button>` defaults to `variant="gradient"`: primary #4cd6ff → primary_container #009dc1 at 135°, bold dark `on_primary` text, `xl` radius. Use it for the page's main CTA.
  - `variant="default"` is the ghost secondary style. Destructive confirms use `color="red" variant="filled"`.
- **Type:**
  - Manrope (`.headline`, Mantine headings) for titles and big numbers; Inter for everything else. Both are bundled via `@fontsource-variable`, so they work offline.
  - Metadata labels and table headers use `.label-sm` style: 0.6875rem, uppercase, 0.1rem tracking, dimmed.
  - Page titles are 1.75rem. Stat values are Manrope 800 at 1.75rem. A page may have one `HeroStat` at display size.
- **Spacing:** `mb="xl"` between major page sections and `gutter="lg"` for grids. Cards are padded 1.1rem.
- **Charts** (also follow the dataviz rules: one axis, legends for 2+ series, deltas with an arrow and sign, never color alone):
  - Single-series trend lines and areas use `var(--trend)` (= primary #4cd6ff) with `fillOpacity={0.2}`.
  - Paired series use `--series-1` #009dc1 (income/values) and `--series-2` #d9762b (expenses). This pair passed the palette validator on #272a31. Primary itself is too light (OKLCH L 0.82) to sit beside another hue, so don't swap it in.
  - `--delta-up` = `secondary` #40e56c and `--delta-down` = `tertiary_container` #ff5353 are for gains/losses and over-budget status only, never series colors.
  - Solid recessive gridlines: `gridAxis="x" strokeDasharray="0"`. Legends keep Income before Expenses via `SERIES_ORDER`.
- Recharts must stay on 3.x: Mantine charts 8 wraps series in Fragments, which recharts 2 doesn't render.
