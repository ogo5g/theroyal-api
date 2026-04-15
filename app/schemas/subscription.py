"""Subscription schemas — request/response."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class SubscribeRequest(BaseModel):
    plan_code: str
    referral_code: str | None = None


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    sid: str
    plan_code: str | None = None
    plan_name: str | None = None
    status: str
    weekly_amount: Decimal
    total_expected: Decimal
    total_paid: Decimal
    settlement_amount: Decimal
    weeks_paid: int
    current_streak: int
    longest_streak: int
    missed_payments: int
    start_date: date
    end_date: date
    last_payment_date: date | None = None
    next_due_date: date | None = None
    referral_code: str | None = None         # None when not yet available
    referral_code_available_at: date | None = None
    referral_code_expires_at: date | None = None
    is_referral_code_active: bool = False
    commission_paid: bool
    penalty_count: int
    clearance_submitted: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleItemResponse(BaseModel):
    id: uuid.UUID
    week_number: int
    due_date: date
    amount: Decimal
    status: str
    paid_at: datetime | None = None
    transaction_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class DownlineStatusResponse(BaseModel):
    sid: str
    weeks_paid: int
    qualification_week: int
    is_qualified: bool
    status: str


class ReferralInfoResponse(BaseModel):
    referral_code: str | None
    available_at: date | None
    expires_at: date | None
    is_active: bool
    downlines: list[DownlineStatusResponse] = []
