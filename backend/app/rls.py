"""Postgres row-level security: a second wall behind the app's own household and company checks.

Every request already filters by the household or company it's working in (app.tenancy). These policies
make the database enforce the same thing, so a query that forgets its filter returns nothing from anyone
else rather than leaking it. Reads need any role; writes need owner or editor.

They apply only to the restricted app role (settings.app_db_password), never to the table owner, so
migrations and an offline install are unaffected. The migration that introduced households runs
`statements()` as it stood then; change policies in a new migration, not by editing this after the fact.
"""

# Tables with a household_id column.
HOUSEHOLD_TABLES = [
    "categories",
    "budget_items",
    "accounts",
    "transactions",
    "statement_imports",
    "import_rules",
    "month_settings",
    "holdings",
    "credit_cards",
]
# Tables with a company_id column.
COMPANY_TABLES = ["company_members", "company_products", "revenue_shares", "company_entries"]
# Tables scoped through their parent row: table -> (parent table, foreign key column).
CHILD_TABLES = {
    "paycheck_deductions": ("budget_items", "budget_item_id"),
    "balance_snapshots": ("accounts", "account_id"),
    "revenue_share_months": ("revenue_shares", "revenue_share_id"),
}

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION app_user_id() RETURNS integer LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.user_id', true), '')::integer $$""",
    """CREATE OR REPLACE FUNCTION app_bypass_rls() RETURNS boolean LANGUAGE sql STABLE AS
    $$ SELECT coalesce(current_setting('app.bypass_rls', true), '') = 'on' $$""",
    """CREATE OR REPLACE FUNCTION app_household_ok(hid integer, write boolean) RETURNS boolean LANGUAGE sql STABLE AS
    $$ SELECT app_bypass_rls() OR EXISTS (
        SELECT 1 FROM household_access a
        WHERE a.household_id = hid AND a.user_id = app_user_id() AND (NOT write OR a.role <> 'viewer')
    ) $$""",
    """CREATE OR REPLACE FUNCTION app_company_ok(cid integer, write boolean) RETURNS boolean LANGUAGE sql STABLE AS
    $$ SELECT app_bypass_rls() OR EXISTS (
        SELECT 1 FROM company_access a
        WHERE a.company_id = cid AND a.user_id = app_user_id() AND (NOT write OR a.role <> 'viewer')
    ) $$""",
]


def _policies(table: str, check: str) -> list[str]:
    """Read/insert/update/delete policies; `check` is an expression with {write} for true/false."""
    read, write = check.format(write="false"), check.format(write="true")
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_read ON {table} FOR SELECT USING ({read})",
        f"CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK ({write})",
        f"CREATE POLICY tenant_update ON {table} FOR UPDATE USING ({write}) WITH CHECK ({write})",
        f"CREATE POLICY tenant_delete ON {table} FOR DELETE USING ({write})",
    ]


def _parent_check(parent: str) -> str:
    if parent in HOUSEHOLD_TABLES:
        return "app_household_ok(p.household_id, {write})"
    return "app_company_ok(p.company_id, {write})"


def statements() -> list[str]:
    sql = list(FUNCTIONS)
    for table in HOUSEHOLD_TABLES:
        sql += _policies(table, "app_household_ok(household_id, {write})")
    for table in COMPANY_TABLES:
        sql += _policies(table, "app_company_ok(company_id, {write})")
    for table, (parent, fk) in CHILD_TABLES.items():
        sql += _policies(table, f"EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {table}.{fk} AND {_parent_check(parent)})")
    # A company's creator can read it back before their access row exists (INSERT ... RETURNING).
    sql += [
        "ALTER TABLE companies ENABLE ROW LEVEL SECURITY",
        "CREATE POLICY tenant_read ON companies FOR SELECT "
        "USING (app_company_ok(id, false) OR created_by_id = app_user_id())",
        "CREATE POLICY tenant_insert ON companies FOR INSERT "
        "WITH CHECK (app_bypass_rls() OR created_by_id = app_user_id())",
        "CREATE POLICY tenant_update ON companies FOR UPDATE "
        "USING (app_company_ok(id, true)) WITH CHECK (app_company_ok(id, true))",
        "CREATE POLICY tenant_delete ON companies FOR DELETE USING (app_company_ok(id, true))",
    ]
    return sql


def drop_statements() -> list[str]:
    tables = HOUSEHOLD_TABLES + COMPANY_TABLES + list(CHILD_TABLES) + ["companies"]
    sql = []
    for table in tables:
        sql += [f"DROP POLICY IF EXISTS {p} ON {table}" for p in ("tenant_read", "tenant_insert", "tenant_update", "tenant_delete")]
        sql.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    sql += [
        "DROP FUNCTION IF EXISTS app_company_ok(integer, boolean)",
        "DROP FUNCTION IF EXISTS app_household_ok(integer, boolean)",
        "DROP FUNCTION IF EXISTS app_bypass_rls()",
        "DROP FUNCTION IF EXISTS app_user_id()",
    ]
    return sql
