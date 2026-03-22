from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from functools import partial

from config.settings import settings
from scheduler.jobs import job_morning_briefing, job_event_reminder, job_weekly_briefing, run_app_job

logger = logging.getLogger(__name__)


def create_scheduler(bot) -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler.

    The scheduler must be started *inside* the running asyncio event loop
    (e.g. via Application.post_init) so all jobs share the same loop as
    the Telegram bot.

    기본 시스템 잡 + APP.md schedule 필드 기반 동적 앱 잡을 등록합니다.
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

    # APP.md schedule 필드 기반 동적 앱 잡 등록
    _register_app_jobs(scheduler, bot)

    logger.info(
        "스케줄러 설정 완료 – 아침브리핑 %02d:00, 리마인더 %d분 전, 주간브리핑 월 %02d:05",
        briefing_hour,
        settings.reminder_minutes_before,
        briefing_hour,
    )
    return scheduler


def _register_app_jobs(scheduler: AsyncIOScheduler, bot) -> None:
    """설치된 모든 앱의 schedule 필드를 읽어 동적으로 cron 잡을 등록합니다."""
    try:
        from skills import get_skill_loader
        loader = get_skill_loader()
        apps = loader.load_apps()
    except Exception as e:
        logger.warning("앱 잡 등록 실패 (스킬 로더 오류): %s", e)
        return

    registered = 0
    for app in apps:
        if not app.schedule or not app.enabled:
            continue

        job_id = f"app_{app.name}"
        try:
            trigger = CronTrigger.from_crontab(app.schedule, timezone="Asia/Seoul")
            scheduler.add_job(
                run_app_job,
                trigger=trigger,
                args=[app.name, bot],
                id=job_id,
                name=f"앱 자동 실행: {app.name} ({app.schedule})",
                replace_existing=True,
            )
            registered += 1
            logger.info("앱 잡 등록: %s (cron: %s)", app.name, app.schedule)
        except Exception as e:
            logger.warning("앱 잡 등록 실패 (%s, cron=%s): %s", app.name, app.schedule, e)

    if registered:
        logger.info("동적 앱 잡 %d개 등록 완료", registered)
