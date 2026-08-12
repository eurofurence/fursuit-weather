"""Visitor counting and the busy signal. No DWD needed: nothing here touches it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main, presence, ratelimit
from app.main import app, visitors


@pytest.fixture(autouse=True)
def clear_presence():
    visitors.reset()
    yield
    visitors.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _tracker(**kwargs) -> presence.PresenceTracker:
    return presence.PresenceTracker(window_seconds=60, busy_at=3, crowded_at=5, **kwargs)


def _touch(tracker: presence.PresenceTracker, count: int, at: float) -> None:
    """Put ``count`` distinct visitors on the tracker at a given clock reading."""
    for index in range(count):
        tracker._seen[f"visitor-{index}"] = at
    tracker._counted_at = float("-inf")  # force the next read to recount


def test_repeat_requests_are_one_visitor():
    tracker = _tracker()
    for _ in range(20):
        tracker.touch("same-visitor")
    assert tracker.visitors() == 1


def test_visitors_expire_after_the_window(monkeypatch):
    tracker = _tracker()
    now = 1_000.0
    monkeypatch.setattr(presence.time, "monotonic", lambda: now)
    tracker.touch("early")
    assert tracker.visitors() == 1

    now = 1_061.0  # one second past the 60 s window
    assert tracker.visitors() == 0


def test_levels_follow_the_thresholds(monkeypatch):
    tracker = _tracker()
    now = 500.0
    monkeypatch.setattr(presence.time, "monotonic", lambda: now)

    _touch(tracker, 2, now)
    assert tracker.level() == "normal"

    _touch(tracker, 3, now)
    assert tracker.level() == "busy"

    _touch(tracker, 5, now)
    assert tracker.level() == "crowded"


def test_snapshot_reports_the_peak_after_the_crowd_leaves(monkeypatch):
    tracker = _tracker()
    now = 500.0
    monkeypatch.setattr(presence.time, "monotonic", lambda: now)
    _touch(tracker, 6, now)
    assert tracker.snapshot()["visitors"] == 6

    now = 600.0
    snapshot = tracker.snapshot()
    assert snapshot["visitors"] == 0
    assert snapshot["peak_visitors"] == 6


class FakeRequest:
    """Just enough request for the two key functions."""

    def __init__(self, host: str, headers: dict | None = None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})()


def test_the_key_is_not_the_address():
    """A visitor handle must be stable per address but say nothing about it."""
    first = presence.visitor_key(FakeRequest("203.0.113.7"))
    again = presence.visitor_key(FakeRequest("203.0.113.7"))
    other = presence.visitor_key(FakeRequest("203.0.113.8"))

    assert first == again
    assert first != other
    assert "203.0.113" not in first


def test_cloudflare_header_wins_over_a_forgeable_one():
    """Behind the tunnel, CF-Connecting-IP is written by Cloudflare itself.

    A caller who sends their own X-Forwarded-For gets it *prepended* to the real
    one by the proxy, so trusting the first entry there would hand out a fresh
    identity per request -- and with it a way past the rate limit and a way to
    inflate the visitor count.
    """
    spoofed = FakeRequest(
        "172.16.0.1",
        {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "1.1.1.1, 203.0.113.7"},
    )
    honest = FakeRequest("172.16.0.1", {"cf-connecting-ip": "203.0.113.7"})

    assert presence.visitor_key(spoofed) == presence.visitor_key(honest)


def test_plain_proxy_still_falls_back_to_forwarded_for():
    behind_proxy = FakeRequest("172.16.0.1", {"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert ratelimit.client_key(behind_proxy) == "203.0.113.7"


def test_rate_limit_log_line_never_carries_an_address(client, caplog, monkeypatch):
    """The one line in the whole app that used to write a visitor's IP to disk.

    Nothing about a visitor is meant to reach disk; this is the test that keeps
    that true when someone edits the message back to something friendlier.
    """
    monkeypatch.setattr(main.limiter, "limit", 1)
    main.limiter.reset()
    headers = {"CF-Connecting-IP": "203.0.113.7"}

    with caplog.at_level("INFO", logger="app.ratelimit"):
        client.get("/api/v1/scale", headers=headers)
        blocked = client.get("/api/v1/scale", headers=headers)

    assert blocked.status_code == 429
    assert "Rate limit hit by client" in caplog.text
    assert "203.0.113.7" not in caplog.text


def test_both_privacy_paths_lead_to_the_eurofurence_notice(client):
    """The pages are gone, the paths are not: they are in links and bookmarks."""
    for path in ("/privacy", "/datenschutz"):
        page = client.get(path, follow_redirects=False)
        assert page.status_code == 307
        assert page.headers["location"] == main.PRIVACY_URL


def test_api_responses_carry_the_load_headers(client):
    response = client.get("/api/load")
    assert response.status_code == 200
    assert response.headers["X-Site-Load"] == "normal"
    assert int(response.headers["X-Site-Visitors"]) >= 1
    assert response.headers["Cache-Control"] == "no-store"

    body = response.json()
    assert body["level"] == "normal"
    assert body["window_seconds"] > 0


def test_healthcheck_is_not_a_visitor(client):
    """The container polls /api/health every minute; it must not haunt the count."""
    client.get("/api/health")
    assert visitors.visitors() == 0

    client.get("/")
    assert visitors.visitors() == 1


def test_a_page_visit_counts_but_only_api_carries_headers(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "X-Site-Load" not in page.headers
    assert visitors.visitors() == 1
