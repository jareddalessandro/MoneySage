"""investment ledger: buys, sells, deposits and withdrawals

Revision ID: 4a8e2c6f1b39
Revises: 1f6b3d8a2c57
Create Date: 2026-11-02 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app import rls

revision: str = '4a8e2c6f1b39'
down_revision: Union[str, None] = '1f6b3d8a2c57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'investment_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('kind', sa.Enum('buy', 'sell', 'deposit', 'withdraw', 'add', name='investmenttxnkind', native_enum=False, length=20), nullable=False),
        sa.Column('asset_type', sa.Enum('stock', 'etf', 'crypto', 'cash', name='assettype', native_enum=False, length=20), nullable=False),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column('price', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('realized_gain', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('cash_change', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_investment_transactions_household_id', 'investment_transactions', ['household_id'])
    op.create_index('ix_investment_transactions_date', 'investment_transactions', ['date'])
    for statement in rls.household_policies('investment_transactions'):
        op.execute(statement)


def downgrade() -> None:
    for statement in rls.drop_policies('investment_transactions'):
        op.execute(statement)
    op.drop_index('ix_investment_transactions_date', 'investment_transactions')
    op.drop_index('ix_investment_transactions_household_id', 'investment_transactions')
    op.drop_table('investment_transactions')
