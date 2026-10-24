from datetime import datetime

from alembic import command
from sqlalchemy import text


def test_assignment_paths_and_profile_fields_work_together(client):
    plan_response = client.post('/plans', json={
        'name': 'Quarterly', 'description': 'Business plan', 'price': '499.00',
        'currency': 'INR', 'billing_cycle': 'quarterly', 'status': 'active',
    })
    assert plan_response.status_code == 201
    plan = plan_response.json()
    assert plan['billing_cycle'] == 'quarterly'
    assert plan['status'] == 'active'
    assert plan['updated_at'].endswith('Z')
    customer = client.post('/customers', json={
        'name': 'Test', 'email': 'test@example.com', 'company_name': ' Test Company ',
    }).json()
    assert customer['company_name'] == 'Test Company'
    assert customer['status'] == 'active'
    subscription = client.post('/subscriptions', json={'customer_id': customer['id'], 'plan_id': plan['id']}).json()
    assert subscription['current_period_start'] == subscription['start_date']
    assert subscription['current_period_end'] > subscription['start_date']
    invoice_response = client.post('/invoices/generate', json={'subscription_id': subscription['id']})
    assert invoice_response.status_code == 201
    invoice = invoice_response.json()
    entry = client.get(f"/customers/{customer['id']}/ledger").json()[0]
    assert entry['entry_type'] == entry['event_type'] == 'invoice_created'
    assert entry['description']
    payment = client.post('/payments/record', json={
        'invoice_id': invoice['id'], 'amount': '499.00', 'currency': 'INR',
        'status': 'success', 'provider_reference': 'assignment-demo',
    })
    assert payment.status_code == 201
    assert payment.json()['invoice']['status'] == 'paid'
    assert client.patch(f"/subscriptions/{subscription['id']}/cancel").status_code == 200


def test_general_plan_patch_and_yearly_alias(client):
    plan = client.post('/plans', json={'name': 'Starter', 'price': '100.00', 'currency': 'INR'}).json()
    response = client.patch(f"/plans/{plan['id']}", json={
        'name': 'Pro', 'price': '200.00', 'currency': 'USD',
        'billing_cycle': 'yearly', 'status': 'inactive', 'description': 'New description',
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated['name'] == 'Pro'
    assert updated['price'] == '200.00'
    assert updated['currency'] == 'USD'
    assert updated['billing_interval'] == 'annual'
    assert updated['billing_cycle'] == 'yearly'
    assert updated['is_active'] is False
    assert updated['description'] == 'New description'
    assert updated['updated_at'] >= plan['updated_at']
    assert client.patch(f"/plans/{plan['id']}", json={'description': None}).json()['description'] is None
    for payload in ({'price': '0'}, {'price': None}, {'currency': None}, {'status': 'invalid'},
                    {'is_active': True, 'status': 'active'}, {'billing_cycle': 'yearly', 'billing_interval': 'monthly'}):
        assert client.patch(f"/plans/{plan['id']}", json=payload).status_code == 422


def test_plan_patch_preserves_prior_invoice_snapshot(client):
    customer = client.post('/customers', json={'name': 'Test', 'email': 'test@example.com'}).json()
    plan = client.post('/plans', json={'name': 'Starter', 'price': '100.00', 'currency': 'INR'}).json()
    subscription = client.post('/subscriptions', json={'customer_id': customer['id'], 'plan_id': plan['id']}).json()
    first = client.post('/invoices/generate', json={'subscription_id': subscription['id']}).json()
    client.patch(f"/plans/{plan['id']}", json={'price': '200.00', 'currency': 'USD'})
    second = client.post('/invoices/generate', json={'subscription_id': subscription['id'], 'period_start': first['period_end']}).json()
    assert second['amount_due'] == '200.00'
    assert second['currency'] == 'USD'
    assert client.get(f"/invoices/{first['id']}").json() == first
    current = client.get(f"/subscriptions/{subscription['id']}").json()
    assert current['current_period_start'] == second['period_start']
    assert current['current_period_end'] == second['period_end']


def test_assignment_paths_are_documented_and_validate_ids(client):
    paths = client.get('/openapi.json').json()['paths']
    assert 'patch' in paths['/subscriptions/{subscription_id}/cancel']
    assert 'post' in paths['/invoices/generate']
    assert 'post' in paths['/payments/record']
    assert client.post('/invoices/generate', json={'subscription_id': 0}).status_code == 422
    assert client.post('/invoices/generate', json={'subscription_id': 9999}).status_code == 404


def test_assignment_migration_preserves_existing_records(database):
    engine, config = database
    command.downgrade(config, '2a6cb94e8d10')
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO customers (id, name, email) VALUES (1, 'Test', 'test@example.com')"))
        connection.execute(text("INSERT INTO plans (id, name, price, currency, billing_interval) VALUES (1, 'Annual', 10, 'INR', 'annual')"))
        connection.execute(text("INSERT INTO subscriptions (id, customer_id, plan_id, start_date) VALUES (1, 1, 1, '2024-02-29 00:00:00')"))
    command.upgrade(config, 'head')
    command.check(config)
    with engine.connect() as connection:
        row = connection.execute(text('SELECT current_period_start, current_period_end FROM subscriptions WHERE id = 1')).one()
        assert datetime.fromisoformat(row[0]) == datetime(2024, 2, 29)
        assert datetime.fromisoformat(row[1]) == datetime(2025, 2, 28)
        assert connection.execute(text('SELECT status FROM customers WHERE id = 1')).scalar_one() == 'active'
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
