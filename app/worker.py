import asyncio
import logging
from arq.connections import RedisSettings

from app.config import settings

# Setup standard logger for the worker
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arq.worker")


async def startup(ctx):
    """Executes when the ARQ worker boots up."""
    logger.info("🚀 ARQ Worker started. Connected to Redis.")
    # You can initialize HTTP clients, DB pool, etc., and store them in ctx here.


async def shutdown(ctx):
    """Executes when the ARQ worker shuts down."""
    logger.info("🛑 ARQ Worker shutting down cleanly.")


# --- Placeholder Tasks (To be moved to phases 2, 3, 4) ---

async def send_welcome_email(ctx, email: str, name: str):
    """A placeholder task to verify the worker is functioning."""
    logger.info(f"📧 [TASK STARTED] Sending welcome email to {name} <{email}>")
    await asyncio.sleep(2)  # Simulate network hop to Resend
    logger.info(f"✅ [TASK DONE] Welcome email sent to {email}.")


class WorkerSettings:
    """
    Configuration for the ARQ worker.
    To start this worker locally:
      uv run arq app.worker.WorkerSettings
    """
    # Connect to the Redis URL defined in our project config
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    # Register all background tasks the worker is allowed to process here
    functions = [send_welcome_email]
    
    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Periodic tasks (e.g., daily penalty checks) will be added here
    cron_jobs = []
