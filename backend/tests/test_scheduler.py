"""The scheduler's catch-up refresh at startup."""

import threading

from app.services import scheduler


def test_stale_prices_refresh_right_away(monkeypatch):
    ran = threading.Event()
    monkeypatch.setattr(scheduler, "is_stale", lambda db: True)
    monkeypatch.setattr(scheduler, "_refresh_job", ran.set)
    started = scheduler.start_scheduler()
    try:
        assert ran.wait(5), "the startup catch-up didn't run"
    finally:
        started.shutdown(wait=False)
