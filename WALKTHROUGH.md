# End-to-end walkthrough

## Start the API

From `saas_product` with the virtual environment active:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Alternatively, use `docker compose up --build -d`. Both expose Swagger at
http://127.0.0.1:8000/docs; choose one server at a time on port 8000.

## Run the demonstration

Open a second PowerShell terminal in `saas_product`:

```powershell
.\scripts\walkthrough.ps1
```

For another local port:

```powershell
.\scripts\walkthrough.ps1 -BaseUrl 'http://127.0.0.1:8137'
```

The script sends real HTTP requests and creates fresh demo records with unique
emails and references each run. It checks the assignment's required paths:

| Step | Request | Expected result |
| --- | --- | --- |
| 1 | POST /plans | Active monthly INR plan priced 499.00 |
| 2 | POST /customers | Customer with unique email and company details |
| 3 | POST /subscriptions | Active subscription with billing period |
| 4 | POST /invoices/generate | Issued invoice for 499.00 and one ledger event |
| 5 | POST /payments/record, success 200.00 | Partially paid invoice, amount_paid 200.00 |
| 6 | POST /payments/record, failed 299.00 | Failed attempt recorded, amount_paid still 200.00 |
| 7 | POST /payments/record, success 299.00 | Paid invoice, amount_paid 499.00 |
| 8 | GET /customers/{id}/ledger | Four events: invoice, success, failure, success |
| 9 | PATCH /subscriptions/{id}/cancel | Cancelled subscription with retained history |

The result prints PASS, the created IDs, invoice status/total, three payment attempts,
four ledger events, and cancellation status. Use the IDs in Swagger to inspect the
records. A failed assertion stops the script with an error.

## Verify errors in Swagger

- Submit a zero-price plan: 422.
- Repeat a customer email: 409.
- Create another active subscription to the same plan before cancellation: 409.
- Repeat invoice generation for the first period: 409.
- Reuse a payment provider reference: 409.
- Pay a currency different from the invoice: 409.
- Submit an additional successful amount on the paid invoice: 409.

After cancellation, a new subscription to the same active plan is allowed and gets
a new ID. The paid invoice and ledger history remain available.

## Automated checks

```powershell
python -m pytest -q
python -m alembic check
```

Tests use temporary databases and include concurrent writes, rollback on ledger
failure, schema constraints, and migration data preservation.
