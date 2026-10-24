from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import Invoice, LedgerEntry, Plan, Subscription
from app.repositories.ledger import LedgerRepository
from app.schemas.invoice import InvoiceCreate
from app.services.invoice import InvoiceService, next_period_end


@pytest.fixture
def billing(client, database):
    customer = client.post("/customers", json={"name": "Test", "email": "test@example.com"}).json()
    plan = client.post("/plans", json={"name": "Starter", "price": "499.00", "currency": "INR"}).json()
    subscription = client.post("/subscriptions", json={"customer_id": customer["id"], "plan_id": plan["id"]}).json()
    with Session(database[0]) as session:
        session.get(Subscription, subscription["id"]).start_date = datetime(2024, 1, 31, 10, tzinfo=timezone.utc)
        session.commit()
    return {
        "customer_id": customer["id"], "plan_id": plan["id"],
        "subscription_id": subscription["id"],
        "path": f"/subscriptions/{subscription['id']}/invoices",
        "ledger": f"/customers/{customer['id']}/ledger",
    }


def test_generate_default_invoice_and_traceable_ledger(client, billing):
    response = client.post(billing["path"])
    assert response.status_code == 201
    invoice = response.json()
    assert invoice["subscription_id"] == billing["subscription_id"]
    assert invoice["customer_id"] == billing["customer_id"]
    assert invoice["amount_due"] == "499.00"
    assert invoice["amount_paid"] == "0.00"
    assert invoice["currency"] == "INR"
    assert invoice["status"] == "issued"
    assert invoice["period_start"] == "2024-01-31T10:00:00Z"
    assert invoice["period_end"] == "2024-02-29T10:00:00Z"
    assert invoice["due_date"] == "2024-02-07T10:00:00Z"
    assert client.get(f"/invoices/{invoice['id']}").json() == invoice
    entries = client.get(billing["ledger"]).json()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["event_type"] == "invoice_created"
    assert entry["invoice_id"] == invoice["id"]
    assert entry["customer_id"] == invoice["customer_id"]
    assert entry["amount"] == invoice["amount_due"]
    assert entry["currency"] == invoice["currency"]
    assert entry["reference_id"] == f"invoice:{invoice['id']}"


@pytest.mark.parametrize("start,interval,expected", [
    ("2023-01-31T10:00:00+00:00", "monthly", "2023-02-28T10:00:00+00:00"),
    ("2024-01-31T10:00:00+00:00", "monthly", "2024-02-29T10:00:00+00:00"),
    ("2024-12-31T10:00:00+00:00", "monthly", "2025-01-31T10:00:00+00:00"),
    ("2024-02-29T10:00:00+00:00", "annual", "2025-02-28T10:00:00+00:00"),
    ("2024-01-31T10:00:00+00:00", "quarterly", "2024-04-30T10:00:00+00:00"),
])
def test_calendar_period_boundaries(start, interval, expected):
    assert next_period_end(datetime.fromisoformat(start), interval).isoformat() == expected


def test_annual_invoice_period(client, billing, database):
    with Session(database[0]) as session:
        session.get(Plan, billing["plan_id"]).billing_interval = "annual"
        session.get(Subscription, billing["subscription_id"]).start_date = datetime(2024, 2, 29, tzinfo=timezone.utc)
        session.commit()
    invoice = client.post(billing["path"], json={}).json()
    assert invoice["period_start"] == "2024-02-29T00:00:00Z"
    assert invoice["period_end"] == "2025-02-28T00:00:00Z"


def test_custom_period_dates_normalize_to_utc_and_next_period_is_allowed(client, billing):
    first = client.post(billing["path"]).json()
    response = client.post(billing["path"], json={
        "period_start": "2024-02-29T15:30:00+05:30",
        "period_end": "2024-03-31T15:30:00+05:30",
        "due_date": "2024-03-03T15:30:00+05:30",
    })
    assert response.status_code == 201
    second = response.json()
    assert second["period_start"] == first["period_end"]
    assert second["period_end"] == "2024-03-31T10:00:00Z"
    assert second["due_date"] == "2024-03-03T10:00:00Z"
    assert second["amount_due"] == "499.00"
    assert len(client.get(billing["ledger"]).json()) == 2


def test_price_and_currency_are_snapshots_at_generation(client, billing, database):
    first = client.post(billing["path"]).json()
    with Session(database[0]) as session:
        plan = session.get(Plan, billing["plan_id"])
        plan.price = Decimal("799.00")
        plan.currency = "USD"
        session.commit()
    second = client.post(billing["path"], json={"period_start": first["period_end"]}).json()
    assert second["amount_due"] == "799.00"
    assert second["currency"] == "USD"
    assert client.get(f"/invoices/{first['id']}").json() == first
    entries = client.get(billing["ledger"]).json()
    assert [(item["amount"], item["currency"]) for item in entries] == [("499.00", "INR"), ("799.00", "USD")]


