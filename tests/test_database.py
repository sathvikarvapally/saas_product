"""Exercise the migrated schema, including constraints bypassing API validation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import Customer, Invoice, LedgerEntry, PaymentAttempt, Plan, Subscription


def seed_invoice(session):
    now = datetime.now(timezone.utc)
    customer = Customer(name="Test Customer", email="test@example.com")
    plan = Plan(name="Starter", price=Decimal("19.99"), currency="INR")
    subscription = Subscription(customer=customer, plan=plan)
    invoice = Invoice(
        subscription=subscription, customer=customer,
        amount_due=Decimal("19.99"), currency="INR",
        period_start=now, period_end=now + timedelta(days=30),
        due_date=now + timedelta(days=7),
    )
    session.add(invoice)
    session.commit()
    return invoice


def test_migration_round_trip(database):
    engine, config = database
    expected = {"customers", "plans", "subscriptions", "invoices", "payment_attempts", "ledger_entries"}
    assert expected <= set(inspect(engine).get_table_names())
    command.check(config)
    command.downgrade(config, "base")
    assert not expected.intersection(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert expected <= set(inspect(engine).get_table_names())


@pytest.mark.parametrize("price", ["0", "-1.00"])
def test_plan_price_must_be_positive(session, price):
    session.add(Plan(name="Invalid", price=Decimal(price), currency="INR"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_customer_email_is_unique(session):
    session.add_all([
        Customer(name="First", email="same@example.com"),
        Customer(name="Second", email="same@example.com"),
    ])
    with pytest.raises(IntegrityError):
        session.commit()


def test_email_must_be_normalized(session):
    session.add(Customer(name="Test", email=" Test@Example.com "))
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_active_subscription_rejected(session):
    invoice = seed_invoice(session)
    session.add(Subscription(customer_id=invoice.customer_id, plan_id=invoice.subscription.plan_id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_new_subscription_allowed_after_cancellation(session):
    invoice = seed_invoice(session)
    subscription = invoice.subscription
    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.now(timezone.utc)
    session.commit()
    session.add(Subscription(customer_id=invoice.customer_id, plan_id=subscription.plan_id))
    session.commit()
    assert len(session.scalars(select(Subscription)).all()) == 2


def test_foreign_keys_reject_missing_customer(session):
    plan = Plan(name="Starter", price=Decimal("10.00"), currency="INR")
    session.add(plan)
    session.commit()
    session.add(Subscription(customer_id=9999, plan_id=plan.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_relationships_money_and_utc_round_trip(session):
    invoice_id = seed_invoice(session).id
    session.expunge_all()
    invoice = session.get(Invoice, invoice_id)
    assert invoice.amount_due == Decimal("19.99")
    assert isinstance(invoice.amount_due, Decimal)
    assert invoice.created_at.utcoffset() == timedelta(0)
    assert invoice.period_start.utcoffset() == timedelta(0)
    assert invoice.subscription.plan.name == "Starter"
    assert invoice.customer.email == "test@example.com"
    invoice.subscription.plan.price = Decimal("30.00")
    session.commit()
    session.refresh(invoice)
    assert invoice.amount_due == Decimal("19.99")


def test_naive_datetime_rejected(session):
    invoice = seed_invoice(session)
    invoice.due_date = datetime(2026, 12, 1)
    with pytest.raises(StatementError, match="timezone-aware"):
        session.commit()


@pytest.mark.parametrize("amount,status", [("20.00", "paid"), ("10.00", "paid"), ("0.00", "partially_paid")])
def test_invalid_invoice_balance_or_status_rejected(session, amount, status):
    invoice = seed_invoice(session)
    invoice.amount_paid = Decimal(amount)
    invoice.status = status
    with pytest.raises(IntegrityError):
        session.commit()


def test_valid_partial_and_full_invoice_states(session):
    invoice = seed_invoice(session)
    invoice.amount_paid = Decimal("10.00")
    invoice.status = "partially_paid"
    session.commit()
    invoice.amount_paid = Decimal("19.99")
    invoice.status = "paid"
    session.commit()


def test_failed_payment_requires_reason(session):
    invoice = seed_invoice(session)
    session.add(PaymentAttempt(
        invoice_id=invoice.id, amount=Decimal("5.00"), currency="INR",
        status="failed", provider_reference="attempt-1",
    ))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("operation", ["UPDATE ledger_entries SET amount = 1", "DELETE FROM ledger_entries"])
def test_ledger_is_append_only_even_with_direct_sql(session, operation):
    invoice = seed_invoice(session)
    session.add(LedgerEntry(
        invoice_id=invoice.id, customer_id=invoice.customer_id,
        event_type="invoice_created", amount=invoice.amount_due,
        currency=invoice.currency, reference_id=f"invoice:{invoice.id}",
    ))
    session.commit()
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text(operation))
    session.rollback()
    assert session.scalar(select(LedgerEntry.amount)) == Decimal("19.99")
