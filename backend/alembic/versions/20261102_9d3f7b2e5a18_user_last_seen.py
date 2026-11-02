"""users.last_seen_at: when each person last used the app, for the Admin page

Revision ID: 9d3f7b2e5a18
Revises: 4a8e2c6f1b39
Create Date: 2026-11-02 15:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '9d3f7b2e5a18'
down_revision: Union[str, None] = '4a8e2c6f1b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    # Start from what's known: the last sign-in, or a session used since (GREATEST skips nulls).
    op.execute(
        "UPDATE users SET last_seen_at = GREATEST(last_login_at, "
        "(SELECT max(s.last_seen_at) FROM sessions s WHERE s.user_id = users.id))"
    )


def downgrade() -> None:
    op.drop_column('users', 'last_seen_at')
