"""Reusable pagination dependency and response builder."""

from dataclasses import dataclass
from math import ceil

from fastapi import Query


@dataclass
class PaginationParams:
    page: int
    per_page: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """FastAPI dependency for pagination query params."""
    return PaginationParams(page=page, per_page=per_page)


def paginated_response(
    data: list, total: int, pagination: PaginationParams
) -> dict:
    """Build a pagination envelope for list responses."""
    return {
        "success": True,
        "data": data,
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": total,
            "pages": ceil(total / pagination.per_page) if pagination.per_page else 0,
        },
    }
