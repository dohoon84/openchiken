from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from scheduler.jobs import job_morning_briefing, job_event_reminder, job_weekly_briefing

logger = logging.getLogger(__name__)


def create_scheduler(bot) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler.

    The scheduler must be started *inside* the running asyncio event loop
    (e.g. via Application.post_init) so all jobs share the same loop as
    the Telegram bot.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    briefing_hour = settings.morning_briefing_hour

    # 매일 아침 브리핑
    scheduler.add_job(
        job_morning_briefing,
        trigger=CronTrigger(hour=briefing_hour, minute=0, timezone="Asia/Seoul"),
        args=[bot],
        id="morning_briefing",
        name=f"아침 브리핑 ({briefing_hour:02d}:00 KST)",
        replace_existing=True,
    )

    # 매 5분마다 15분 후 일정 리마인더
    scheduler.add_job(
        job_event_reminder,
        trigger=IntervalTrigger(minutes=5),
        args=[bot],
        id="event_reminder",
        name="일정 리마인더 (5분 간격)",
        replace_existing=True,
    )

    # 매주 월요일 아침 주간 브리핑
    scheduler.add_job(
        job_weekly_briefing,
        trigger=CronTrigger(day_of_week="mon", hour=briefing_hour, minute=5, timezone="Asia/Seoul"),
        args=[bot],
        id="weekly_briefing",
        name=f"주간 브리핑 (월요일 {briefing_hour:02d}:05 KST)",
        replace_existing=True,
    )

    logger.info(
        "스케줄러 설정 완료 – 아침브리핑 %02d:00, 리마인더 %d분 전, 주간브리핑 월 %02d:05",
        briefing_hour,
        settings.reminder_minutes_before,
        briefing_hour,
    )
    return scheduler
