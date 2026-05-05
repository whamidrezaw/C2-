"""
worker/run_once.py
یکبار reminder های سررسیده را پردازش می‌کند و خارج می‌شود.
مناسب برای GitHub Actions — به‌جای حلقه بی‌نهایت.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Bot

from app.config import get_settings
from app.db import close_mongo_connection, connect_to_mongo, ensure_indexes
from app.services.reminders import process_due_reminders

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tm_pro.run_once")


async def main() -> None:
    logger.info("run_once: connecting to MongoDB...")
    await connect_to_mongo(settings)
    await ensure_indexes(settings)

    async with Bot(token=settings.bot_token) as bot:
        logger.info("run_once: processing due reminders...")
        processed = await process_due_reminders(bot=bot, settings=settings)
        logger.info("run_once: done. processed=%s", processed)

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
