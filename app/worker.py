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


from app.services.notifiers.email import send_resend_email_task
from app.services.notifiers.sms import send_termii_sms_task


class WorkerSettings:
    """
    Configuration for the ARQ worker.
    To start this worker locally:
      uv run arq app.worker.WorkerSettings
    """
    # Connect to the Redis URL defined in our project config
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    # Register all background tasks the worker is allowed to process here
    functions = [
        send_resend_email_task,
        send_termii_sms_task,
    ]
    
    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Periodic tasks (e.g., daily penalty checks) will be added here
    cron_jobs = []
