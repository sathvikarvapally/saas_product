from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import Invoice, LedgerEntry, PaymentAttempt
from app.repositories.ledger import LedgerRepository
from app.repositories.payment import PaymentAttemptRepository
from app.schemas.payment import PaymentCreate
from app.services.payment import PaymentService


@pytest.fixture
def payment_invoice(client):
    customer = client.post("/customers", json={"name": "Test", "email": "test@example.com"}).json()
    plan = client.post("/plans", json={"name": "Starter", "price": "499.00", "currency": "INR"}).json()
    subscription = client.post("/subscriptions", json={"customer_id": customer["id"], "plan_id": plan["id"]}).json()
    response = client.post(f"/subscriptions/{subscription['id']}/invoices")
    assert response.status_code == 201
    invoice = response.json()
    return {
        "invoice": invoice, "subscription_id": subscription["id"],
        "path": f"/invoices/{invoice['id']}/payments",
        "ledger": f"/customers/{customer['id']}/ledger",
    }


def success(amount="200.00", reference="attempt-1"):
    return {"amount": amount, "currency": "INR", "status": "success", "provider_reference": reference}


def failure(amount="200.00", reference="failed-1"):
    return {**success(amount, reference), "status": "failed", "failure_reason": "Card declined"}


def test_partial_then_full_payment_updates_invoice_and_ledger(client, payment_invoice):
    path = payment_invoice["path"]
    response = client.post(path, json=success())
    assert response.status_code == 201
    first = response.json()
    assert first["invoice"]["amount_paid"] == "200.00"
    assert first["invoice"]["status"] == "partially_paid"
    attempt = first["payment_attempt"]
    assert attempt["amount"] == "200.00"
    assert attempt["status"] == "success"
    assert attempt["failure_reason"] is None
    assert attempt["created_at"].endswith("Z")
    response = client.post(path, json=success("299.00", "attempt-2"))
    assert response.status_code == 201
    result = response.json()
    assert result["invoice"]["status"] == "paid"
    assert result["invoice"]["amount_paid"] == "499.00"
    assert client.get(f"/invoices/{result['invoice']['id']}").json() == result["invoice"]
    entries = client.get(payment_invoice["ledger"]).json()
    assert [entry["event_type"] for entry in entries] == ["invoice_created", "payment_success", "payment_success"]
    assert entries[1]["reference_id"] == f"payment:{attempt['id']}"
    assert entries[1]["amount"] == "200.00"
    assert entries[1]["invoice_id"] == result["invoice"]["id"]
    assert entries[1]["currency"] == "INR"
    assert client.get(path).json() == [first["payment_attempt"], result["payment_attempt"]]


def test_full_payment_and_no_further_successful_payment(client, payment_invoice):
    response = client.post(payment_invoice["path"], json=success("499.00"))
    assert response.status_code == 201
    assert response.json()["invoice"]["status"] == "paid"
    assert client.post(payment_invoice["path"], json=success("0.01", "extra")).status_code == 409
    assert len(client.get(payment_invoice["path"]).json()) == 1
    assert len(client.get(payment_invoice["ledger"]).json()) == 2


def test_overpayment_uses_remaining_amount_and_leaves_no_attempt_or_event(client, payment_invoice):
    client.post(payment_invoice["path"], json=success("200.00"))
    response = client.post(payment_invoice["path"], json=success("299.01", "too-much"))
    assert response.status_code == 409
    assert "remaining unpaid" in response.json()["detail"]
    assert len(client.get(payment_invoice["path"]).json()) == 1
    assert len(client.get(payment_invoice["ledger"]).json()) == 2
    invoice = client.get(f"/invoices/{payment_invoice['invoice']['id']}").json()
    assert invoice["amount_paid"] == "200.00"
    # A rejected reference was not recorded, so a corrected request may use it.
    assert client.post(payment_invoice["path"], json=success("299.00", "too-much")).status_code == 201


