# Assignment review

The review includes both text and embedded tables from `saas subscription.docx`.

## Verification results

- Windows/Python 3.14: all 144 automated tests passed.
- Development database upgraded to revision `39f1b5c0a712`; Alembic reports no schema differences.
- Docker Compose configuration validated and Docker image built successfully.
- A fresh isolated Docker container completed the real HTTP PowerShell walkthrough:
  invoice paid at 499.00, three payment attempts, four ledger events, subscription cancelled.
- The container's post-walkthrough Alembic check also passed. The temporary container
  was stopped and removed; its demo database did not touch development data.
- The test client emits one upstream httpx deprecation warning; tests pass.

| Requirement | Implementation/evidence |
| --- | --- |
| Separate application layers | app/api, services, repositories, models, schemas, core, db |
| ERD and responsibilities | DESIGN.md ERD, service table, repository table |
| Business-rule ownership and pattern explanation | DESIGN.md ownership table and architecture |
| Invoice/payment flows | DESIGN.md; WALKTHROUGH.md demonstration |
| Plan update/deactivation | POST/GET /plans; PATCH /plans/{plan_id} for name, description, price, currency, cycle, status |
| Customer/contact/company details | POST/GET /customers; GET details; unique normalized email, optional company_name, status |
| Subscription lifecycle | POST/GET /subscriptions; GET details; PATCH cancellation; active-plan/duplicate checks |
| Billing period fields | current_period_start/current_period_end; monthly/quarterly/yearly cycles |
| Invoice generation/details | POST /invoices/generate; GET /invoices/{invoice_id}; snapshots and overlap protection |
| Successful/failed payments | POST /payments/record; partial/full settlement, currency/overpayment checks |
| Append-only traceable ledger | Customer history; append/list repository; SQLite mutation triggers; invoice/payment references |
| At least five business-rule tests | tests cover validation, API flows, constraints, concurrency, rollback, migrations |
| Environment and run instructions | .env.example, requirements.txt, README.md |
| Docker/local setup | Dockerfile, compose.yaml, .dockerignore, README.md |
| API documentation | Swagger /docs and OpenAPI /openapi.json |
| GitHub submission | Local Git repository initialized on main; awaiting destination repository URL for upload |

## Deliberate assumptions

- SQLite is supported. Other databases require separate locking/migration verification.
- Plan cycle/status and ledger entry_type support assignment names alongside existing
  billing_interval/is_active/event_type names. Yearly maps to annual.
- Cycles are monthly, quarterly, or yearly. Arbitrary custom cycle lengths are not
  supported. Custom invoice dates are accepted at the full plan price.
- Subscriptions activate immediately; cancellation is immediate/idempotent.
- Customer contact details are email and company name; no phone/address fields.
- Invoice generation is manual. Overdue/void are stored states without a scheduler
  or lifecycle endpoint to assign them automatically.
- References are globally unique; duplicate requests return 409 instead of replaying
  earlier responses. INR/USD/EUR/GBP use two decimal places.
- Payment statuses are simulated inputs. No gateway, tax, proration, refunds,
  frontend, authentication, or RBAC is included in the assignment's base scope.

## Submission

Include app/, migrations/, tests/, scripts/, requirements.txt, alembic.ini,
pytest.ini, .env.example, Docker files, and Markdown documents. Exclude .venv,
.env, databases, and caches using .gitignore. Use the destination GitHub repository
URL as the assignment submission link once the initial commit has been uploaded.
