"""Shared HTTP session and a small TTL cache for DWD OpenData requests.

Everything here is deliberately synchronous: the endpoints are hit at most a
few times per hour thanks to the cache, and FastAPI runs sync route helpers in
a threadpool.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def get_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            _session = requests.Session()
            _session.headers.update({"User-Agent": settings.user_agent})
        return _session


class TTLCache:
    """Cache that also keeps the last good value as a fallback.

    If DWD is briefly unreachable we would rather show slightly stale data than
    an error page, so ``get_or_fetch`` falls back to the expired entry when the
    refresh raises.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_fetch(self, key: str, ttl: int, fetch: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            entry = self._data.get(key)
        if entry and now - entry[0] < ttl:
            return entry[1]

        try:
            value = fetch()
        except Exception as exc:  # noqa: BLE001 - upstream failures must not 500
            if entry is not None:
                age = int(now - entry[0])
                logger.warning("Refresh of %s failed (%s); serving %ss old data", key, exc, age)
                return entry[1]
            logger.error("Fetch of %s failed with no cached fallback: %s", key, exc)
            raise

        with self._lock:
            self._data[key] = (now, value)
        return value

    def age(self, key: str) -> Optional[float]:
        with self._lock:
            entry = self._data.get(key)
        return None if entry is None else time.time() - entry[0]

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


cache = TTLCache()


def fetch_bytes(url: str, timeout: Optional[int] = None) -> bytes:
    response = get_session().get(url, timeout=timeout or settings.request_timeout)
    response.raise_for_status()
    return response.content
