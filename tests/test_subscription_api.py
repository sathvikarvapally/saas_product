from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import Subscription
from app.repositories.subscription import SubscriptionRepository
from app.schemas.subscription import SubscriptionCreate
from app.services.subscription import SubscriptionService


@pytest.fixture
def subscription_data(client):
    customer = client.post("/customers", json={"name": "Test", "email": "test@example.com"})
    plan = client.post("/plans", json={"name": "Starter", "price": "499.00", "currency": "INR"})
    assert customer.status_code == plan.status_code == 201
    return {"customer_id": customer.json()["id"], "plan_id": plan.json()["id"]}


def test_create_and_get_subscription(client, subscription_data):
    response = client.post("/subscriptions", json=subscription_data)
    assert response.status_code == 201
    subscription = response.json()
    assert subscription.items() >= subscription_data.items()
    assert subscription["status"] == "active"
    assert subscription["cancelled_at"] is None
    assert subscription["start_date"].endswith("Z")
    assert subscription["created_at"].endswith("Z")
    assert client.get(f"/subscriptions/{subscription['id']}").json() == subscription
    assert client.get("/subscriptions").json() == [subscription]


@pytest.mark.parametrize("field,detail", [("customer_id", "Customer not found"), ("plan_id", "Plan not found")])
def test_subscription_requires_existing_entities(client, subscription_data, field, detail):
    response = client.post("/subscriptions", json={**subscription_data, field: 9999})
    assert response.status_code == 404
    assert response.json() == {"detail": detail}
    assert client.get("/subscriptions").json() == []


def test_inactive_plan_blocks_subscription_without_poisoning_next_request(client, subscription_data):
    path = f"/plans/{subscription_data['plan_id']}"
    assert client.patch(path, json={"is_active": False}).status_code == 200
    response = client.post("/subscriptions", json=subscription_data)
    assert response.status_code == 409
    assert response.json() == {"detail": "Cannot subscribe to an inactive plan"}
    assert client.get("/subscriptions").json() == []
    client.patch(path, json={"is_active": True})
    assert client.post("/subscriptions", json=subscription_data).status_code == 201


def test_duplicate_active_subscription_returns_conflict(client, subscription_data):
    assert client.post("/subscriptions", json=subscription_data).status_code == 201
    response = client.post("/subscriptions", json=subscription_data)
    assert response.status_code == 409
    assert response.json() == {"detail": "Customer already has an active subscription to this plan"}
    assert len(client.get("/subscriptions").json()) == 1


def test_database_duplicate_conflict_after_missed_precheck(client, subscription_data, monkeypatch):
    assert client.post("/subscriptions", json=subscription_data).status_code == 201
    lookup = SubscriptionRepository.get_active
    calls = 0

    def miss_initial_check(self, customer_id, plan_id):
        nonlocal calls
        calls += 1
        return None if calls == 1 else lookup(self, customer_id, plan_id)

    monkeypatch.setattr(SubscriptionRepository, "get_active", miss_initial_check)
    assert client.post("/subscriptions", json=subscription_data).status_code == 409
    assert len(client.get("/subscriptions").json()) == 1


def test_cancellation_is_immediate_idempotent_and_allows_resubscription(client, subscription_data):
    original = client.post("/subscriptions", json=subscription_data).json()
    path = f"/subscriptions/{original['id']}"
    response = client.post(f"{path}/cancel")
    assert response.status_code == 200
    cancelled = response.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_at"].endswith("Z")
    assert cancelled["start_date"] == original["start_date"]
    assert client.post(f"{path}/cancel").json() == cancelled
    assert client.get(path).json() == cancelled
    replacement = client.post("/subscriptions", json=subscription_data)
    assert replacement.status_code == 201
    assert replacement.json()["id"] != original["id"]
    assert len(client.get("/subscriptions").json()) == 2


def test_plan_deactivation_preserves_existing_subscription_and_allows_cancellation(client, subscription_data):
    subscription = client.post("/subscriptions", json=subscription_data).json()
    client.patch(f"/plans/{subscription_data['plan_id']}", json={"is_active": False})
    path = f"/subscriptions/{subscription['id']}"
    assert client.get(path).json()["status"] == "active"
    assert client.post(f"{path}/cancel").status_code == 200
    assert client.post("/subscriptions", json=subscription_data).status_code == 409


def test_multiple_plans_and_customers_are_allowed_and_filters_combine(client, subscription_data):
    first = client.post("/subscriptions", json=subscription_data).json()
    second_plan = client.post("/plans", json={"name": "Pro", "price": "999.00", "currency": "INR"}).json()
    second_customer = client.post("/customers", json={"name": "Other", "email": "other@example.com"}).json()
    second = client.post("/subscriptions", json={**subscription_data, "plan_id": second_plan["id"]}).json()
    third = client.post("/subscriptions", json={**subscription_data, "customer_id": second_customer["id"]}).json()
    assert len({first["id"], second["id"], third["id"]}) == 3
    client.post(f"/subscriptions/{first['id']}/cancel")
    by_customer = client.get("/subscriptions", params={"customer_id": subscription_data["customer_id"]}).json()
    assert [item["id"] for item in by_customer] == [first["id"], second["id"]]
    assert client.get("/subscriptions", params={"plan_id": second_plan["id"]}).json() == [second]
    assert client.get("/subscriptions", params={"status": "active", "customer_id": subscription_data["customer_id"]}).json() == [second]
    assert client.get("/subscriptions", params={"status": "cancelled"}).json()[0]["id"] == first["id"]
    assert client.get("/subscriptions", params={"offset": 1, "limit": 1}).json() == [second]
    assert client.get("/subscriptions", params={"customer_id": 9999}).json() == []


@pytest.mark.parametrize("payload", [
    {}, {"customer_id": 1}, {"customer_id": 0, "plan_id": 1},
    {"customer_id": 1, "plan_id": -1}, {"customer_id": True, "plan_id": 1},
    {"customer_id": "1", "plan_id": 1}, {"customer_id": 1, "plan_id": 1.1},
    {"customer_id": 1, "plan_id": 1, "status": "cancelled"},
    {"customer_id": 1, "plan_id": 1, "start_date": "2026-01-01"},
])
def test_invalid_create_input_rejected(client, payload):
    assert client.post("/subscriptions", json=payload).status_code == 422
    assert client.get("/subscriptions").json() == []


@pytest.mark.parametrize("query", [
    {"offset": -1}, {"limit": 0}, {"limit": 101}, {"status": "paused"},
    {"customer_id": 0}, {"plan_id": -1},
])
def test_invalid_list_filters_rejected(client, query):
    assert client.get("/subscriptions", params=query).status_code == 422


def test_missing_subscription_returns_404(client):
    assert client.get("/subscriptions/999").status_code == 404
    assert client.post("/subscriptions/999/cancel").status_code == 404
    assert client.get("/subscriptions/0").status_code == 422


def test_concurrent_subscription_creation_creates_one_active_row(database, client, subscription_data):
    barrier = Barrier(2)
    data = SubscriptionCreate(**subscription_data)

    def create():
        with Session(database[0], expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            try:
                SubscriptionService(session).create(data)
                return "created"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert sorted(results) == ["conflict", "created"]
    with Session(database[0]) as session:
        assert len(session.scalars(select(Subscription)).all()) == 1


def test_openapi_documents_subscriptions(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/subscriptions", "/subscriptions/{subscription_id}", "/subscriptions/{subscription_id}/cancel"} <= paths.keys()
