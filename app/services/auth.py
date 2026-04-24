# app/services/auth.py

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl, unquote

from fastapi import HTTPException, Request
from pymongo import ReturnDocument

from app.config import Settings, get_settings

logger = logging.getLogger("tm_pro.auth")

EXCLUDED_KEYS = frozenset({"hash", "signature"})


def build_data_check_string(parsed: dict[str, str]) -> str:
    filtered = {k: v for k, v in parsed.items() if k not in EXCLUDED_KEYS}
    return "\n".join(f"{key}={value}" for key, value in sorted(filtered.items()))


def compute_telegram_hash(init_data_map: dict[str, str], bot_token: str) -> str:
    data_check_string = build_data_check_string(init_data_map)
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sh_map)
    secretst()
    return hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def parse_init_data(init_data: str) -> dict[str, str]:
    if not init_data:
        raise HTTPException(status_code=403, detail="NODATA")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    if not parsed:
        raise HTTPException(status_code=403, detail="INVALIDINITDATA")
    return parsed


def parse_init_user(user_raw: str) -> dict[str, Any]:
    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=403, detail="INVALIDUSERJSON") from exc

    if not isinstance(user_data, dict):
        raise HTTPException(status_code=403, detail="INVALIDUSER")
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
        raise HTTPException(status_code=403, detail="INVALIDAUTHDATE") from exc

    if auth_date <= 0:
        raise HTTPException(status_code=403, detail="INVALIDAUTHDATE")

    now = now_ts if now_ts is not None else int(time.time())

    if auth_date < now - max_age_seconds:
        raise HTTPException(status_code=403, detail="EXPIRED")

    if auth_date > now + max_future_skew_seconds:
        raise HTTPException(status_code=403, detail="INVALIDAUTHDATE")


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
        raise HTTPException(status_code=403, detail="NOHASH")

    computed_hash = compute_telegram_hash(parsed, settings.bot_token)

    if not hmac.compare_digest(computed_hash, received_hash):
        client_ip = request.client.host if request.client else "unknown"
        data_check_string = build_data_check_string(parsed)

        logger.warning(
            "Bad Telegram initData HMAC: ip=%s received=%s computed=%s auth_date=%s keys=%s dcs=%r bot_tail=%s",
            client_ip,
            received_hash[:8] + "…",
            computed_hash[:8] + "…",
            parsed.get("auth_date"),
            sorted(parsed.keys()),
            data_check_string[:400],
            settings.bot_token[-8:] if settings.bot_token else "none",
        )
        raise HTTPException(status_code=403, detail="BADHASH")

    validate_auth_date(
        auth_date_raw=parsed.get("auth_date"),
        max_age_seconds=settings.telegram_init_data_max_age,
        max_future_skew_seconds=settings.telegram_init_data_future_skew,
    )

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=403, detail="NOUSER")

    user_data = parse_init_user(user_raw)
    user_id = str(user_data.get("id", ""))

    if not user_id.isdigit():
        raise HTTPException(status_code=403, detail="INVALIDID")

    await check_rate_limit_mongo(user_id, settings)

    return {
        "userid": user_id,
        "user": user_data,
        "authdate": parsed.get("auth_date"),
        "raw": parsed,
    }
