"""Add assignment profile, billing period, and audit fields.

Revision ID: 39f1b5c0a712
Revises: 2a6cb94e8d10
"""
from calendar import monthrange
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "39f1b5c0a712"
down_revision = "2a6cb94e8d10"
branch_labels = None
depends_on = None

OLD_BALANCE = (
    "(status IN ('draft', 'issued') AND amount_paid = 0) OR "
    "(status = 'partially_paid' AND amount_paid > 0 AND amount_paid < amount_due) OR "
    "(status = 'paid' AND amount_paid = amount_due)"
)
NEW_BALANCE = (
    "(status IN ('draft', 'issued', 'void') AND amount_paid = 0) OR "
    "(status = 'overdue' AND amount_paid < amount_due) OR "
    "(status = 'partially_paid' AND amount_paid > 0 AND amount_paid < amount_due) OR "
    "(status = 'paid' AND amount_paid = amount_due)"
)


def upgrade():
    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("description", sa.String(500), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch.drop_constraint("ck_plan_interval", type_="check")
        batch.create_check_constraint("ck_plan_interval", "billing_interval IN ('monthly', 'quarterly', 'annual')")
    op.execute("UPDATE plans SET updated_at = created_at")
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("company_name", sa.String(150), nullable=True))
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="active"))
        batch.create_check_constraint("ck_customer_status", "status IN ('active', 'inactive')")
    op.add_column("subscriptions", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT s.id, s.start_date, p.billing_interval FROM subscriptions s "
        "JOIN plans p ON p.id = s.plan_id"
    )).mappings().all()
    for row in rows:
        start = row["start_date"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        months = {"monthly": 1, "quarterly": 3, "annual": 12}[row["billing_interval"]]
        year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
        month += 1
        end = start.replace(year=year, month=month, day=min(start.day, monthrange(year, month)[1]))
        # Preserve the latest generated billing period when invoices already exist.
        latest = connection.execute(sa.text(
            "SELECT period_start, period_end FROM invoices WHERE subscription_id = :id "
            "ORDER BY period_start DESC LIMIT 1"
        ), {"id": row["id"]}).mappings().first()
        if latest:
            start, end = latest["period_start"], latest["period_end"]
        if isinstance(start, datetime):
            start = start.isoformat(sep=" ")
        if isinstance(end, datetime):
            end = end.isoformat(sep=" ")
        connection.execute(sa.text(
            "UPDATE subscriptions SET current_period_start = :start, current_period_end = :end WHERE id = :id"
        ), {"id": row["id"], "start": start, "end": end})
    with op.batch_alter_table("subscriptions") as batch:
        batch.alter_column("current_period_start", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("current_period_end", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_check_constraint("ck_subscription_period", "current_period_end > current_period_start")
    with op.batch_alter_table("invoices") as batch:
        batch.drop_constraint("ck_invoice_status_balance", type_="check")
        batch.create_check_constraint("ck_invoice_status_balance", NEW_BALANCE)
    op.add_column("ledger_entries", sa.Column("description", sa.String(500), nullable=False, server_default=""))


def downgrade():
    # Audit history stays immutable. Do not silently rewrite invoice or plan state.
    connection = op.get_bind()
    unsupported = connection.execute(sa.text(
        "SELECT (SELECT count(*) FROM plans WHERE billing_interval = 'quarterly') + "
        "(SELECT count(*) FROM invoices WHERE status IN ('overdue', 'void'))"
    )).scalar_one()
    if unsupported:
        raise RuntimeError("Downgrade requires no quarterly plans or overdue/void invoices")
    op.drop_column("ledger_entries", "description")
    with op.batch_alter_table("invoices") as batch:
        batch.drop_constraint("ck_invoice_status_balance", type_="check")
        batch.create_check_constraint("ck_invoice_status_balance", OLD_BALANCE)
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_constraint("ck_subscription_period", type_="check")
        batch.drop_column("current_period_end")
        batch.drop_column("current_period_start")
    with op.batch_alter_table("customers") as batch:
        batch.drop_constraint("ck_customer_status", type_="check")
        batch.drop_column("company_name")
        batch.drop_column("status")
    with op.batch_alter_table("plans") as batch:
        batch.drop_constraint("ck_plan_interval", type_="check")
        batch.create_check_constraint("ck_plan_interval", "billing_interval IN ('monthly', 'annual')")
        batch.drop_column("updated_at")
        batch.drop_column("description")
