"""invites to share a household or company

Revision ID: 7b3c9e1f4a26
Revises: 5e2f8a7c1d94
Create Date: 2026-11-01 15:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7b3c9e1f4a26'
down_revision: Union[str, None] = '5e2f8a7c1d94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="CASCADE")),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("target_name", sa.String(200), nullable=False),
        sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("(household_id IS NULL) <> (company_id IS NULL)", name="invites_one_target"),
        sa.UniqueConstraint("email", "household_id"),
        sa.UniqueConstraint("email", "company_id"),
    )
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_household_id", "invites", ["household_id"])
    op.create_index("ix_invites_company_id", "invites", ["company_id"])


def downgrade() -> None:
    op.drop_table("invites")
