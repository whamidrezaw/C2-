from __future__ import annotations
from pymongo import ReturnDocument
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from app.config import Settings, get_settings
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from pymongo import ReturnDocument
logger = logging.getLogger("tm_pro.auth")

# ─── Fallback in-memory store (فقط برای تست یا وقتی DB در دسترس نیست) ──────
_rate_store: dict[str, list[float]] = {}


def _prune_rate_history(user_id: str, window_seconds: int = 60) -> list[float]:
    now = time.time()
    history = [t for t in _rate_store.get(user_id, []) if now - t < window_seconds]
    _rate_store[user_id] = history
    return history


def _check_rate_limit_memory(user_id: str, settings: Settings) -> None:
    """Fallback in-memory rate limit — فقط وقتی DB در دسترس نیست."""
    history = _prune_rate_history(user_id)
    if len(history) >= settings.rate_limit_count:
        logger.warning("Rate limit exceeded (memory): user_id=%s", user_id)
        raise HTTPException(status_code=429, detail="RATE_LIMIT")
    history.append(time.time())
    _rate_store[user_id] = history


def check_rate_limit(user_id: str, settings: Settings | None = None) -> None:
    """نسخه sync — فقط برای تست‌ها استفاده می‌شه."""
    settings = settings or get_settings()
    _check_rate_limit_memory(user_id, settings)


async def check_rate_limit_mongo(user_id: str, settings: Settings) -> None:
    try:
        from app.db import get_database

        db = get_database()
        rate_coll = db["rate_limits"]

        now = datetime.now(timezone.utc)
        bucket = now.replace(second=0, microsecond=0)

        doc = await rate_coll.find_one_and_update(
            {"user_id": user_id, "bucket": bucket},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {"ts": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if int(doc.get("count", 0)) > settings.rate_limit_count:
            raise HTTPException(status_code=429, detail="RATE_LIMIT")

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Rate limit mongo unavailable, using memory fallback: %s", exc)
        _check_rate_limit_memory(user_id, settings)


# ─── توابع اصلی ─────────────────────────────────────────────────────────────

def build_data_check_string(parsed: dict[str, str]) -> str:
    filtered = {
        key: value
        for key, value in parsed.items()
        if key not in {"hash", "signature"}
    }
    return "\n".join(f"{key}={value}" for key, value in sorted(filtered.items()))


def compute_telegram_hash(init_data_map: dict[str, str], bot_token: str) -> str:
    data_check_string = build_data_check_string(init_data_map)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def parse_init_data(init_data: str) -> dict[str, str]:
    if not init_data:
        raise HTTPException(status_code=403, detail="NO_DATA")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    if not parsed:
        raise HTTPException(status_code=403, detail="INVALID_INIT_DATA")

    return parsed


def parse_init_user(user_raw: str) -> dict[str, Any]:
    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=403, detail="INVALID_USER_JSON") from exc

    if not isinstance(user_data, dict):
        raise HTTPException(status_code=403, detail="INVALID_USER")

    return user_data


def validate_auth_date(
    auth_date_raw: str | None,
    max_age_seconds: int,
    max_future_skew_seconds: int = 60,
    now_ts: int | None = None,
) -> None:
    try:
        auth_date = int(auth_date_raw or "0")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="INVALID_AUTH_DATE") from exc

    if auth_date <= 0:
        raise HTTPException(status_code=403, detail="INVALID_AUTH_DATE")

    now = now_ts if now_ts is not None else int(time.time())

    if auth_date < now - max_age_seconds:
        raise HTTPException(status_code=403, detail="EXPIRED")

    if auth_date > now + max_future_skew_seconds:
        raise HTTPException(status_code=403, detail="INVALID_AUTH_DATE")


async def validate_init_data(
    request: Request,
    init_data: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()

    if not settings.bot_token:
        raise HTTPException(status_code=500, detail="MISCONFIGURED")

    parsed = parse_init_data(init_data)

    received_hash = parsed.get("hash")
    if not received_hash:
        raise HTTPException(status_code=403, detail="NO_HASH")

logger.warning(
    "initData validation failed: bot_token_prefix=%s received_hash=%s computed_hash=%s auth_date=%s",
    (settings.bot_token[:10] + "...") if settings.bot_token else "EMPTY",
    (received_hash[:12] + "...") if received_hash else "NONE",
    (computed_hash[:12] + "...") if computed_hash else "NONE",
    parsed.get("auth_date"),
)
    
    computed_hash = compute_telegram_hash(parsed, settings.bot_token)
    if not hmac.compare_digest(computed_hash, received_hash):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Bad Telegram initData HMAC: ip=%s", client_ip)
        raise HTTPException(status_code=403, detail="BAD_HASH")

    validate_auth_date(
        auth_date_raw=parsed.get("auth_date"),
        max_age_seconds=settings.telegram_initdata_max_age,
        max_future_skew_seconds=settings.telegram_initdata_future_skew,
    )

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=403, detail="NO_USER")

    user_data = parse_init_user(user_raw)
    user_id = str(user_data.get("id", ""))

    if not user_id or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="INVALID_ID")

    # Rate limit مبتنی بر MongoDB (مشترک بین همه worker ها)
    await check_rate_limit_mongo(user_id, settings)

    return {
        "user_id": user_id,
        "user": user_data,
        "auth_date": parsed.get("auth_date"),
        "raw": parsed,
    }


async def get_authenticated_user_id(
    request: Request,
    init_data: str,
    settings: Settings | None = None,
) -> str:
    auth_result = await validate_init_data(request, init_data, settings)
    return auth_result["user_id"]
