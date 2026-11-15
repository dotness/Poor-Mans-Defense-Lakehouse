import hashlib
import logging
import time
from typing import Optional
import redis

from src.config.settings import settings
from src.core.exceptions import ConnectionError

logger = logging.getLogger(__name__)


class QueryCache:
    """Redis semantic query cache and rate limiter."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        client: Optional[redis.Redis] = None,
    ):
        self.host = host or settings.redis_host
        self.port = port or settings.redis_port
        self.db = db or settings.redis_db

        if client is not None:
            self._client: Optional[redis.Redis] = client
        else:
            self._client = None
            self._connect()

    def _connect(self) -> None:
        try:
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                socket_timeout=2.0,
                decode_responses=True,
            )
            client.ping()
            self._client = client
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {self.host}:{self.port}: {e}")
            raise ConnectionError(
                f"Failed to connect to Redis at {self.host}:{self.port}: {e}",
                host=self.host,
                port=self.port,
                original_cause=e,
            ) from e

    def _hash_prompt(self, prompt: str) -> str:
        normalized = prompt.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        """Retrieves cached response if present and not expired."""
        if not self._client:
            return None
        key = f"artemis:ai:query:{self._hash_prompt(prompt)}"
        try:
            return self._client.get(key)
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            return None

    def set(self, prompt: str, response: str, ttl: int = 3600) -> None:
        """Caches response for a given prompt with TTL in seconds (default: 1 hour)."""
        if not self._client:
            return
        key = f"artemis:ai:query:{self._hash_prompt(prompt)}"
        try:
            self._client.setex(key, ttl, response)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")

    def check_rate_limit(self, user_id: str, limit: int = 60, window_seconds: int = 60) -> bool:
        """Sliding window rate limiter using Redis sorted sets."""
        if not self._client:
            return True
        key = f"artemis:ai:ratelimit:{user_id}"
        now = time.time()
        clear_before = now - window_seconds
        try:
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, 0, clear_before)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds + 1)
            results = pipe.execute()
            current_count = results[1]
            return current_count < limit
        except Exception as e:
            logger.warning(f"Redis rate limit check error: {e}")
            return True

    def clear(self) -> None:
        """Flushes all cached query responses and rate limit counters."""
        if not self._client:
            return
        try:
            keys = self._client.keys("artemis:ai:*")
            if keys:
                self._client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")
