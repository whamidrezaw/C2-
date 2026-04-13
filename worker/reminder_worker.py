from __future__ import annotations

import asyncio
import logging

from telegram import Bot

from app.config import get_settings
from app.db import close_mongo_connection, connect_to_mongo, ensure_indexes
from app.services.reminders import process_due_reminders

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("tm_pro.worker")


async def worker_loop() -> None:
    logger.info("Reminder worker starting")

    await connect_to_mongo(settings)
    await ensure_indexes(settings)

    bot = Bot(token=settings.bot_token)

    try:
        async with bot:
            while True:
                try:
                    processed = await process_due_reminders(bot=bot, settings=settings)
                    if processed:
                        logger.info("Processed reminders: %s", processed)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Reminder worker iteration failed")

                await asyncio.sleep(settings.reminder_poll_interval_secs)
    finally:
        await close_mongo_connection()
        logger.info("Reminder worker stopped")


def main() -> None:
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Reminder worker interrupted by user")


if __name__ == "__main__":
    main()