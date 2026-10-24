# SubLedger

A Python billing backend built with FastAPI, SQLAlchemy, and SQLite.
See [DESIGN.md](DESIGN.md) for the entities, architecture, and billing flows.
See [WALKTHROUGH.md](WALKTHROUGH.md) for a complete demonstration and
[REVIEW.md](REVIEW.md) for assignment coverage.

## Current status

The application skeleton, configuration, database sessions, six billing models,
database migrations, and health endpoint are implemented. Plans, customers,
subscriptions, and invoices have schemas, repositories, services, and working APIs.
Invoice generation appends a ledger event atomically, and customer ledger history
is available. Payment recording supports partial/full payments, failed attempts,
currency checks, unique provider references, and atomic ledger events.

## Run locally with PowerShell

From the workspace root, create the virtual environment if needed:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
cd saas_product
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

If the environment is already active and dependencies are installed, start at
`cd saas_product`. Copy `.env.example` only if you have not configured `.env` yet.

- Health: http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

The SQLite path is relative to the working directory. Run commands from
`saas_product` to keep configuration and the eventual database in this folder.
`/health` reports application liveness, not database connectivity.

## Layout

```text
app/
  main.py          FastAPI entrypoint
  api/             HTTP routes
  core/            Environment configuration
  db/              Base model, engine, session dependency
  models/          Six billing entities and their relationships
  schemas/         Input and output contracts
  repositories/    Persistence operations
  services/        Business logic and transactions
```

## Database and checks

