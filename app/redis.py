"""Redis connection and RQ queue setup."""

from redis import Redis
from rq import Queue

from app.config import settings

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

# RQ task queues
default_queue = Queue("default", connection=redis_client)
notification_queue = Queue("notifications", connection=redis_client)
