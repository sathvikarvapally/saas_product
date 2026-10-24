# Verification against saas subscription.docx

Reviewed on 2026-10-25 against local commit `b184580`. This audit compares the
assignment text and all nine embedded images/tables with the implementation.
The embedded images match those inspected during the earlier implementation review.

## Verdict

The core functional requirements, six domain entities, required API operations,
and nine business rules are implemented. The project is not fully submission-complete:
there is no GitHub remote or submission URL. The service responsibility table gap
identified during the audit was closed in the documentation follow-up: explicit
per-service exclusions and corrected validation ownership are now included.
The other notes below are documented assumptions or design refinements.

## Fresh verification

- `python -m pytest -q`: 144 passed, one upstream TestClient/httpx deprecation warning.
- `python -m alembic check`: no new upgrade operations detected.
- OpenAPI inspection: all 13 required HTTP method/path combinations are present.
- `git remote -v`: empty; no remote upload has been completed.
- Docker image build, Compose configuration, and isolated real-HTTP walkthrough
  passed in the preceding review. Docker was not rebuilt or rerun for this audit.

## Functional and domain requirements

| Document requirement | Status | Evidence |
| --- | --- | --- |
| Plans: create, update, list, deactivate | Satisfied | app/api/plans.py; app/services/plan.py; tests/test_catalog_api.py; tests/test_assignment_api.py |
| Customers: create/list/details, unique email, company/contact details | Satisfied | app/schemas/customer.py; app/services/customer.py; company_name and email are supported |
| Subscriptions: create, activate, cancel, fetch, prevent duplicates | Satisfied with stated assumption | Subscriptions activate on creation; app/services/subscription.py; tests/test_subscription_api.py |
| Invoices for active subscriptions, amounts/status/billing period | Satisfied | app/services/invoice.py; app/repositories/invoice.py; tests/test_invoice_api.py |
| Successful/failed payment recording and invoice updates | Satisfied | app/services/payment.py; tests/test_payment_api.py |
| invoice_created/payment_success/payment_failure ledger events | Satisfied | app/services/ledger.py; invoice/payment service calls; ledger tests |
| Plan minimum fields | Satisfied through equivalent names | app/models/entities.py: description, updated_at, price/currency; billing_cycle/status properties map to billing_interval/is_active |
| Customer minimum fields | Satisfied | Customer model includes name, email, company_name, status, created_at |
| Subscription minimum fields | Satisfied | Subscription model includes current_period_start/end, start_date, cancelled_at, and relationships |
| Invoice minimum fields | Satisfied | Invoice model includes all listed billing fields and relationships |
| PaymentAttempt minimum fields | Satisfied | PaymentAttempt model includes provider_reference, failure_reason, status, amount/currency |
| LedgerEntry minimum fields | Satisfied through equivalent names | Ledger model has description/reference_id; entry_type property exposes stored event_type |
| Suggested customer/plan/subscription/invoice relationships | Satisfied | app/models/entities.py; tests/test_database.py relationship checks |

Monthly, quarterly, and yearly cycles are available; yearly maps to stored annual.
The document permits those cycles and does not require arbitrary custom cycle lengths.
Email and company name provide the base contact/company details; phone/address fields
are not explicitly required. Overdue/void invoice states are modeled but have no
automatic scheduler or status-management endpoint; the required API list does not
specify those operations.

## Required APIs

Every operation below is registered in the generated OpenAPI schema.

| Method | Required path | Status | Route implementation |
| --- | --- | --- | --- |
| POST | /plans | Satisfied | app/api/plans.py |
| GET | /plans | Satisfied | app/api/plans.py |
| PATCH | /plans/{plan_id} | Satisfied | app/api/plans.py |
| POST | /customers | Satisfied | app/api/customers.py |
| GET | /customers | Satisfied | app/api/customers.py |
| GET | /customers/{customer_id} | Satisfied | app/api/customers.py |
| POST | /subscriptions | Satisfied | app/api/subscriptions.py |
| GET | /subscriptions | Satisfied | app/api/subscriptions.py |
| PATCH | /subscriptions/{subscription_id}/cancel | Satisfied | app/api/assignment.py |
| POST | /invoices/generate | Satisfied | app/api/assignment.py |
| GET | /invoices/{invoice_id} | Satisfied | app/api/invoices.py |
| POST | /payments/record | Satisfied | app/api/assignment.py |
| GET | /customers/{customer_id}/ledger | Satisfied | app/api/ledger.py |

