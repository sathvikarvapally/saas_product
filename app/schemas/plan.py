from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from app.schemas.common import InputSchema, Name, OutputSchema

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Currency = Literal["INR", "USD", "EUR", "GBP"]
BillingInterval = Literal["monthly", "quarterly", "annual"]


class PlanInput(InputSchema):
    @model_validator(mode="before")
    @classmethod
    def assignment_field_names(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if "billing_cycle" in value:
            if "billing_interval" in value:
                raise ValueError("Use billing_cycle or billing_interval, not both")
            cycle = value.pop("billing_cycle")
            value["billing_interval"] = "annual" if cycle == "yearly" else cycle
        if "status" in value:
            if "is_active" in value:
                raise ValueError("Use status or is_active, not both")
            status = value.pop("status")
            if status not in ("active", "inactive"):
                raise ValueError("status must be active or inactive")
            value["is_active"] = status == "active"
        return value


class PlanCreate(PlanInput):
    name: Annotated[Name, Field(max_length=100)]
    price: Money
    currency: Currency
    billing_interval: BillingInterval = "monthly"
    is_active: StrictBool = True
    description: Annotated[str, Field(max_length=500)] | None = None


class PlanUpdate(PlanInput):
    name: Annotated[Name, Field(max_length=100)] | None = None
    price: Money | None = None
    currency: Currency | None = None
    billing_interval: BillingInterval | None = None
    is_active: StrictBool | None = None
    description: Annotated[str, Field(max_length=500)] | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one plan field")
        for field in self.model_fields_set - {"description"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class PlanResponse(OutputSchema):
    id: int
    name: str
    description: str | None
    price: Decimal
    currency: str
    billing_interval: str
    is_active: bool
    billing_cycle: str
    status: Literal["active", "inactive"]
    created_at: datetime
    updated_at: datetime
