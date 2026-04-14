"""User response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import OnboardingStep, UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    phone_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    other_name: str | None = None
    date_of_birth: str | None = None
    address: str | None = None
    profile_image_url: str | None = None
    role: UserRole
    onboarding_step: OnboardingStep
    is_active: bool
    is_verified: bool
    is_suspended: bool
    created_at: datetime
    updated_at: datetime
    has_bank_account: bool | None = None
    has_proof_of_address: bool | None = None
    kyc_status: str | None = None

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    other_name: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = None
    address: str | None = None
