"""OpenChiken – Personal AI Assistant

Run with:
    uv run python main.py
"""
from __future__ import annotations

import asyncio
import logging
import sys

from config.settings import settings  # noqa: F401  (triggers .env loading)
from channels import load_channels
from channels.telegram_bot import TelegramAdapter
from scheduler.scheduler import create_scheduler


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("openchiken.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=== OpenChiken AI 비서 시작 ===")
    logger.info("LLM provider : %s / model : %s", settings.llm_provider, settings.openai_model)
    logger.info("Allowed users: %s", settings.allowed_user_ids or "(all)")
    logger.info("Enabled skills: %s", settings.enabled_skills)
    logger.info("Enabled channels: %s", settings.enabled_channels)
    logger.info(
        "스케줄: 아침브리핑 %02d:00 / 리마인더 %d분 전 / 주간브리핑 월 %02d:05",
        settings.morning_briefing_hour,
        settings.reminder_minutes_before,
        settings.morning_briefing_hour,
    )

    adapters = load_channels(settings.enabled_channels)
    if not adapters:
        logger.error("활성화된 채널이 없습니다. ENABLED_CHANNELS 설정을 확인하세요.")
        return

    telegram_adapter = next(
        (a for a in adapters if isinstance(a, TelegramAdapter)), None
    )
    other_adapters = [a for a in adapters if not isinstance(a, TelegramAdapter)]

    if telegram_adapter is None:
        # Telegram 없이 비동기 채널만 실행하는 경우
        logger.info("Telegram 없이 비동기 채널만 실행합니다.")
        try:
            asyncio.run(_run_async_channels(other_adapters))
        except (KeyboardInterrupt, SystemExit):
            pass
        return

    # Telegram이 있을 때: run_polling()이 이벤트 루프를 소유하고
    # post_init에서 스케줄러 + 나머지 채널을 asyncio 태스크로 시작합니다.
    async def _post_init(app) -> None:
        scheduler = create_scheduler(app.bot)
        scheduler.start()
        app.bot_data["scheduler"] = scheduler
        logger.info("스케줄러 시작 완료")

        for adapter in other_adapters:
            task = asyncio.create_task(adapter.start(), name=f"channel-{adapter.channel_name}")
            app.bot_data[f"channel_{adapter.channel_name}"] = task
            logger.info("%s 채널 태스크 시작", adapter.channel_name)

    async def _post_shutdown(app) -> None:
        if (s := app.bot_data.get("scheduler")) and s.running:
            s.shutdown(wait=False)
            logger.info("스케줄러 종료 완료")
        for adapter in other_adapters:
            task = app.bot_data.get(f"channel_{adapter.channel_name}")
            if task and not task.done():
                task.cancel()

    tg_app = telegram_adapter.build_app(
        post_init=_post_init, post_shutdown=_post_shutdown
    )
    logger.info("Telegram bot polling started – press Ctrl+C to stop")
    tg_app.run_polling(drop_pending_updates=True)


async def _run_async_channels(adapters) -> None:
    """Telegram 없이 비동기 채널만 실행합니다."""
    await asyncio.gather(*[adapter.start() for adapter in adapters])


if __name__ == "__main__":
    main()
