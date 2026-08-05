"""A small per-client rate limit for the public API.

The data behind every endpoint is cached, so a burst costs us little -- but an
open API still needs a ceiling so one misbehaving consumer cannot crowd out the
ConOps board or the site itself.

This is an in-process sliding window. That is the honest scope: with several
uvicorn workers each holds its own counter, so the effective limit is the
configured value times the worker count. For a single-container deployment that
is exactly right; behind a load balancer, enforce limits there instead.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60

#: Regenerated on every start, never persisted, never logged. Shared with the
#: visitor counter next door: both need to talk about a client without holding
#: an address, and one salt for both keeps that promise in one place.
_SALT = secrets.token_bytes(16)


def anonymised(key: str) -> str:
    """An opaque, unlinkable handle for a client key.

    Not reversible, and not comparable across restarts. Anything that outlives
    the request -- a table that sticks around, a log line -- uses this rather
    than the address itself.
    """
    return hashlib.blake2s(key.encode("utf-8"), key=_SALT, digest_size=8).hexdigest()


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: int = WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        """Return (allowed, remaining, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = max(1, int(hits[0] + self.window - now) + 1)
                return False, 0, retry_after

            hits.append(now)
            remaining = self.limit - len(hits)

        # Keep the table from growing without bound on a long-lived process.
        if len(self._hits) > 4096:
            self._prune(cutoff)

        return True, remaining, 0

    def _prune(self, cutoff: float) -> None:
        with self._lock:
            stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
            for key in stale:
                del self._hits[key]
        if stale:
            logger.debug("Rate limiter pruned %d idle clients", len(stale))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request) -> str:
    """Identify the caller, preferring the header the proxy in front actually sets.

    ``CF-Connecting-IP`` first, because the deployment is a Cloudflare Tunnel and
    that header is written by Cloudflare itself -- a client cannot forge it,
    since anything it sends under that name is overwritten.

    ``X-Forwarded-For`` is the fallback for any other proxy, and its first entry
    is *not* trustworthy: Cloudflare and most proxies append to whatever the
    client sent, so a caller who invents a first entry would get a fresh
    identity on every request. That is only acceptable for a limit whose job is
    politeness, and it is why the header above is tried first.
    """
    cloudflare = request.headers.get("cf-connecting-ip")
    if cloudflare:
        return cloudflare.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def build_middleware(limiter: SlidingWindowLimiter, path_prefix: str = "/api/"):
    """ASGI middleware limiting only the API surface, not the pages or media."""

    async def middleware(request: Request, call_next):
        if not request.url.path.startswith(path_prefix):
            return await call_next(request)

        allowed, remaining, retry_after = limiter.check(client_key(request))
        if not allowed:
            # The hash, not the address: this line is the one piece of the
            # system that would otherwise write a visitor's IP to disk, and the
            # site promises on /privacy that nothing does. It still tells one
            # persistent offender apart from a crowd, which is all it was for.
            logger.info(
                "Rate limit hit by client %s on %s",
                anonymised(client_key(request))[:8],
                request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. The data is cached; please poll less often.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limiter.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    return middleware
