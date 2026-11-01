"""the app is now Tallyvio: the offline user's placeholder address follows

Revision ID: 1f6b3d8a2c57
Revises: 8c4d2a6e9f13
Create Date: 2026-11-02 09:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '1f6b3d8a2c57'
down_revision: Union[str, None] = '8c4d2a6e9f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET email = 'local@tallyvio.invalid' WHERE is_local AND email = 'local@moneysage.invalid'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE users SET email = 'local@moneysage.invalid' WHERE is_local AND email = 'local@tallyvio.invalid'"))