Additional nested invoice/payment endpoints and POST cancellation do not replace or
remove the required operations. Assignment request bodies include subscription_id
for invoice generation and invoice_id for recording payment.

## Nine required business rules

| Rule from section 7 | Status | Implementation and test evidence |
| --- | --- | --- |
| Plan price > 0 | Satisfied | Money schema and ck_plan_positive_price; test_invalid_plan_input_rejected_without_writes and test_plan_price_must_be_positive |
| Customer email unique | Satisfied | CustomerService precheck plus uq_customer_email; duplicate/case-normalization/database-conflict tests |
| No subscription to an inactive plan | Satisfied | SubscriptionService.create; test_inactive_plan_blocks_subscription_without_poisoning_next_request |
| No two active subscriptions to the same plan/customer | Satisfied | Service check plus partial unique index; duplicate and concurrent-creation tests |
| Invoice amount_due uses price at generation time | Satisfied | InvoiceService copies current plan.price/currency; snapshot tests, including public plan PATCH |
| Successful payment cannot exceed unpaid balance | Satisfied | PaymentService check inside SQLite write reservation; overpayment and concurrent-payment tests |
| Full payment -> paid; partial payment -> partially_paid | Satisfied | InvoiceRepository.apply_payment; settlement and exact Decimal-sum tests |
| Failed payment does not increase amount_paid | Satisfied | PaymentService changes invoice only on success; failure tests for issued/partially_paid invoices |
| Ledger append-only and traceable through reference_id | Satisfied | Repository append/list interface; SQLite UPDATE/DELETE rejection triggers; invoice:<id>/payment:<id> references; direct-SQL immutability tests |

## LLD, learning goals, and submission deliverables

| Requirement | Status | Evidence or remaining work |
| --- | --- | --- |
| Separation of routes/services/repositories/models/schemas/config/database | Substantially satisfied | Dedicated packages; two request-adapter classes are still declared in app/api/assignment.py rather than app/schemas |
| Separate invoice/subscription/payment/ledger responsibilities | Satisfied | Distinct services and repositories; invoice/payment transactions compose LedgerService |
| Dependency management | Satisfied at request/session level | app/api/dependencies.py injects services/sessions; repositories are constructed inside services rather than independently injected |
| Repository and service-layer patterns | Satisfied | Database access in repositories; business workflows/transactions in services; DESIGN.md architecture |
| Environment variables and .env.example | Satisfied | app/core/config.py; .env.example; README.md |
| ERD | Satisfied | DESIGN.md, Entities and relationships |
| Service responsibility table: owns and should not do | Satisfied after follow-up | DESIGN.md now includes per-service responsibilities, exclusions, repositories, and corrected validation ownership |
| Repository responsibility table: entities/methods | Satisfied | DESIGN.md, Repository responsibilities |
| Business-rule ownership | Satisfied | DESIGN.md ownership table |
| At least one design pattern and reason | Satisfied | DESIGN.md repository/service-layer explanation |
| Invoice and payment flows | Satisfied | DESIGN.md workflows and implemented service transactions |
| Class diagram | Optional, omitted | Document explicitly labels it optional |
| README setup/API list/assumptions/limitations | Satisfied | README.md plus linked DESIGN.md/REVIEW.md |
| At least five important business-rule tests | Satisfied | 144 passing cases across six test modules |
| Dockerfile/Compose or clear local commands | Satisfied | Dockerfile, compose.yaml, README.md; previously verified container walkthrough |
| Swagger or Postman | Satisfied, optional | Swagger at /docs and OpenAPI at /openapi.json |
| GitHub repository link with completed implementation | Pending | Local main commit exists, but no remote repository is configured |

## Items to finish or improve

1. Completed: service exclusions and schema validation ownership added to DESIGN.md;
   README now has explicit assumptions, limitations, and submission-file sections.
2. Create/upload to a GitHub repository and retain the resulting submission URL.
3. For stricter layer separation, move InvoiceGenerateRequest and PaymentRecordRequest
   from app/api/assignment.py into app/schemas. This does not block current behavior.
4. Swagger request schemas currently show billing_interval/is_active, while the
   accepted billing_cycle/status aliases are explained only in Markdown. Expose
   those aliases/examples in OpenAPI for clearer assignment-facing API documentation.

The document explicitly excludes a real payment gateway, frontend UI, complex tax,
proration, and authentication/RBAC from base scope. Their absence is not a missing
assignment requirement. No application code was changed during this verification.
