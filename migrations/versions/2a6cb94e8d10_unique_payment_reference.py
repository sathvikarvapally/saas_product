"""Require unique provider references for payment attempts.

Revision ID: 2a6cb94e8d10
Revises: 1d994a3b37fa
"""
from alembic import op

revision = "2a6cb94e8d10"
down_revision = "1d994a3b37fa"
branch_labels = None
depends_on = None


def upgrade():
    # If duplicate data exists, preserve the old index and fail without deleting rows.
    op.create_index("uq_payment_provider_reference", "payment_attempts", ["provider_reference"], unique=True)
    op.drop_index("ix_payment_attempts_provider_reference", table_name="payment_attempts")


def downgrade():
    op.create_index("ix_payment_attempts_provider_reference", "payment_attempts", ["provider_reference"], unique=False)
    op.drop_index("uq_payment_provider_reference", table_name="payment_attempts")
