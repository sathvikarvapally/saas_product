import pytest

from app.repositories.customer import CustomerRepository


PLAN = {"name": "Starter", "price": "499.00", "currency": "INR"}
CUSTOMER = {"name": "Sathvik", "email": "sathvik@example.com"}


def test_create_read_and_deactivate_plan(client):
    response = client.post("/plans", json={**PLAN, "name": " Starter "})
    assert response.status_code == 201
    plan = response.json()
    assert plan["name"] == "Starter"
    assert plan["price"] == "499.00"
    assert plan["billing_interval"] == "monthly"
    assert plan["is_active"] is True
    assert plan["created_at"].endswith("Z")
    assert client.get(f"/plans/{plan['id']}").json() == plan
    response = client.patch(f"/plans/{plan['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["price"] == "499.00"
    assert client.get("/plans").json() == [response.json()]
    assert client.patch(f"/plans/{plan['id']}", json={"is_active": True}).json()["is_active"] is True


@pytest.mark.parametrize("field,value", [
    ("price", "0"), ("price", "-1"), ("price", "1.001"),
    ("price", "10000000000.00"), ("price", "NaN"), ("price", "Infinity"),
    ("name", "  "), ("name", "x" * 101), ("currency", "XYZ"),
    ("currency", "inr"), ("billing_interval", "weekly"), ("is_active", "false"),
])
def test_invalid_plan_input_rejected_without_writes(client, field, value):
    response = client.post("/plans", json={**PLAN, field: value})
    assert response.status_code == 422
    assert client.get("/plans").json() == []


@pytest.mark.parametrize("payload", [{}, {"is_active": None}, {"is_active": "false"}, {"is_active": False, "customer_id": 1}])
def test_plan_patch_rejects_invalid_or_unsupported_fields(client, payload):
    plan_id = client.post("/plans", json=PLAN).json()["id"]
    assert client.patch(f"/plans/{plan_id}", json=payload).status_code == 422
    assert client.get(f"/plans/{plan_id}").json()["is_active"] is True


def test_create_customer_normalizes_email_and_name(client):
    response = client.post("/customers", json={"name": " Sathvik ", "email": " Sathvik@EXAMPLE.COM "})
    assert response.status_code == 201
    customer = response.json()
    assert customer["name"] == "Sathvik"
    assert customer["email"] == "sathvik@example.com"
    assert client.get(f"/customers/{customer['id']}").json() == customer
    assert client.get("/customers").json() == [customer]


def test_duplicate_email_is_case_insensitive_and_returns_conflict(client):
    assert client.post("/customers", json=CUSTOMER).status_code == 201
    response = client.post("/customers", json={**CUSTOMER, "email": "SATHVIK@EXAMPLE.COM"})
    assert response.status_code == 409
    assert response.json() == {"detail": "A customer with this email already exists"}
    assert len(client.get("/customers").json()) == 1
    # A failed request must not poison the following transaction.
    assert client.post("/customers", json={**CUSTOMER, "email": "another@example.com"}).status_code == 201


def test_duplicate_detected_by_database_is_translated_and_rolled_back(client, monkeypatch):
    assert client.post("/customers", json=CUSTOMER).status_code == 201
    lookup = CustomerRepository.get_by_email
    calls = 0

    def miss_initial_check(self, email):
        nonlocal calls
        calls += 1
        return None if calls == 1 else lookup(self, email)

    monkeypatch.setattr(CustomerRepository, "get_by_email", miss_initial_check)
    assert client.post("/customers", json=CUSTOMER).status_code == 409
    assert len(client.get("/customers").json()) == 1


@pytest.mark.parametrize("payload", [
    {"name": "Test", "email": "invalid"},
    {"name": " ", "email": "test@example.com"},
    {"name": "x" * 151, "email": "test@example.com"},
    {"name": "Test", "email": "test@example.com", "id": 123},
])
def test_invalid_customer_input_rejected(client, payload):
    assert client.post("/customers", json=payload).status_code == 422
    assert client.get("/customers").json() == []


@pytest.mark.parametrize("path", ["/plans/999", "/customers/999"])
def test_missing_entity_returns_404(client, path):
    assert client.get(path).status_code == 404


def test_patch_missing_plan_returns_404(client):
    assert client.patch("/plans/999", json={"is_active": False}).status_code == 404


@pytest.mark.parametrize("path,payload", [("/plans", PLAN), ("/customers", CUSTOMER)])
def test_lists_have_stable_pagination(client, path, payload):
    assert client.get(path).json() == []
    ids = []
    for i in range(3):
        values = {**payload, "name": f"Item {i}"}
        if path == "/customers":
            values["email"] = f"customer{i}@example.com"
        ids.append(client.post(path, json=values).json()["id"])
    assert [item["id"] for item in client.get(path, params={"offset": 1, "limit": 1}).json()] == ids[1:2]
    assert client.get(path, params={"offset": 3}).json() == []
    for query in ({"offset": -1}, {"limit": 0}, {"limit": 101}):
        assert client.get(path, params=query).status_code == 422


def test_openapi_includes_catalog_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/plans", "/plans/{plan_id}", "/customers", "/customers/{customer_id}"} <= paths.keys()