def test_decimal_payments_sum_exactly(client, payment_invoice):
    for i, amount in enumerate(["0.10", "0.20", "498.70"]):
        response = client.post(payment_invoice["path"], json=success(amount, f"decimal-{i}"))
        assert response.status_code == 201
    assert response.json()["invoice"]["amount_paid"] == "499.00"
    assert response.json()["invoice"]["status"] == "paid"


@pytest.mark.parametrize("partial", [False, True])
def test_failed_payment_does_not_change_invoice_balance_or_status(client, payment_invoice, partial):
    if partial:
        client.post(payment_invoice["path"], json=success())
    before = client.get(f"/invoices/{payment_invoice['invoice']['id']}").json()
    response = client.post(payment_invoice["path"], json={**failure("999.00"), "failure_reason": " Card declined "})
    assert response.status_code == 201
    assert response.json()["invoice"] == before
    assert response.json()["payment_attempt"]["failure_reason"] == "Card declined"
    entry = client.get(payment_invoice["ledger"]).json()[-1]
    assert entry["event_type"] == "payment_failure"
    assert entry["amount"] == "999.00"
    assert client.post(payment_invoice["path"], json=success("299.00" if partial else "499.00", "retry-new-reference")).status_code == 201


@pytest.mark.parametrize("status", ["success", "failed"])
def test_currency_mismatch_returns_conflict(client, payment_invoice, status):
    payload = success() if status == "success" else failure()
    response = client.post(payment_invoice["path"], json={**payload, "currency": "USD"})
    assert response.status_code == 409
    assert client.get(payment_invoice["path"]).json() == []
    assert len(client.get(payment_invoice["ledger"]).json()) == 1


@pytest.mark.parametrize("payload", [success(), failure()])
def test_repeated_reference_returns_conflict_and_preserves_original_attempt(client, payment_invoice, payload):
    first = client.post(payment_invoice["path"], json=payload)
    assert first.status_code == 201
    repeated = client.post(payment_invoice["path"], json=payload)
    assert repeated.status_code == 409
    assert repeated.json() == {"detail": "Provider reference has already been recorded"}
    changed = client.post(payment_invoice["path"], json={**payload, "amount": "1.00"})
    assert changed.status_code == 409
    assert client.get(payment_invoice["path"]).json() == [first.json()["payment_attempt"]]
    assert len(client.get(payment_invoice["ledger"]).json()) == 2


def test_references_are_trimmed_and_unique_across_invoices(client, payment_invoice):
    assert client.post(payment_invoice["path"], json=success(reference=" shared ")).status_code == 201
    second = client.post(f"/subscriptions/{payment_invoice['subscription_id']}/invoices", json={"period_start": payment_invoice["invoice"]["period_end"]}).json()
    assert client.post(f"/invoices/{second['id']}/payments", json=success(reference="shared")).status_code == 409


def test_database_reference_constraint_and_conflict_translation(client, payment_invoice, database, monkeypatch):
    assert client.post(payment_invoice["path"], json=success()).status_code == 201
    lookup = PaymentAttemptRepository.get_by_reference
    calls = 0

    def miss_initial_check(self, reference):
        nonlocal calls
        calls += 1
        return None if calls == 1 else lookup(self, reference)

    monkeypatch.setattr(PaymentAttemptRepository, "get_by_reference", miss_initial_check)
    assert client.post(payment_invoice["path"], json=success()).status_code == 409
    assert len(client.get(payment_invoice["path"]).json()) == 1
    with Session(database[0]) as session:
        session.add(PaymentAttempt(invoice_id=payment_invoice["invoice"]["id"], **success()))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("field,value", [
    ("amount", "0"), ("amount", "-1"), ("amount", "1.001"),
    ("amount", "NaN"), ("amount", "Infinity"), ("amount", "10000000000.00"),
    ("currency", "XYZ"), ("status", "pending"), ("provider_reference", " "),
    ("provider_reference", "x" * 256), ("failure_reason", "Unexpected reason"),
    ("invoice_id", 123),
])
def test_invalid_payment_input_rejected_without_writes(client, payment_invoice, field, value):
    assert client.post(payment_invoice["path"], json={**success(), field: value}).status_code == 422
    assert client.get(payment_invoice["path"]).json() == []
    assert len(client.get(payment_invoice["ledger"]).json()) == 1


