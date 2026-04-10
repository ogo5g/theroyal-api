"""Admin panel routers — aggregates all admin sub-routers."""

from fastapi import APIRouter

from app.routers.admin import clearance, kyc, plans, stats, subscriptions, users, tickets

router = APIRouter(prefix="/admin", tags=["Admin"])

router.include_router(users.router)
router.include_router(kyc.router)
router.include_router(plans.router)
router.include_router(subscriptions.router)
router.include_router(clearance.router)
router.include_router(stats.router)
router.include_router(tickets.router)

