"""Plan schemas — request/response for savings plans."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator


class PlanResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    weekly_amount: Decimal
    duration_weeks: int
    registration_fee: Decimal
    clearance_fee: Decimal
    return_rate: Decimal
    penalty_type: str
    penalty_value: Decimal
    minimum_wallet_balance: Decimal
    max_subscribers: int | None = None
    current_subscribers: int
    status: str
    referral_code_release_week: int
    referral_code_validity_weeks: int
    downline_qualification_week: int
    referral_bonus_type: str
    referral_bonus_value: Decimal
    referral_required_for_payout: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanCreateRequest(BaseModel):
    name: str
    description: str
    weekly_amount: Decimal
    duration_weeks: int
    registration_fee: Decimal
    clearance_fee: Decimal = Decimal("0.00")
    return_rate: Decimal
    penalty_type: str
    penalty_value: Decimal
    minimum_wallet_balance: Decimal = Decimal("0.00")
    max_subscribers: int | None = None
    referral_code_release_week: int = 1
    referral_code_validity_weeks: int = 1
    downline_qualification_week: int = 1
    referral_bonus_type: str = "fixed"
    referral_bonus_value: Decimal = Decimal("0.00")
    referral_required_for_payout: bool = False

    @field_validator(
        "weekly_amount", "registration_fee", "clearance_fee",
        "penalty_value", "minimum_wallet_balance", "referral_bonus_value",
    )
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

    @model_validator(mode="after")
    def validate_referral_weeks(self) -> "PlanCreateRequest":
        if self.referral_code_release_week >= self.duration_weeks:
            raise ValueError("referral_code_release_week must be less than duration_weeks")
        if self.downline_qualification_week > self.duration_weeks:
            raise ValueError("downline_qualification_week must not exceed duration_weeks")
        return self


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    weekly_amount: Decimal | None = None
    duration_weeks: int | None = None
    registration_fee: Decimal | None = None
    clearance_fee: Decimal | None = None
    return_rate: Decimal | None = None
    penalty_type: str | None = None
    penalty_value: Decimal | None = None
    minimum_wallet_balance: Decimal | None = None
    max_subscribers: int | None = None
    status: str | None = None
    referral_code_release_week: int | None = None
    referral_code_validity_weeks: int | None = None
    downline_qualification_week: int | None = None
    referral_bonus_type: str | None = None
    referral_bonus_value: Decimal | None = None
    referral_required_for_payout: bool | None = None
