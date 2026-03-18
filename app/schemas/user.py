"""User response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    phone_number: str
    first_name: str
    last_name: str
    other_name: str | None = None
    role: UserRole
    is_active: bool
    is_verified: bool
    is_suspended: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    other_name: str | None = None
