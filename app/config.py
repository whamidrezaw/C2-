from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    bot_token: str
    app_base_url: str
    telegram_webhook_secret: str
    mongodb_uri: str
    mongodb_db_name: str
    telegram_initdata_max_age: int
    telegram_initdata_future_skew: int
    rate_limit_count: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        bot_token=os.environ["BOT_TOKEN"].strip(),
        app_base_url=os.environ["APP_BASE_URL"].strip().rstrip("/"),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "CHANGE_ME_NOW").strip(),
        mongodb_uri=os.environ["MONGODB_URI"].strip(),
        mongodb_db_name=os.getenv("MONGODB_DB_NAME", "tm_pro").strip(),
        telegram_initdata_max_age=int(os.getenv("TELEGRAM_INITDATA_MAX_AGE", "3600")),
        telegram_initdata_future_skew=int(os.getenv("TELEGRAM_INITDATA_FUTURE_SKEW", "60")),
        rate_limit_count=int(os.getenv("RATE_LIMIT_COUNT", "60")),
    )
