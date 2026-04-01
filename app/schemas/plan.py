"""Plan schemas — request/response for savings plans."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class PlanResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    weekly_amount: Decimal
    duration_weeks: int
    start_commission: Decimal
    return_rate: Decimal
    penalty_type: str
    penalty_value: Decimal
    minimum_wallet_balance: Decimal
    max_subscribers: int | None = None
    current_subscribers: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanCreateRequest(BaseModel):
    name: str
    description: str
    weekly_amount: Decimal
    duration_weeks: int
    start_commission: Decimal
    return_rate: Decimal
    penalty_type: str
    penalty_value: Decimal
    minimum_wallet_balance: Decimal = Decimal("0.00")
    max_subscribers: int | None = None

    @field_validator("weekly_amount", "start_commission", "penalty_value", "minimum_wallet_balance")
    @classmethod
    def validate_positive_decimal(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Amount must be a positive number")
        return v

    @field_validator("return_rate")
    @classmethod
    def validate_return_rate(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 100:
            raise ValueError("Return rate must be between 0 and 100")
        return v

    @field_validator("duration_weeks")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Duration must be at least 1 week")
        return v


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    weekly_amount: Decimal | None = None
    duration_weeks: int | None = None
    start_commission: Decimal | None = None
    return_rate: Decimal | None = None
    penalty_type: str | None = None
    penalty_value: Decimal | None = None
    minimum_wallet_balance: Decimal | None = None
    max_subscribers: int | None = None
    status: str | None = None
