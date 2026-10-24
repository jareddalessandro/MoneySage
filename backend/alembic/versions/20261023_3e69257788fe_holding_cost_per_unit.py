"""holding cost per unit

Revision ID: 3e69257788fe
Revises: cf2d091ba933
Create Date: 2026-10-23 15:45:01.134754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3e69257788fe'
down_revision: Union[str, None] = 'cf2d091ba933'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Store what was paid per share/coin instead of the total; convert existing totals.
    op.add_column('holdings', sa.Column('cost_per_unit', sa.Numeric(precision=20, scale=6), nullable=True))
    op.execute(
        "UPDATE holdings SET cost_per_unit = ROUND(cost_basis / quantity, 6) "
        "WHERE cost_basis IS NOT NULL AND quantity > 0"
    )
    op.drop_column('holdings', 'cost_basis')


def downgrade() -> None:
    op.add_column('holdings', sa.Column('cost_basis', sa.Numeric(precision=14, scale=2), nullable=True))
    op.execute(
        "UPDATE holdings SET cost_basis = ROUND(cost_per_unit * quantity, 2) WHERE cost_per_unit IS NOT NULL"
    )
    op.drop_column('holdings', 'cost_per_unit')
