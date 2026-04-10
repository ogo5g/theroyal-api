"""ARQ Global Connection Pool."""

import logging
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)


class WorkerPool:
    """Holds a global instance of the ARQ Redis connection pool."""
    pool: ArqRedis | None = None


async def init_pool() -> None:
    """Initialize the ARQ Redis pool. Call during FastAPI lifespan."""
    logger.info("Initializing ARQ Redis pool...")
    WorkerPool.pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


async def close_pool() -> None:
    """Close the ARQ Redis pool. Call during FastAPI shutdown."""
    if WorkerPool.pool:
        logger.info("Closing ARQ Redis pool...")
        await WorkerPool.pool.close()
