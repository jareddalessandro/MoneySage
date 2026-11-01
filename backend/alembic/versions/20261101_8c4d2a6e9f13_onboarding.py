"""first-time setup and terms acceptance

Revision ID: 8c4d2a6e9f13
Revises: 7b3c9e1f4a26
Create Date: 2026-11-01 18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8c4d2a6e9f13'
down_revision: Union[str, None] = '7b3c9e1f4a26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarded_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("terms_version", sa.String(20)))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
    op.drop_column("users", "onboarded_at")
