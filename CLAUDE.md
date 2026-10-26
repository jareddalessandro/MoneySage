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

- **`models.py`:** Category, BudgetItem, Account, BalanceSnapshot, Transaction, Holding, PriceQuote, PriceRefreshRun, CreditCard, Company, CompanyMember, CompanyProduct, CompanyEntry, RevenueShare, RevenueShareMonth, StatementImport, ImportRule, MonthSetting. Enums are stored as VARCHAR (`native_enum=False`).
- **`routers/`:** one router per tab (the Investments tab is `stocks`: route `/investments`, `/stocks` redirects there) (`budget`, `transactions` for the income statement, `statements` for statement import, `balance_sheet`, `stocks`, `categories`, `credit_cards`, `companies`). There's no Dashboard: the user removed it, and `/` redirects to Budget.
- **`services/`:**
  - `budget.py`: normalizes frequencies to monthly amounts.
  - `prices.py`: yfinance fetching and refresh runs.
  - `portfolio.py`: valuation, holdings → balance-sheet sync, history.
  - `scheduler.py`: APScheduler.
  - `revenue_shares.py`: revenue-share months, totals, cost-of-revenue rule, and the payee statement.
  - `company_statements.py`: year-end statements. `documents.py`: the PDF/Excel helpers both use.
  - `statement_parser.py`: reads SoFi statement PDFs (pdfplumber). `statement_import.py`: suggestions, learned rules, saving.
- **`months.py`:** months are `"YYYY-MM"` in the API and the 1st of the month in the DB.
- **`seed.py`:** inserts the 27 default categories (incl. Credit Card Payments) when the table is empty.

**Frontend:** React 19 + TypeScript + Vite + Mantine 8 + TanStack Query + recharts 3, in `frontend/src/`.

- `pages/` has one file per tab.
- `components/common.tsx` holds the shared pieces: PageHeader, StatCard, HeroStat, SectionCard, Delta, MonthSwitcher, FilterControl, `useAppMutation`, `confirmDelete`.
- `components/StatementImport.tsx` is the upload → review → import modal.
- `api.ts` / `types.ts` are the typed client. `format.ts` holds the money and month formatters.
- `theme.ts` + `styles.css` hold the design tokens.
- Vite proxies `/api` to the backend container.

### Domain rules that aren't obvious from the code

