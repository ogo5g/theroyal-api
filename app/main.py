"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import async_session_factory, engine
from app.models import Base
from app.routers import auth, notifications, onboarding, plans, subscriptions, users, wallet, webhooks
from app.routers.admin import router as admin_router
from app.services.plans import seed_default_plans
from app.services.seed import seed_admin_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Startup: create tables (dev only) and seed plans
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        await seed_default_plans(db)
        await seed_admin_user(db)

    yield

    # Shutdown: dispose engine
    await engine.dispose()


app = FastAPI(
    title="TheRoyalSaving API",
    description="Premium Nigerian Cooperative Savings Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if settings.FRONTEND_URL and settings.FRONTEND_URL not in allowed_origins:
    allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
api_prefix = "/api/v1"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(onboarding.router, prefix=api_prefix)
app.include_router(users.router, prefix=api_prefix)
app.include_router(wallet.router, prefix=api_prefix)
app.include_router(plans.router, prefix=api_prefix)
app.include_router(subscriptions.router, prefix=api_prefix)
app.include_router(webhooks.router, prefix=api_prefix)
app.include_router(notifications.router, prefix=api_prefix)
app.include_router(admin_router, prefix=api_prefix)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a consistent error envelope."""
    if settings.is_production:
        # TODO: Report to Sentry
        pass
    else:
        import traceback
        traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_server_error",
            "detail": str(exc) if not settings.is_production else None,
            "message": "An unexpected error occurred.",
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "theroyalsaving-api"}
