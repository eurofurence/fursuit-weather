"""How many people are on the site right now, and whether that is too many.

The site is served from a single machine at home, so "too many visitors at
once" is a state it can actually reach: the ICON renders and the radar fetches
are the expensive part, and a residential uplink is the narrow part. This
module gives the frontend a truthful signal for that -- a quiet notice telling
visitors the site is busy is far better than a page that silently takes twenty
seconds.

It is deliberately cookie-free, and that is not a compromise. A visitor is the
salted hash of the client address (see ``ratelimit.anonymised``), kept in memory
only; the salt is random per process, so the values cannot be linked across
restarts or turned back into an address. Nothing is stored on the visitor's
device, nothing is written to disk, and no single visitor can be picked out of
the table -- only counted.

Two honest limits:

* One process, one table. With several uvicorn workers each holds its own
  count, so the numbers divide across workers -- the same scope as the rate
  limiter next door. The container runs a single worker, which is why this is
  fine here.
* A visitor is an address, so a whole hotel or convention centre behind one NAT
  counts once, and a crawler counts as a person. The number is a load signal,
  not an audience metric, and should never be published as one.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Dict

from fastapi import Request

from app.ratelimit import anonymised, client_key

logger = logging.getLogger(__name__)

#: The count is read on nearly every response, so it is cached for a moment
#: rather than recomputed each time. A second of staleness costs nothing.
RECOUNT_SECONDS = 1.0


def visitor_key(request: Request) -> str:
    """An opaque, unlinkable handle for the caller."""
    return anonymised(client_key(request))


class PresenceTracker:
    """Counts distinct visitors seen inside a sliding window."""

    def __init__(self, window_seconds: int = 300, busy_at: int = 40, crowded_at: int = 80) -> None:
        self.window = window_seconds
        self.busy_at = busy_at
        self.crowded_at = crowded_at
        self._seen: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._count = 0
        # -inf rather than 0: time.monotonic() has no defined epoch, so a small
        # starting value would make the first recount look recent and skip.
        self._counted_at = float("-inf")
        self._in_flight = 0
        self._peak = 0

    def touch(self, key: str) -> None:
        """Record that this visitor is here now."""
        now = time.monotonic()
        with self._lock:
            arrived = key not in self._seen
            self._seen[key] = now
            if now - self._counted_at >= RECOUNT_SECONDS:
                self._recount(now)
            elif arrived:
                # Someone showing up counts at once; only people leaving wait
                # for the next recount, which is the direction to be slow in.
                self._count += 1
                self._note_peak()

    def visitors(self) -> int:
        """The current count, cheap enough to call per request."""
        now = time.monotonic()
        with self._lock:
            if now - self._counted_at >= RECOUNT_SECONDS:
                self._recount(now)
            return self._count

    def level(self, visitors: int | None = None) -> str:
        """``normal``, ``busy`` or ``crowded`` -- what the frontend acts on."""
        count = self.visitors() if visitors is None else visitors
        if count >= self.crowded_at:
            return "crowded"
        if count >= self.busy_at:
            return "busy"
        return "normal"

    @contextlib.contextmanager
    def in_flight(self):
        """Count a request while it is being served.

        Visitors say how many people are around; in-flight requests say how
        much the machine is doing about it right now. The second is what the
        operator wants when deciding where to put the thresholds.
        """
        with self._lock:
            self._in_flight += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight -= 1

    def snapshot(self) -> dict:
        """Everything /api/load reports."""
        now = time.monotonic()
        with self._lock:
            self._recount(now)
            return {
                "visitors": self._count,
                "level": self.level(self._count),
                "in_flight_requests": self._in_flight,
                "window_seconds": self.window,
                "busy_at": self.busy_at,
                "crowded_at": self.crowded_at,
                "peak_visitors": self._peak,
            }

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()
            self._count = 0
            self._counted_at = float("-inf")
            self._peak = 0

    def _recount(self, now: float) -> None:
        """Drop everyone who has gone quiet, then count. Caller holds the lock."""
        cutoff = now - self.window
        stale = [key for key, seen in self._seen.items() if seen < cutoff]
        for key in stale:
            del self._seen[key]
        self._count = len(self._seen)
        self._counted_at = now
        self._note_peak()

    def _note_peak(self) -> None:
        """Remember the high-water mark. Caller holds the lock."""
        if self._count > self._peak:
            self._peak = self._count
            logger.info("New peak: %d visitors in the last %ds", self._count, self.window)


#: The container's own healthcheck calls this once a minute from inside the
#: network namespace. Counting it would put a permanent phantom visitor on the
#: site, which is exactly the kind of small lie that makes a load signal
#: useless.
UNCOUNTED_PATHS = frozenset({"/api/health"})


def build_middleware(tracker: PresenceTracker, header_prefix: str = "/api/"):
    """ASGI middleware that counts the caller and reports the load back.

    Every request counts, not only page loads: a browser fetching the stylesheet
    is a person here, and repeats collapse onto the same key anyway. The headers
    ride along on API responses the page already makes, so the notice costs no
    extra request.
    """

    async def middleware(request: Request, call_next):
        path = request.url.path
        if path not in UNCOUNTED_PATHS:
            tracker.touch(visitor_key(request))

        with tracker.in_flight():
            response = await call_next(request)

        if path.startswith(header_prefix):
            visitors = tracker.visitors()
            response.headers["X-Site-Load"] = tracker.level(visitors)
            response.headers["X-Site-Visitors"] = str(visitors)
        return response

    return middleware