@pytest.mark.parametrize("reason", [None, " ", "x" * 501])
def test_failed_payment_requires_valid_reason(client, payment_invoice, reason):
    assert client.post(payment_invoice["path"], json={**failure(), "failure_reason": reason}).status_code == 422


def test_missing_invoice_and_invalid_pagination(client, payment_invoice):
    assert client.post("/invoices/999/payments", json=success()).status_code == 404
    assert client.get("/invoices/999/payments").status_code == 404
    assert client.get(payment_invoice["path"]).json() == []
    for query in ({"offset": -1}, {"limit": 0}, {"limit": 101}):
        assert client.get(payment_invoice["path"], params=query).status_code == 422
    for i in range(3):
        assert client.post(payment_invoice["path"], json=failure(reference=f"failed-{i}")).status_code == 201
    attempts = client.get(payment_invoice["path"]).json()
    assert client.get(payment_invoice["path"], params={"offset": 1, "limit": 1}).json() == attempts[1:2]


def test_cancellation_does_not_prevent_paying_existing_invoice(client, payment_invoice):
    client.post(f"/subscriptions/{payment_invoice['subscription_id']}/cancel")
    assert client.post(payment_invoice["path"], json=success("499.00")).json()["invoice"]["status"] == "paid"


def test_draft_invoice_rejects_payments(client, payment_invoice, database):
    with Session(database[0]) as session:
        session.get(Invoice, payment_invoice["invoice"]["id"]).status = "draft"
        session.commit()
    assert client.post(payment_invoice["path"], json=success()).status_code == 409
    assert client.get(payment_invoice["path"]).json() == []


@pytest.mark.parametrize("payload", [success(), failure()])
def test_ledger_failure_rolls_back_payment_invoice_and_event(client, payment_invoice, database, monkeypatch, payload):
    append = LedgerRepository.append

    def append_then_fail(self, **values):
        append(self, **values)
        raise RuntimeError("Simulated payment ledger failure")

    with monkeypatch.context() as patch:
        patch.setattr(LedgerRepository, "append", append_then_fail)
        with pytest.raises(RuntimeError, match="Simulated payment ledger failure"):
            client.post(payment_invoice["path"], json=payload)
    with Session(database[0]) as session:
        invoice = session.get(Invoice, payment_invoice["invoice"]["id"])
        assert invoice.amount_paid == Decimal("0.00")
        assert invoice.status == "issued"
        assert session.scalar(select(func.count()).select_from(PaymentAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(LedgerEntry)) == 1
    assert client.post(payment_invoice["path"], json=payload).status_code == 201


@pytest.mark.parametrize("same_reference,amount,total,count", [
    (False, "300.00", "300.00", 1),
    (True, "100.00", "100.00", 1),
    (False, "200.00", "400.00", 2),
])
def test_concurrent_payments_cannot_overpay_duplicate_or_lose_updates(
    client, payment_invoice, database, same_reference, amount, total, count,
):
    barrier = Barrier(2)

    def record(i):
        reference = "shared" if same_reference else f"concurrent-{i}"
        data = PaymentCreate(**success(amount, reference))
        with Session(database[0], expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            try:
                PaymentService(session).record(payment_invoice["invoice"]["id"], data)
                return "created"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(record, range(2)))
    assert results.count("created") == count
    assert results.count("conflict") == 2 - count
    with Session(database[0]) as session:
        invoice = session.get(Invoice, payment_invoice["invoice"]["id"])
        assert invoice.amount_paid == Decimal(total)
        assert invoice.status == "partially_paid"
        assert session.scalar(select(func.count()).select_from(PaymentAttempt)) == count
        assert session.scalar(select(func.count()).select_from(LedgerEntry)) == count + 1


def test_openapi_contains_payment_routes(client):
    route = client.get("/openapi.json").json()["paths"]["/invoices/{invoice_id}/payments"]
    assert {"get", "post"} <= route.keys()
