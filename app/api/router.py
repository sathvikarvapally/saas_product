from fastapi import APIRouter

from app.api.customers import router as customers_router
from app.api.plans import router as plans_router
from app.api.subscriptions import router as subscriptions_router
from app.api.invoices import router as invoices_router
from app.api.ledger import router as ledger_router
from app.api.payments import router as payments_router
from app.api.assignment import router as assignment_router

router = APIRouter()
router.include_router(assignment_router)
router.include_router(plans_router)
router.include_router(customers_router)
router.include_router(subscriptions_router)
router.include_router(invoices_router)
router.include_router(ledger_router)
router.include_router(payments_router)


@router.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Return application liveness; this does not check database readiness."""
    return {"status": "ok"}
