"""Standard API response envelopes."""

from typing import Any

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: str = "Request successful"


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
    message: str = "An error occurred"


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    pages: int


class PaginatedResponse(BaseModel):
    success: bool = True
    data: list[Any]
    pagination: PaginationMeta
