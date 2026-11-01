"""households, users and sharing

Every household-scoped table gets a household_id, and companies get access rows. Existing data moves into
one household owned by the automatic local user (the offline install's user), so nothing changes for an
offline install. Then row-level security policies are added (they only bind the restricted app role).

Revision ID: 9d4a1c2b7e30
Revises: c78053bf01c4
Create Date: 2026-10-31 12:00:00

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app import rls

revision: str = '9d4a1c2b7e30'
down_revision: Union[str, None] = 'c78053bf01c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that gain a household_id (month_settings too, but its primary key changes, so it's separate).
SCOPED = [t for t in rls.HOUSEHOLD_TABLES if t != "month_settings"]
# (table, old unique constraint, new columns) for names that are now unique per household.
UNIQUES = [
    ("categories", "categories_name_kind_key", ["name", "kind"]),
    ("accounts", "accounts_name_key", ["name"]),
    ("accounts", "accounts_statement_key_key", ["statement_key"]),
    ("transactions", "transactions_import_hash_key", ["import_hash"]),
    ("import_rules", "import_rules_pattern_direction_key", ["pattern", "direction"]),
    ("credit_cards", "credit_cards_name_key", ["name"]),
]


def _timestamp(name: str = "created_at", nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=nullable)


def _access_table(name: str, parent: str, fk: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(fk, sa.Integer(), sa.ForeignKey(f"{parent}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        _timestamp(),
        sa.UniqueConstraint(fk, "user_id"),
    )
    op.create_index(f"ix_{name}_{fk}", name, [fk])
    op.create_index(f"ix_{name}_user_id", name, ["user_id"])


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("google_sub", sa.String(255), unique=True),
        sa.Column("picture_url", sa.String(1000)),
        sa.Column("is_local", sa.Boolean(), server_default="false", nullable=False),
        _timestamp(),
        _timestamp("last_login_at", nullable=True),
    )
    op.alter_column("users", "last_login_at", server_default=None)
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        _timestamp(),
    )
    _access_table("household_access", "households", "household_id")
    _access_table("company_access", "companies", "company_id")

    # Everything that exists so far belongs to the offline install's user.
    conn = op.get_bind()
    user_id = conn.execute(
        sa.text("INSERT INTO users (email, name, is_local) VALUES ('local@moneysage.invalid', 'You', true) RETURNING id")
    ).scalar_one()
    household_id = conn.execute(
        sa.text("INSERT INTO households (name, timezone) VALUES ('Household', :tz) RETURNING id"),
        {"tz": os.environ.get("TZ") or "America/Phoenix"},
    ).scalar_one()
    conn.execute(
        sa.text("INSERT INTO household_access (household_id, user_id, role) VALUES (:h, :u, 'owner')"),
        {"h": household_id, "u": user_id},
    )

    for table in SCOPED + ["month_settings"]:
        op.add_column(table, sa.Column("household_id", sa.Integer(), nullable=True))
        conn.execute(sa.text(f"UPDATE {table} SET household_id = :h"), {"h": household_id})
        op.alter_column(table, "household_id", nullable=False)
        op.create_foreign_key(
            f"{table}_household_id_fkey", table, "households", ["household_id"], ["id"], ondelete="CASCADE"
        )
    for table in SCOPED:
        op.create_index(f"ix_{table}_household_id", table, ["household_id"])
    op.drop_constraint("month_settings_pkey", "month_settings", type_="primary")
    op.create_primary_key("month_settings_pkey", "month_settings", ["household_id", "month"])

    for table, old, columns in UNIQUES:
        op.drop_constraint(old, table, type_="unique")
        op.create_unique_constraint(f"{table}_household_id_{'_'.join(columns)}_key", table, ["household_id", *columns])

    # Company names only need to be unique among the companies one person can open (checked by the app).
    op.drop_constraint("companies_name_key", "companies", type_="unique")
    op.add_column("companies", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "companies_created_by_id_fkey", "companies", "users", ["created_by_id"], ["id"], ondelete="SET NULL"
    )
    conn.execute(sa.text("UPDATE companies SET created_by_id = :u"), {"u": user_id})
    conn.execute(
        sa.text("INSERT INTO company_access (company_id, user_id, role) SELECT id, :u, 'owner' FROM companies"),
        {"u": user_id},
    )

    op.add_column("price_refresh_runs", sa.Column("household_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "price_refresh_runs_household_id_fkey", "price_refresh_runs", "households", ["household_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_price_refresh_runs_household_id", "price_refresh_runs", ["household_id"])
    op.add_column(
        "price_refresh_runs",
        sa.Column("failed_tickers", postgresql.JSONB(), server_default="[]", nullable=False),
    )

    for statement in rls.statements():
        op.execute(statement)


def downgrade() -> None:
    # Only safe with a single household: names unique per household become unique again overall.
    for statement in rls.drop_statements():
        op.execute(statement)

    op.drop_column("price_refresh_runs", "failed_tickers")
    op.drop_index("ix_price_refresh_runs_household_id", "price_refresh_runs")
    op.drop_constraint("price_refresh_runs_household_id_fkey", "price_refresh_runs", type_="foreignkey")
    op.drop_column("price_refresh_runs", "household_id")

    op.drop_constraint("companies_created_by_id_fkey", "companies", type_="foreignkey")
    op.drop_column("companies", "created_by_id")
    op.create_unique_constraint("companies_name_key", "companies", ["name"])

    for table, old, columns in UNIQUES:
        op.drop_constraint(f"{table}_household_id_{'_'.join(columns)}_key", table, type_="unique")
        op.create_unique_constraint(old, table, columns)

    op.drop_constraint("month_settings_pkey", "month_settings", type_="primary")
    op.create_primary_key("month_settings_pkey", "month_settings", ["month"])
    for table in SCOPED:
        op.drop_index(f"ix_{table}_household_id", table)
    for table in SCOPED + ["month_settings"]:
        op.drop_constraint(f"{table}_household_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "household_id")

    op.drop_table("company_access")
    op.drop_table("household_access")
    op.drop_table("households")
    op.drop_table("users")