- **Money:** `NUMERIC(14,2)` / `Decimal` on the backend. Output schemas use the `Num` serializer so values reach JSON as numbers, not strings. Quantities use `Numeric(24,8)`.
- **Signs are stored positive:** transaction amounts are positive, and category kind (income/expense) decides the sign. Liability balances are also stored positive and subtracted for net worth.
- **Unexpected items:** `is_unexpected` on a transaction puts it in the "Unexpected items" card on the Income Statement. Manual unexpected items are left out of the Transactions table (an imported line flagged unexpected stays). They're entered inline (`QuickUnexpected`, top of the card, no dialog): amount first, Tab, description, Enter (focus returns to the amount). Type and category persist between entries; expenses default to Miscellaneous, income to Other Income. The card shows no dates (the user found them clutter): new items are dated today in the current month, else the month's 1st, and the lists sort newest entry first (by id). The user logs these often, so keep it few-keystroke. The card lists Unexpected expenses and Unexpected income separately (`UnexpectedList`), each with a total of all its items, paginated 8 per page (the user often has 15-30 a month; adding one jumps back to page 1). There's deliberately no net-unexpected figure, and no budget comparison in this card (it duplicated Budget vs. actual's Unexpected items / Everything else columns).
- **Income Statement layout,** top to bottom: header (statement line with undo and the Totals-from switch under the title), one row of four compact stat cards (lg 8) with the Notes card beside them (lg 4), Unexpected items (full width: the entry row on one line, then the expense and income lists side by side from `md`), Budget vs. actual (full width), the Transactions table, then the chart of this calendar year's months (January through now; income, expenses and net bars) with running YTD income/expenses/net.
- **Month notes** (`MonthSetting.notes`, `PUT /api/income-statement/notes`, returned as `notes` on the income statement): a free-text box per month (`MonthNotes`) that autosaves 800ms after typing stops, on blur, and when switching months. A `MonthSetting` row can hold only notes (`totals_from` null means "use the default"); clearing the notes of such a row deletes it.
- **Budget vs. actual card** (`BudgetSummary`): empty until the month has a statement or regular entries (unexpected items alone don't count, since against the budget they'd read as a huge shortfall). one row each for Income and Expenses (the user removed Savings) with Budget, Actual, vs. budget, Unexpected items (the month's unexpected totals) and Everything else (vs. budget minus unexpected). The per-category table sits behind a "By category" switch, off by default and saved in localStorage (`moneysage.budget-by-category`): the user imports statements, so per-category breakdowns aren't useful to them. An earlier "Savings vs. plan" breakdown with top category drivers was rejected for the same reason.
- **Paychecks:** an income budget item becomes a paycheck when `gross_amount` is set. It then has `PaycheckDeduction` rows (all amounts per paycheck).
  - **`amount` is always take-home**, so budget totals, the surplus, and budget vs. actual on the Income Statement (bank deposits) all stay in take-home terms. Don't switch the budget to gross.
  - **Deduction stages:** type `tax` is always the tax stage (`pre_tax` is forced false). Other types are pre-tax or post-tax by the `pre_tax` flag.
  - **Waterfall:** gross − pre-tax − taxes = after-tax; after-tax − post-tax − not itemized = take-home. "Not itemized" (`unitemized`) is the remainder, which lets people enter just gross and take-home. It's negative if the deductions are over-entered (the UI warns).
  - **Summary totals:** `/api/budget/summary` returns `paycheck` (all paychecks combined) and `paycheck_items` (one per paycheck, with `paychecks_per_year`), as exact **annual** totals (amount × paychecks per year). The frontend divides by 12 for monthly, or by `paychecks_per_year` for per paycheck. Don't derive yearly from rounded monthly figures, which drifts by cents.
  - **Combining:** in the combined view, same-named lines (e.g. two earners' 401(k)) are combined. The "Income breakdown" card's selector shows each paycheck on its own.
  - **"Where gross pay goes":** the not-itemized remainder is labeled "Taxes or not itemized" (striped tax orange) when no taxes are entered, since it's mostly withholding, and "Not itemized" (striped gray) when they are. HSA/FSA and other deductions get their own solid gray segment, shown only when present.
  - **Validation (400):** deductions need a gross amount, take-home can't exceed gross, and only income categories can have either.
- **Balance snapshots:** one per (account, month). A `null` balance in `PUT /api/balance-sheet` deletes the snapshot.
- **Balance Sheet cards** (frontend, `groupTotal` in `BalanceSheet.tsx`): Cash total = checking + savings + cash subtypes. Investment total = brokerage + retirement + HSA + crypto. The investment change vs. last month only counts accounts with a balance in both months, so a newly added account doesn't read as a gain. It includes contributions, so it isn't pure market performance.
- **Balance Sheet table:**
  - Assets are split into Cash / Investments / Other assets (`ASSET_GROUPS`, same subtypes as the cards), each with a subtotal on its heading row.
  - Inputs still to fill get `.needs-entry` (primary tint) and an "Enter balance" placeholder, and a count shows by Save. That covers every active non-synced account in the current month, and in past months the ones that had a balance the month before. Future months aren't flagged.
  - The "From Investments" badge links to `/investments?account=<id>`. The Investments holdings table has an account selector driving the same `?account=` param (`unassigned` for holdings with no account), defaulting to all accounts combined. When filtered, the footer totals and allocation are computed for that account only. The top cards and charts stay portfolio-wide.
- **Net worth trend** (`/api/balance-sheet/trend`):
  - Returns one point per calendar month, from the first month with any asset balance (so debt-only history doesn't show as negative net worth) through the last recorded month, never a future one.
  - A month with nothing recorded is null. The chart bridges it with `connectNulls` and says so.
  - The net worth view's y-axis is fitted to the data (`fittedAxis` in `chartAxis.ts`: padded, with round evenly spaced ticks) rather than starting at $0, which flattened real month-to-month moves. The Assets vs. Liabilities view keeps $0, since it compares two amounts.
  - Lines are straight (`curveType="linear"`), never smoothed. A toggle switches to an Assets vs. Liabilities line view (`--series-1` / `--series-2`).
- **Synced accounts:** accounts with `sync_from_holdings` get their **current-month** snapshot overwritten from linked holdings' value on every price refresh, holding change, and current-month balance-sheet read. Past months freeze. A synced account can't be edited manually in the current month or a future month (the API returns 400). Past months stay editable so history can be typed in.
  - **Month-end capture:** the 5:30 PM ET refresh on the last day writes that day's closes, so normally the frozen month holds its month-end value. In case the app was off then, `refresh_all` calls `finalize_previous_month` after storing quotes. It revalues last month's synced snapshots that haven't been written since local midnight on the 1st, using the last close on or before the month's final day and current share counts. It runs once per snapshot (it bumps `updated_at`), never overrides a snapshot written after the month ended (e.g. a manual edit), and never creates missing months. Backfilling earlier months was considered and declined by the user.
- **Price refresh:**
  - Runs daily at 17:30 America/New_York, every day so crypto stays current.
  - On startup it catches up if the last successful run is more than 20h old.
  - yfinance often has a NaN close for today right after the market closes; `fetch_history` fills it from `fast_info["last_price"]`. Keep that.
  - Crypto price dates are UTC days.
- **Cash holdings:** `AssetType.cash` represents uninvested cash in an account (brokerage, IRA, money market sweep).
  - Stored as a `Holding` with ticker `CASH_TICKER` ("CASH"), `quantity` = dollar amount, and `cost_basis` forced to null.
  - `value_holding` values it at face value with day change 0 and no gain, so it counts toward portfolio value, allocation, and synced account balances, but not toward gains.
  - It's never fetched: `refresh_all` and `_apply` skip it, so the real stock CASH (Pathward) only matters for stock-type holdings.
  - `portfolio_history` adds it as a flat amount each day.
  - No migration was needed: enums are VARCHAR without a CHECK constraint.
- **Cost basis:** holdings store `cost_per_unit` (average price per share/coin, `Numeric(20,6)`). `Holding.cost_basis` is a derived property (quantity × cost_per_unit, rounded to the cent) used for gains and the "invested" total. The API returns both.
- **Holdings table grouping (frontend only, `groupPositions` in `Stocks.tsx`):** holdings are grouped by asset type + ticker.
  - A ticker held in several accounts shows one row with Account "Multiple", totals, and a share-weighted avg cost over the lots that have a cost. It notes "n of m accounts" if some lots lack a cost.
  - That row expands to per-account rows, which is where edit and delete live. Each account's position stays its own `Holding` row in the DB.
  - Sorting (ticker, value, allocation, gain/loss) applies to the grouped positions. Rows with no figure for the column (no price, no cost, cash for gain) sort last in both directions. The choice is saved in localStorage (`moneysage.holdings-sort`).
  - Allocation = market value ÷ the sum of all listed holdings' market values, so the rows add up to 100%.
- **Portfolio value chart:** `/api/portfolio/history?days=N` values the *current* holdings over the range. It opens on the range start itself, using the last close on or before it (it looks back 10 days past weekends and holidays). YTD asks for the days since Dec 31, so its base is last year's final close. The header shows the change and % from the first point to the last. If history doesn't reach back that far, it says "since <date>". The % includes cash in the base.
- **Tickers:** `normalize_ticker` uppercases, and crypto without `-` gets `-USD` (BTC → BTC-USD). New tickers are validated by fetching them, which returns 400 if Yahoo has no data.
- **Timezone:** the container `TZ` (default America/Phoenix, the user's zone) decides which month "today" is in.
- **Credit Card Info** (`CreditCard`, `/api/credit-cards`, `pages/CreditCards.tsx`):
  - Reference info per card: name (unique), issuer, payment site, annual fee, the month the fee posts (1-12), benefits (a JSONB list of short lines; the form takes one per line), and notes.
  - **Never add card numbers, CVVs, logins or passwords.** The page tells users not to enter them.
  - `payment_url` is normalized server-side: "chase.com" becomes `https://chase.com`, and non-web schemes (e.g. `javascript:`) are rejected. Links open in a new tab with `rel="noopener noreferrer"`.
  - It isn't linked to Balance Sheet credit card accounts yet.
- **Companies** (`Company`, `CompanyMember`, `CompanyEntry`, `/api/companies`, `pages/Companies.tsx` + `pages/Company.tsx`):
  - Businesses the household has a stake in, kept **separate from household finances**: company income and expenses don't touch the Budget, Income Statement or Balance Sheet.
  - The sidebar lists each company as its own link under Companies (`/companies/:id`). `/companies` is the overview.
  - Members hold `equity_percent` (0-100, `Numeric(7,4)`). A company's members can't total more than 100% (400 on add or edit). Under 100% is allowed, and the page shows the unassigned part.
  - Entries have a `kind`: `income`, `expense`, `contribution`, `distribution` or `funding` (see revenue-share funding below), with positive amounts.
    - Contributions are capital a member put in, not income. Distributions are money paid out to a member, not expenses. Neither affects net profit or the monthly chart.
    - Both are "member kinds" (`MEMBER_KINDS`, defined on the backend and in `types.ts`). They require `member_id`, which must belong to the same company, and the server clears `category` on them.
    - Income and expenses have a free-text `category` (the form suggests ones already used), and the server clears `member_id` on them.
  - A member with contributions or distributions can't be deleted (409). Deleting a company deletes its members, products, revenue shares and entries.
  - **Products** (`CompanyProduct`, optional, e.g. each app): income and expense entries can carry `product_id` (cleared on member kinds; must be the same company's). A product used by entries or a revenue share can't be deleted (409). The summary's `products` has one row per product (income, cost of revenue, other expenses, net) plus "No product" when anything is untagged; it's empty without products.
  - **Revenue shares** (`RevenueShare`): agreements to pay a non-member a percentage of revenue (the user's cases: an investor gets 10% of one app's revenue after platform fees, forever; a sales consultant gets 20% of revenue from customers he refers). They're expenses, never distributions.
    - `basis="income"`: the rate applies to recorded income between the start and end dates (one product's if `product_id` is set, else the whole company's), less expenses in `deduct_categories` (platform fees). The user records income through Stripe/app stores, and "gross" in their contracts means after platform fees.
    - `basis="reported"`: the rate applies to revenue entered per month (`RevenueShareMonth`, `PUT .../months`; null clears a month). Used because referred-customer revenue isn't tagged per entry (the user declined per-customer/referral tagging). `deduct_categories` is cleared for this basis. Finished months with nothing entered are listed in `missing_months`.
    - Each month: base = max(revenue − fees, 0), earned = base × rate rounded half up to the cent. Payments are expense entries with `revenue_share_id` (only expenses keep it). Due = everything earned − everything paid through today; negative means paid ahead. An agreement with payments can't be deleted (409). No cap field: the user's deals don't have one.
    - **Funding** (`kind="funding"`, requires `revenue_share_id`; the server clears category, product and member): money a payee paid the company for their share. The user's investor sends money that the LLC uses to pay its data provider, and the user chose to treat it as a **liability for the sale of future revenue, repaid as royalty payments are remitted**, not income.
      - `revenue_shares.repayments()` allocates per agreement in date order (funding before payments on the same day): each payment repays what's still owed, and only the rest is an expense. Funding after the balance hit zero starts a new balance; earlier payments stay expenses.
      - Everywhere profit is computed (company list, summary incl. monthly chart, cost of revenue, products, statements) uses `expensed()` = amount − repaid part. Revenue-share earned/paid/due is unchanged: payments are still payments to the payee. Funding is never income, so it never enters a share's base.
      - The summary has `funding_received`/`funding_repaid` for the year, entries carry `funding_repaid`, and agreements have `funding_received`/`funding_repaid`/`funding_outstanding` (all time). Statements add a "Revenue-share funding" roll-forward (beginning, received, repaid, owed) and funding lines in the cash summary; the payee statement adds a Funding section when they've funded anything.
    - **Cost of revenue** = expenses linked to a revenue share, or in any agreement's payment `category` or `deduct_categories` (case-insensitive). It's part of expenses (`summary.cost_of_revenue`), and the statements split it out with a gross profit line.
    - **Payee statement** (`GET .../revenue-shares/{id}/statement?month=YYYY-MM&format=pdf|xlsx`): the month's revenue, fees, base and share, the account (opening balance, earned, payments, balance due), payments listed, and the year to date by month. It never includes the agreement's private `notes`. The current month runs through today; future months and months before the start return 400. The user plans to send these monthly.
  - `/summary?year=` returns the year's totals, 12 monthly income/expense points, and per-member figures:
    - contributions and distributions, for that year and all time
    - "share of profit" = the year's net × equity %, a paper entitlement, not money paid out
  - The Owners table shows contributed and distributed for the year, share of profit, and "net invested" (all-time contributions − all-time distributions, which can go negative).
  - **Company page layout** (`Company.tsx`), top to bottom:
    - stat cards: a loss shows "Spent $X for every $1 earned" instead of a negative margin
    - income vs. expenses chart (`zeroAxis`: $0 up to round steps)
    - expenses by category (`ExpenseDonut`, computed from the year's entries using the expensed amount, colored by rank in palette order, "Uncategorized" gray)
    - Entries: full length, no inner scroll. Date sorts both ways (saved in localStorage), Type badges have a dot per kind (`KIND_COLORS`), and a Total row follows the filters ("All" shows income minus expenses)
    - revenue shares and products, only when the company has them; otherwise a compact "Optional tracking" card sits beside Owners
  - **Companies overview:** when there's more than one company, a "Share of profit by owner" table (each company's net × equity, members matched by name) replaces summed totals, which would mix stakes held by different people. Tiles always reserve a description line so their figures line up.
  - **Year-end statements** (`services/company_statements.py`, `GET /api/companies/{id}/statements?year=&format=pdf|xlsx`, the Export menu on the company page):
    - Cash basis, built only from recorded entries. Contents:
      - income statement (by category, largest first, "Uncategorized" last), with cost of revenue and gross profit when there is any
      - statement of members' capital: beginning + contributions + share of profit − distributions = ending
      - results by product (when the company has products) and revenue shares (earned and paid in the period, due at its end)
      - revenue-share funding (the liability roll-forward), when any was received
      - cash summary
      - transaction detail
    - Beginning capital and beginning cash come from all entries before Jan 1. Profit is allocated by **current** ownership % for every year, since ownership history isn't kept; the statements say so. Profit not allocated because ownership is under 100% is noted.
    - The current year is labeled year to date (through today), and its file name says "YTD".
    - The PDF uses reportlab. User text goes through `escape()` because Paragraph parses markup. The Excel file uses openpyxl and has four sheets, with SUM formulas for totals.
    - Both libraries are pinned in `requirements.txt`. After changing requirements, run `docker compose up -d --build backend`.
- **Statement import** (`/api/statements`, `StatementImport.tsx`): the user's main way to fill the Income Statement. They upload a monthly SoFi PDF (checking + savings + Vaults in one file), review it, and import.
  - **Parsing:** SoFi's text layer places columns separately, so plain text extraction scrambles rows. `statement_parser` groups words into lines by position and splits columns at the DATE/TYPE/DESCRIPTION/AMOUNT header's x positions. Each account's rows must satisfy beginning + rows = ending; the review shows "Off by $X" otherwise. Only SoFi is supported (400 for other PDFs). The PDF is never stored.
  - **Two steps:** `POST /preview` (multipart) parses and suggests, saving nothing. `POST /statements` saves the reviewed rows. `DELETE /statements/{id}` undoes an import (its transactions cascade; Balance Sheet balances stay).
  - **Suggestions,** in order: a remembered `ImportRule` (normalized description + direction "in"/"out"), then transfers between the statement's own accounts ("To Joint Savings", "From Joint checking balance", Vault moves) are skipped, card payments go to the `is_card_payments` category, PAYROLL → Salary, interest → Interest & Dividends, MTG/HOA → Housing, then Other Income / Miscellaneous marked "Not recognized". Every choice at import is saved as a rule, and recategorizing an imported transaction later updates its rule.
  - **Dedup:** each row's key (`import_hash`) is a hash of bank, account, section, SoFi transaction ID, date and amount. Skipped rows' keys are kept in `StatementImport.skipped_keys`, so re-uploading a statement flags every line as already imported (409 if nothing is new).
  - **Accounts:** each statement account maps to a Balance Sheet account (remembered in `Account.statement_key`, first guessed by subtype + bank name). By default the import writes the ending balances for the statement month (savings' ending includes its Vaults). Synced accounts can't be picked.
  - Imported transactions have `source="statement"`, the mapped `account_id`, and `statement_import_id`. Positive rows need income categories, negative rows expense categories.
- **Totals source per month** (`month_sources` in `transactions.py`, `MonthSetting`, `PUT /api/income-statement/totals-from`): a month with imported rows totals them by default ("Statement"), and manual entries (unexpected or not) then only explain the month; they're shown with "Not in totals". The user can switch a month to "Manual entries", which ignores the imported rows. A month without imported rows always uses manual entries. The trend chart follows each month's choice. Unexpected totals count manual unexpected items in either mode.
- **Card-paid budget items:** `BudgetItem.paid_by_card` (expenses only; forced false otherwise). In a statement month, Budget vs. actual moves those items' budget into the Credit Card Payments line (`card_items` lists them), since the statement only sees card payments. Manual months compare each category as before. The card category is the one with `is_card_payments` (added by migration on existing installs, by the seed on fresh ones).
- **`examples/`** holds the user's real statements for parser work. It's gitignored; never commit them or copy them into tests (tests build a synthetic SoFi-layout PDF with reportlab).

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
- **Glass:**
  - Modals use rgba(29,32,38,0.7) with a 24px backdrop blur and the ambient shadow `0 12px 32px rgba(4,6,10,.4)`.
  - Menus, selects and popovers keep the blur but are 94% opaque, because at 70% the text of the form behind them showed through.
  - The sticky modal header has its own near-opaque fill.
  - Chart hover popups (every Mantine chart uses `.mantine-ChartTooltip-tooltip`) are 97% opaque. Overlays drawn on a chart, like the donut's center total, go *before* the chart in the DOM so the tooltip paints over them.
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
  - Paired series use `--series-1` #009dc1 (income/values) and `--series-2` #d9762b (expenses). Income/expense bar charts (Income Statement, company pages) are the exception: the user asked for income green, expenses red, net blue (`--chart-income/expenses/net` = the delta colors and `--series-1`); the legend and fixed bar order carry it for color-blind viewers. `SERIES_ORDER` keeps legends Income, Expenses, Net. This pair passed the palette validator on #272a31. Primary itself is too light (OKLCH L 0.82) to sit beside another hue, so don't swap it in.
  - "Where gross pay goes" uses take-home `--series-1`, then `--split-retirement` #8f74e6, `--split-tax` #d9762b, `--split-insurance` #cc5f9a, and the neutral `--split-other` #6f7a80. This set passed the validator on all pairs. Blue and pink are a borderline 7.0 for deuteranopia, which is allowed because every segment is labeled with its amount.
  - **Category colors:**
    - Each category stores a `color` key (`CategoryColor`: blue, orange, teal, violet, gold, pink, green, plum, gray), mapped to `--cat-*` hexes in `styles.css` via `components/CategoryColor.tsx`.
    - The eight hues pass the validator for adjacent pairs only. All-pairs separation is impossible at eight, so a category's color is always shown with its name (badge dot, legend row). Never color alone.
    - New categories get the least-used color for their kind (`next_color`), and users recolor on the Categories page.
    - Badges are neutral gray with a colored dot, so text stays in text color.
  - **Budget expenses donut** (`ExpenseDonut`): largest first, clockwise from 12 o'clock, 2° gaps, total in the center, and a legend with amount and share. More than 8 categories fold the smallest into a gray "Other".
  - `--delta-up` = `secondary` #40e56c and `--delta-down` = `tertiary_container` #ff5353 are for gains/losses and over-budget status only, never series colors.
  - Solid recessive gridlines: `gridAxis="x" strokeDasharray="0"`. Legends keep Income before Expenses via `SERIES_ORDER`.
- **Mobile** (phones are below Mantine's `xs`, 36em / 576px; rules live at the end of `styles.css`):
  - Modals are full screen. Side-by-side fields in a modal (`Group grow`) stack. Text inputs are 16px so iOS doesn't zoom in on focus.
  - Stat-card grids are two columns (`cols={{ base: 2, ... }}`), with smaller numbers and padding from `StatCard`/`SectionCard` themselves. Page-header actions get a full-width row.
  - Tables don't scroll sideways on phones. Mark secondary columns `hide-xs` and repeat their key details under the row's name in a `show-xs` element, and give the `Table.ScrollContainer` `className="phone-fit"` to drop its desktop `minWidth` there. Keep footer cells aligned: split a `colSpan` so the hidden part is its own `hide-xs` cell. Cell padding shrinks, headers wrap, edit/delete icons stack, and long words break (never `.num` text).
  - Filters with more than ~4 options use `FilterControl` (segmented on desktop, a dropdown on phones).
- Recharts must stay on 3.x: Mantine charts 8 wraps series in Fragments, which recharts 2 doesn't render.
