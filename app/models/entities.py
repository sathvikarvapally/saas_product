"""Billing entities. Database constraints also protect writes outside the API."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric,
    String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db.base import Base
from app.core.billing import next_period_end


class UTCDateTime(TypeDecorator):
    """Store UTC and restore timezone information when SQLite returns naive values."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone-aware datetime is required")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Entity:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Plan(Entity, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_plan_positive_price"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_plan_currency"),
        CheckConstraint("billing_interval IN ('monthly', 'quarterly', 'annual')", name="ck_plan_interval"),
    )

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    billing_interval: Mapped[str] = mapped_column(String(10), default="monthly", server_default="monthly")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"),
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")

    @property
    def billing_cycle(self) -> str:
        return "yearly" if self.billing_interval == "annual" else self.billing_interval

    @property
    def status(self) -> str:
        return "active" if self.is_active else "inactive"


class Customer(Entity, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_customer_email"),
        CheckConstraint("email = lower(trim(email))", name="ck_customer_normalized_email"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_customer_status"),
    )

    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(254))
    company_name: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="customer")


class Subscription(Entity, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'cancelled')", name="ck_subscription_status"),
        CheckConstraint("current_period_end > current_period_start", name="ck_subscription_period"),
        CheckConstraint(
            "(status = 'active' AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL AND cancelled_at >= start_date)",
            name="ck_subscription_cancellation",
        ),
        Index(
            "uq_active_customer_plan", "customer_id", "plan_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    start_date: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))
    current_period_start: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda context: context.get_current_parameters()["start_date"],
    )
    current_period_end: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda context: next_period_end(context.get_current_parameters()["start_date"], "monthly"),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    customer: Mapped[Customer] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship(back_populates="subscriptions")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription")


class Invoice(Entity, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount_due > 0", name="ck_invoice_positive_due"),
        CheckConstraint("amount_paid >= 0 AND amount_paid <= amount_due", name="ck_invoice_paid_bounds"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_invoice_currency"),
        CheckConstraint("period_end > period_start", name="ck_invoice_period"),
        CheckConstraint("due_date >= period_start", name="ck_invoice_due_date"),
        CheckConstraint(
            "(status IN ('draft', 'issued', 'void') AND amount_paid = 0) OR "
            "(status = 'overdue' AND amount_paid < amount_due) OR "
            "(status = 'partially_paid' AND amount_paid > 0 AND amount_paid < amount_due) OR "
            "(status = 'paid' AND amount_paid = amount_due)",
            name="ck_invoice_status_balance",
        ),
    )

    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), server_default="0.00")
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="issued", server_default="issued")
    period_start: Mapped[datetime] = mapped_column(UTCDateTime())
    period_end: Mapped[datetime] = mapped_column(UTCDateTime())
    due_date: Mapped[datetime] = mapped_column(UTCDateTime())
    subscription: Mapped[Subscription] = relationship(back_populates="invoices")
    customer: Mapped[Customer] = relationship(back_populates="invoices")
    payment_attempts: Mapped[list["PaymentAttempt"]] = relationship(back_populates="invoice")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="invoice")


class PaymentAttempt(Entity, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        Index("uq_payment_provider_reference", "provider_reference", unique=True),
        CheckConstraint("amount > 0", name="ck_payment_positive_amount"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_payment_currency"),
        CheckConstraint("status IN ('success', 'failed')", name="ck_payment_status"),
        CheckConstraint(
            "(status = 'success' AND failure_reason IS NULL) OR "
            "(status = 'failed' AND failure_reason IS NOT NULL AND length(trim(failure_reason)) > 0)",
            name="ck_payment_failure_reason",
        ),
        CheckConstraint("length(trim(provider_reference)) > 0", name="ck_payment_reference"),
    )

    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    provider_reference: Mapped[str] = mapped_column(String(255))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    invoice: Mapped[Invoice] = relationship(back_populates="payment_attempts")


class LedgerEntry(Entity, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_positive_amount"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_ledger_currency"),
        CheckConstraint(
            "event_type IN ('invoice_created', 'payment_success', 'payment_failure')",
            name="ck_ledger_event_type",
        ),
        CheckConstraint("length(trim(reference_id)) > 0", name="ck_ledger_reference"),
    )

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reference_id: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(String(500), default="", server_default="")
    customer: Mapped[Customer] = relationship(back_populates="ledger_entries")
    invoice: Mapped[Invoice] = relationship(back_populates="ledger_entries")

    @property
    def entry_type(self) -> str:
        return self.event_type
