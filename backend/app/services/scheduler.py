import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.prices import is_stale, refresh_all

log = logging.getLogger(__name__)


def _refresh_job() -> None:
    with SessionLocal() as db:
        try:
            refresh_all(db)
        except Exception:
            log.exception("Scheduled price refresh failed")


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.price_refresh_tz)
    # Daily, including weekends, since crypto trades every day.
    scheduler.add_job(
        _refresh_job,
        CronTrigger(
            hour=settings.price_refresh_hour,
            minute=settings.price_refresh_minute,
            timezone=settings.price_refresh_tz,
        ),
        id="daily_price_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    # Catch up if the computer was off at the scheduled time.
    with SessionLocal() as db:
        if is_stale(db):
            log.info("Prices are stale; refreshing on startup")
            scheduler.add_job(_refresh_job, id="startup_price_refresh", next_run_time=datetime.now())
    scheduler.start()
    return scheduler