@pytest.mark.parametrize("body", [
    {},
    {"period_start": "2024-02-10T10:00:00Z", "period_end": "2024-02-20T10:00:00Z"},
    {"period_start": "2024-02-20T10:00:00Z", "period_end": "2024-03-10T10:00:00Z"},
    {"period_start": "2024-01-31T10:00:00Z", "period_end": "2024-03-10T10:00:00Z"},
])
def test_duplicate_and_overlapping_periods_return_conflict(client, billing, body):
    assert client.post(billing["path"]).status_code == 201
    assert client.post(billing["path"], json=body).status_code == 409
    assert len(client.get(billing["ledger"]).json()) == 1


@pytest.mark.parametrize("body", [
    {"period_start": "2024-01-30T10:00:00Z"},
    {"period_end": "2024-02-29T10:00:00Z"},
    {"period_start": "2024-02-01T10:00:00"},
    {"period_start": "2024-02-01T10:00:00Z", "period_end": "2024-02-01T10:00:00Z"},
    {"period_start": "2024-02-01T10:00:00Z", "period_end": "2024-01-31T10:00:00Z"},
    {"due_date": "2024-01-01T00:00:00Z"},
    {"period_start": "2024-02-01T00:00:00Z", "due_date": "2024-01-01T00:00:00Z"},
    {"amount_due": "1.00"},
    {"period_start": "9999-12-31T00:00:00Z"},
])
def test_invalid_invoice_dates_or_fields_rejected_without_writes(client, billing, body, database):
    assert client.post(billing["path"], json=body).status_code == 422
    assert client.get(billing["ledger"]).json() == []
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 0


def test_cancelled_subscription_cannot_generate_invoice(client, billing):
    client.post(f"/subscriptions/{billing['subscription_id']}/cancel")
    assert client.post(billing["path"]).status_code == 409
    assert client.get(billing["ledger"]).json() == []


def test_inactive_plan_does_not_block_existing_active_subscription(client, billing):
    client.patch(f"/plans/{billing['plan_id']}", json={"is_active": False})
    assert client.post(billing["path"]).status_code == 201


def test_missing_invoice_subscription_or_ledger_customer_returns_404(client):
    assert client.post("/subscriptions/999/invoices").status_code == 404
    assert client.get("/invoices/999").status_code == 404
    assert client.get("/customers/999/ledger").status_code == 404


def test_ledger_is_scoped_to_customer_and_paginated(client, billing):
    assert client.get(billing["ledger"]).json() == []
    other = client.post("/customers", json={"name": "Other", "email": "other@example.com"}).json()
    assert client.get(f"/customers/{other['id']}/ledger").json() == []
    first = client.post(billing["path"]).json()
    second = client.post(billing["path"], json={"period_start": first["period_end"]}).json()
    assert client.get(f"/customers/{other['id']}/ledger").json() == []
    page = client.get(billing["ledger"], params={"offset": 1, "limit": 1}).json()
    assert len(page) == 1
    assert page[0]["invoice_id"] == second["id"]
    assert client.get(billing["ledger"], params={"limit": 101}).status_code == 422


def test_ledger_failure_rolls_back_both_inserted_rows(client, billing, database, monkeypatch):
    append = LedgerRepository.append

    def append_then_fail(self, **values):
        append(self, **values)
        raise RuntimeError("Simulated ledger failure")

    with monkeypatch.context() as patch:
        patch.setattr(LedgerRepository, "append", append_then_fail)
        with pytest.raises(RuntimeError, match="Simulated ledger failure"):
            client.post(billing["path"])
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 0
        assert session.scalar(select(func.count()).select_from(LedgerEntry)) == 0
    assert client.post(billing["path"]).status_code == 201


def test_concurrent_duplicate_invoice_requests_create_one_invoice_and_event(client, billing, database):
    barrier = Barrier(2)

    def generate():
        with Session(database[0], expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            try:
                InvoiceService(session).generate(billing["subscription_id"], InvoiceCreate())
                return "created"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(), range(2)))
    assert sorted(results) == ["conflict", "created"]
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1
        assert session.scalar(select(func.count()).select_from(LedgerEntry)) == 1


def test_openapi_contains_invoice_and_ledger_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/subscriptions/{subscription_id}/invoices", "/invoices/{invoice_id}", "/customers/{customer_id}/ledger"} <= paths.keys()
