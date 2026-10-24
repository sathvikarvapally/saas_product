from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import InputSchema, Name, OutputSchema


class CustomerCreate(InputSchema):
    name: Annotated[Name, Field(max_length=150)]
    email: Annotated[EmailStr, Field(max_length=254)]
    company_name: Annotated[Name, Field(max_length=150)] | None = None
    status: Literal["active", "inactive"] = "active"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class CustomerResponse(OutputSchema):
    id: int
    name: str
    email: str
    company_name: str | None
    status: Literal["active", "inactive"]
    created_at: datetime
