"""Onboarding request schemas."""

import re

from pydantic import BaseModel, field_validator

from app.schemas.auth import normalize_phone


class BasicInfoRequest(BaseModel):
    first_name: str
    last_name: str
    other_name: str | None = None
    phone_number: str
    date_of_birth: str  # YYYY-MM-DD
    address: str

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Name must be at most 100 characters")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = normalize_phone(v)
        if not re.match(r"^\+234[0-9]{10}$", normalized):
            raise ValueError("Invalid Nigerian phone number")
        return normalized

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date of birth must be in YYYY-MM-DD format")
        return v

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Address must be at least 10 characters")
        return v


class NINSubmitRequest(BaseModel):
    nin: str

    @field_validator("nin")
    @classmethod
    def validate_nin(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\d{11}$", v):
            raise ValueError("NIN must be exactly 11 digits")
        return v


class BVNSubmitRequest(BaseModel):
    bvn: str

    @field_validator("bvn")
    @classmethod
    def validate_bvn(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\d{11}$", v):
            raise ValueError("BVN must be exactly 11 digits")
        return v


class ProfilePhotoRequest(BaseModel):
    image_url: str

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("Must be a valid URL")
        return v