Run these from `saas_product`, with the virtual environment active:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest -q
```

Migrations create `subledger.db` using the configured SQLite URL. Starting the API
does not automatically create or migrate tables. Tests migrate separate temporary
databases and leave your development database untouched.

The schema enforces positive amounts, normalized unique customer emails, a single
active subscription per customer/plan, valid invoice balances/statuses, and foreign
keys. SQLite triggers block updates and deletes on ledger entries. Use Alembic to
create the schema so these triggers are installed. SQLite is the supported database
at this stage; other database engines require separate migration verification and
equivalent ledger protection.

Datetime values supplied through models must be timezone-aware and are returned in
UTC. Money uses Decimal with `Numeric(12, 2)`. SQLite does not enforce a fixed monetary
scale internally; API validation and payment arithmetic must enforce two decimal
places. Plan and payment schemas enforce positive amounts with at most two decimal
places and ten integer digits. Payment arithmetic uses Decimal.

## Available APIs

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Application liveness |
| POST | `/plans` | Create plan; returns 201 |
| GET | `/plans` | List plans, including inactive plans |
| GET | `/plans/{plan_id}` | Get plan |
| PATCH | `/plans/{plan_id}` | Update name, description, price, currency, cycle, or activation |
| POST | `/customers` | Create customer; returns 201 |
| GET | `/customers` | List customers |
| GET | `/customers/{customer_id}` | Get customer |
| POST | `/subscriptions` | Create active subscription; returns 201 |
| GET | `/subscriptions` | List subscriptions with optional filters |
| GET | `/subscriptions/{subscription_id}` | Get subscription |
| POST | `/subscriptions/{subscription_id}/cancel` | Cancel immediately; returns 200 |
| PATCH | `/subscriptions/{subscription_id}/cancel` | Required assignment cancellation path |
| POST | `/subscriptions/{subscription_id}/invoices` | Generate invoice and ledger event; returns 201 |
| GET | `/invoices/{invoice_id}` | Retrieve invoice |
| POST | `/invoices/generate` | Generate invoice with subscription_id in the body |
| POST | `/payments/record` | Record attempt with invoice_id in the body |
| POST | `/invoices/{invoice_id}/payments` | Record payment attempt and return updated invoice; returns 201 |
| GET | `/invoices/{invoice_id}/payments` | List payment attempts |
| GET | `/customers/{customer_id}/ledger` | List customer ledger events |

List endpoints accept `offset` (default 0) and `limit` (default 20, maximum 100).
Results are arrays ordered by ID. A missing record returns 404, duplicate customer
email returns 409, and invalid request data returns 422. Unknown input fields are
rejected. Customer emails are trimmed and lowercased before uniqueness checks.

In Swagger UI at http://127.0.0.1:8000/docs, expand an endpoint, select **Try it out**,
enter one of the following bodies, and select **Execute**.

Create a plan with `POST /plans`:

```json
{
  "name": "Starter",
  "price": "499.00",
  "currency": "INR",
  "billing_interval": "monthly",
  "is_active": true
}
```

Supported currencies are INR, USD, EUR, and GBP. Billing intervals are monthly,
quarterly, and annual. Assignment field `billing_cycle` is also accepted, with
`yearly` mapped to `annual`. Plan `status` (active/inactive) can replace `is_active`;
send one naming convention per field. Responses contain both names. Descriptions
are optional, and `updated_at` records plan edits. Send money as decimal strings;
responses also serialize money as strings.
Deactivate a plan using `PATCH /plans/{plan_id}` with `{"is_active": false}`.
It also accepts price, currency, billing cycle, name, and description. Existing
invoices retain their original amounts and currency after plan edits.

Create a customer with `POST /customers`:

```json
{
  "name": "Sathvik",
  "email": "sathvik@example.com",
  "company_name": "Example Company"
}
```

The API currently has no authentication and is intended for local development.

## Try subscriptions

Create a plan and customer first, then use their returned IDs in `POST /subscriptions`:

```json
{
  "customer_id": 1,
  "plan_id": 1
}
```

IDs must be positive JSON integers. The server sets the active status and UTC start
time and initial `current_period_start`/`current_period_end`. Generating a later invoice
updates the period; earlier historical billing does not move it backward.
A missing customer or plan returns 404. An inactive plan or an existing active
subscription for the same customer and plan returns 409.

`GET /subscriptions` accepts `customer_id`, `plan_id`, and `status` (`active` or
`cancelled`), together with `offset` and `limit`. Filters combine. An unmatched filter
returns an empty list.

Call `POST /subscriptions/{subscription_id}/cancel` without a request body to cancel.
Repeating the call returns the same cancelled subscription and original cancellation
timestamp. The record stays available as history. A new subscription to the same
plan is allowed after cancellation if the plan is still active. Deactivating a plan
preserves existing subscriptions and still allows them to be cancelled. Cancellation
does not yet trigger invoices, refunds, or ledger events.

SQLite subscription writes acquire a write reservation before checking state, so
concurrent create/cancel operations serialize. The partial unique index is an
additional safeguard against duplicate active subscriptions.

## Try invoices and ledger history

Call `POST /subscriptions/{subscription_id}/invoices` with no body or `{}` for the
first invoice. It starts at the subscription start timestamp. The end is one calendar
month, quarter, or year later according to the plan, clamping invalid days to the last day of
the target month. The default due date is seven days after the period start.

The invoice stores the plan's current price and currency, starts in `issued` status
with `amount_paid` zero, and appends an `invoice_created` ledger event referencing
`invoice:<invoice_id>`. Either both records commit or neither does.

For later invoices, provide `period_start` equal to the previous invoice's
`period_end`. You can also specify `period_end` and `due_date`:

```json
{
  "period_start": "2026-11-25T00:00:00Z",
  "period_end": "2026-12-25T00:00:00Z",
  "due_date": "2026-12-02T00:00:00Z"
}
```

Use dates appropriate to your subscription. Supplied timestamps must include a
timezone and are normalized to UTC. `period_end` requires `period_start`, the end
must follow the start, the start cannot precede subscription creation, and the due
date cannot precede the period start. Invalid dates return 422. Custom periods are
charged the full plan price; there is no proration or requirement that dates match
today. An omitted start always selects the first period; it does not advance it.
If you want a specific monthly billing day after a short month, supply the desired
`period_end`; otherwise the next boundary is computed from the supplied start.

Overlapping periods for the same subscription return 409, including a repeated first
invoice request. Periods are treated as [start, end), allowing adjacent periods.
SQLite write serialization protects the overlap check during concurrent requests.
Cancelled subscriptions cannot generate invoices. Plan deactivation still permits
invoicing an existing active subscription. Later plan edits do not change saved
invoices or ledger entries.

Read an invoice using `GET /invoices/{invoice_id}`. Read its customer's ledger using
`GET /customers/{customer_id}/ledger`, with optional `offset` and `limit`.
A known customer without events returns `[]`; an unknown customer returns 404.
The ledger is an event history, not a computed account balance. Successful and
failed payment attempts append `payment_success` and `payment_failure` events.

## Try payments

Run `python -m alembic upgrade head` before using payment endpoints. The second
migration makes provider references unique across all payment attempts. If an
older database contains duplicate references, the migration fails without deleting
those rows; resolve the duplicate references before retrying the migration.

Record a successful partial payment with `POST /invoices/{invoice_id}/payments`:

```json
{
  "amount": "200.00",
  "currency": "INR",
  "status": "success",
  "provider_reference": "demo-payment-001"
}
```

The response includes `payment_attempt` and the updated `invoice`. For a 499.00
invoice, the remaining amount is 299.00 and the status is `partially_paid`. Recording
299.00 with a new reference changes the status to `paid`. Additional successful
payments exceeding the remaining amount return 409 without creating an attempt
or ledger event. Currency must match the invoice, otherwise the response is 409.

Record a failed payment:

```json
{
  "amount": "200.00",
  "currency": "INR",
  "status": "failed",
  "provider_reference": "demo-payment-002",
  "failure_reason": "Card declined"
}
```

A failed attempt returns 201 because the attempt was recorded. It requires a
nonblank failure reason and leaves invoice amount_paid and status unchanged.
Success requests cannot include a failure reason. Invalid inputs return 422.
Failed amounts may exceed the remaining balance because no money is applied;
failed attempts may also be recorded against paid invoices. Draft invoices reject
all payment attempts with 409; void invoices also reject attempts. Overdue invoices
are payable, but no automatic overdue scheduler or void endpoint is included.
Existing invoices remain payable after cancellation.

References are trimmed, case-sensitive, and unique globally, including failed
attempts. Reusing a reference returns 409 even for an identical request. Inspect
`GET /invoices/{invoice_id}/payments` after a lost response before submitting another
attempt. A retry of a failed attempt uses a new reference. This is duplicate
rejection, not replay of a previous success response.

Payment, invoice changes, and a ledger event referencing `payment:<attempt_id>`
commit together. SQLite serializes payment writes before checking the balance,
preventing concurrent requests from overpaying. The list endpoint uses the same
`offset` and `limit` parameters as other lists and includes success/failed history.
Payment status is supplied for simulation; no payment provider is contacted.

## Docker

With Docker running, execute from `saas_product`:

```powershell
docker compose up --build -d
docker compose ps
```

Open http://127.0.0.1:8000/docs. The container migrates before starting the API,
runs as a non-root user, and stores SQLite in the `subledger-data` named volume.
Stop a local API on port 8000 before starting Compose on the same port.

```powershell
docker compose down
```

This stops the application while keeping its database volume for the next start.
The Docker database is separate from local `subledger.db`.

## Assumptions

- SQLite is the supported database, with UTC timestamps and two-decimal monetary
  values for INR, USD, EUR, and GBP.
- Subscriptions activate immediately. Cancellation preserves invoices and payment history.
- Billing cycles are monthly, quarterly, or yearly. Invoice generation is manual;
  custom billing periods use the full plan price without proration.
- Payment status is simulated. Provider references are globally unique; duplicate
  requests return 409 rather than replaying the original response.
- Ledger entries record billing events rather than a double-entry account balance.

## Limitations

- No real payment gateway, automatic charging, taxes, refunds, frontend, authentication,
  or RBAC is included in the assignment's base scope.
- Overdue/void invoice states are supported in storage; no scheduler or status-management
  endpoint assigns those states automatically.
- Other database engines need separate locking, migration, and ledger-protection verification.

## Submission files

- This README contains setup commands, the API list, assumptions, and limitations.
- DESIGN.md contains the ERD, service and repository tables, rule ownership, pattern
  explanation, invoice flow, and payment flow.
- tests/ contains business-rule tests; run `python -m pytest -q`.
- Dockerfile and compose.yaml provide container setup; local setup is documented above.
- Swagger is available at `/docs`; OpenAPI is available at `/openapi.json`.
- A GitHub submission URL is pending until the local project is uploaded to a repository.
