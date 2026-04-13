from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

def extract_hash_and_build_data_check_string(init_data: str) -> tuple[str, str, dict[str, str]]:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    if not parsed:
        raise HTTPException(status_code=403, detail="INVALID_INIT_DATA")

    received_hash = parsed.pop("hash", "")
    parsed.pop("signature", None)

    if not received_hash:
        raise HTTPException(status_code=403, detail="NO_HASH")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed.items(), key=lambda item: item[0])
    )
    return received_hash, data_check_string, parsed


def compute_telegram_hash(data_check_string: str, bot_token: str) -> str:
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()

    return hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()


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

    received_hash, data_check_string, parsed = extract_hash_and_build_data_check_string(init_data)

    computed_hash = compute_telegram_hash(data_check_string, settings.bot_token)
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

    if not user_id.isdigit():
        raise HTTPException(status_code=403, detail="INVALID_ID")

    check_rate_limit(user_id, settings)

    return {
        "user_id": user_id,
        "user": user_data,
        "auth_date": parsed.get("auth_date"),
        "raw": parsed,
    }


async def get_authenticated_user_id(request: Request) -> str:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    auth_result = await validate_init_data(request, init_data)
    return auth_result["user_id"]
