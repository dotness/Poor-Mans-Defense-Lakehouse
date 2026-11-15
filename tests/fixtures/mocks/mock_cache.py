import hashlib
import time
from typing import Dict, List, Optional, Tuple


class MockQueryCache:
    """In-memory test double for QueryCache."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, db: Optional[int] = None):
        self.host = host
        self.port = port
        self.db = db
        self._memory_cache: Dict[str, Tuple[str, float]] = {}
        self._memory_rate_limit: Dict[str, List[float]] = {}

    def _hash_prompt(self, prompt: str) -> str:
        normalized = prompt.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        key = f"artemis:ai:query:{self._hash_prompt(prompt)}"
        if key in self._memory_cache:
            val, expires_at = self._memory_cache[key]
            if time.time() < expires_at:
                return val
            del self._memory_cache[key]
        return None

    def set(self, prompt: str, response: str, ttl: int = 3600) -> None:
        key = f"artemis:ai:query:{self._hash_prompt(prompt)}"
        self._memory_cache[key] = (response, time.time() + ttl)

    def check_rate_limit(self, user_id: str, limit: int = 60, window_seconds: int = 60) -> bool:
        now = time.time()
        timestamps = self._memory_rate_limit.setdefault(user_id, [])
        self._memory_rate_limit[user_id] = [t for t in timestamps if now - t < window_seconds]
        if len(self._memory_rate_limit[user_id]) >= limit:
            return False
        self._memory_rate_limit[user_id].append(now)
        return True

    def clear(self) -> None:
        self._memory_cache.clear()
        self._memory_rate_limit.clear()
