"""add_plan_referral_clearance_fields

Revision ID: 9e3cd4ecb5f8
Revises: a206e54d49bc
Create Date: 2026-04-12 21:25:43.469619

"""
from typing import Sequence, Union
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e3cd4ecb5f8'
down_revision: Union[str, Sequence[str], None] = 'a206e54d49bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Add new transactioncategory enum values
    # ------------------------------------------------------------------ #
    op.execute("ALTER TYPE transactioncategory ADD VALUE IF NOT EXISTS 'registration_fee'")
    op.execute("ALTER TYPE transactioncategory ADD VALUE IF NOT EXISTS 'referral_bonus'")
    op.execute("ALTER TYPE transactioncategory ADD VALUE IF NOT EXISTS 'clearance_fee'")

    # ------------------------------------------------------------------ #
    # 2. Create bonustype enum (lowercase values to match Python enum)
    # ------------------------------------------------------------------ #
    op.execute("CREATE TYPE bonustype AS ENUM ('fixed', 'percentage')")

    # ------------------------------------------------------------------ #
    # 3. savings_plans — rename start_commission → registration_fee
    # ------------------------------------------------------------------ #
    op.alter_column('savings_plans', 'start_commission', new_column_name='registration_fee')

    # ------------------------------------------------------------------ #
    # 4. savings_plans — add new columns with server defaults
    # ------------------------------------------------------------------ #
    op.add_column('savings_plans', sa.Column(
        'clearance_fee', sa.Numeric(precision=15, scale=2),
        nullable=False, server_default='0.00'
    ))
    op.add_column('savings_plans', sa.Column(
        'referral_code_release_week', sa.Integer(),
        nullable=False, server_default='1'
    ))
    op.add_column('savings_plans', sa.Column(
        'referral_code_validity_weeks', sa.Integer(),
        nullable=False, server_default='1'
    ))
    op.add_column('savings_plans', sa.Column(
        'downline_qualification_week', sa.Integer(),
        nullable=False, server_default='1'
    ))
    op.add_column('savings_plans', sa.Column(
        'referral_bonus_type',
        sa.Enum('fixed', 'percentage', name='bonustype', create_type=False),
        nullable=False, server_default='fixed'
    ))
    op.add_column('savings_plans', sa.Column(
        'referral_bonus_value', sa.Numeric(precision=15, scale=2),
        nullable=False, server_default='0.00'
    ))
    op.add_column('savings_plans', sa.Column(
        'referral_required_for_payout', sa.Boolean(),
        nullable=False, server_default='false'
    ))

    # ------------------------------------------------------------------ #
    # 5. subscriptions — add referral code date columns (nullable)
    # ------------------------------------------------------------------ #
    op.add_column('subscriptions', sa.Column('referral_code_available_at', sa.Date(), nullable=True))
    op.add_column('subscriptions', sa.Column('referral_code_expires_at', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'referral_code_expires_at')
    op.drop_column('subscriptions', 'referral_code_available_at')

    op.drop_column('savings_plans', 'referral_required_for_payout')
    op.drop_column('savings_plans', 'referral_bonus_value')
    op.drop_column('savings_plans', 'referral_bonus_type')
    op.drop_column('savings_plans', 'downline_qualification_week')
    op.drop_column('savings_plans', 'referral_code_validity_weeks')
    op.drop_column('savings_plans', 'referral_code_release_week')
    op.drop_column('savings_plans', 'clearance_fee')

    # Rename back
    op.alter_column('savings_plans', 'registration_fee', new_column_name='start_commission')

    op.execute("DROP TYPE IF EXISTS bonustype")
    # Note: cannot remove enum values from transactioncategory in PostgreSQL
