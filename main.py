from pathlib import Path
import ast
code = '''import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import time
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import certifi
import jdatetime
from bson import ObjectId
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("TM_PRO")

MAX_TITLE_LEN = 200
MAX_NOTE_LEN = 2000
MAX_EVENTS_PER_USER = 500
RATE_LIMIT_COUNT = 30
AUTH_EXPIRE_SECS = 900
REMINDER_BATCH_SIZE = 50
STALE_PROCESSING_SECS = 300
VALID_REPEATS = {"none", "daily", "weekly", "monthly", "yearly"}
VALID_CATEGORIES = {
    "general",
    "birthday",
    "work",
    "family",
    "health",
    "travel",
    "finance",
    "study",
    "other",
}

_rate_store: dict[str, list[float]] = {}

db_client = None
mdb = None
events_coll = None
users_coll = None


def _validate_env() -> None:
    missing = [k for k, v in {"BOT_TOKEN": BOT_TOKEN, "MONGO_URI": MONGO_URI}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")


def _check_rate_limit(user_id: str) -> None:
    now = time.time()
    hist = [t for t in _rate_store.get(user_id, []) if now - t < 60]
    if len(hist) >= RATE_LIMIT_COUNT:
        logger.warning("Rate limit hit: user=%s", user_id)
        raise HTTPException(429, "RATE_LIMIT")
    hist.append(now)
    _rate_store[user_id] = hist


def _safe_oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except Exception as exc:
        raise HTTPException(400, "INVALID_ID_FORMAT") from exc


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _clean_note(value: str) -> str:
    note = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(note) > MAX_NOTE_LEN:
        raise HTTPException(400, "NOTE_TOO_LONG")
    return note


def _clean_category(value: str) -> str:
    category = str(value or "general").strip().lower()
    if category not in VALID_CATEGORIES:
        raise HTTPException(400, "INVALID_CATEGORY")
    return category


def _safe_zoneinfo(tz_name: str | None) -> tuple[ZoneInfo, str]:
    try:
        if tz_name:
            return ZoneInfo(tz_name), tz_name
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        logger.warning("Invalid timezone received: %s", tz_name)
    return ZoneInfo("UTC"), "UTC"


def _expire_for_repeat(anchor: datetime, repeat: str) -> datetime:
    delta = {
        "none": timedelta(days=30),
        "daily": timedelta(days=2),
        "weekly": timedelta(days=10),
        "monthly": timedelta(days=40),
        "yearly": timedelta(days=400),
    }
    return anchor + delta.get(repeat, timedelta(days=30))


def _repeat_label(repeat: str) -> str:
    return {
        "none": "One-time",
        "daily": "🔁 Daily",
        "weekly": "🔁 Weekly",
        "monthly": "🔁 Monthly",
        "yearly": "🎂 Yearly",
    }.get(repeat, "One-time")


def to_jalali(date_iso: str) -> str:
    try:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        jd = jdatetime.date.fromgregorian(date=d.date())
        return jd.strftime("%Y/%m/%d")
    except Exception:
        return date_iso


def _month_candidate(reference: datetime, anchor_day: int, months_ahead: int = 1) -> datetime:
    month = reference.month - 1 + months_ahead
    year = reference.year + month // 12
    month = month % 12 + 1
    day = min(anchor_day, monthrange(year, month)[1])
    return reference.replace(year=year, month=month, day=day, hour=9, minute=0, second=0, microsecond=0)


def calc_next_notify(base_date: datetime, repeat: str, tz: ZoneInfo) -> datetime | None:
    if repeat == "none":
        return None

    now_local = datetime.now(tz)
    base_local = base_date.astimezone(tz).replace(hour=9, minute=0, second=0, microsecond=0)

    if repeat == "daily":
        candidate = base_local
        while candidate <= now_local:
            candidate += timedelta(days=1)
    elif repeat == "weekly":
        candidate = base_local
        while candidate <= now_local:
            candidate += timedelta(weeks=1)
    elif repeat == "monthly":
        candidate = base_local
        while candidate <= now_local:
            candidate = _month_candidate(candidate, base_local.day, 1)
    elif repeat == "yearly":
        candidate = base_local
        while candidate <= now_local:
            next_year = candidate.year + 1
            try:
                candidate = candidate.replace(year=next_year)
            except ValueError:
                candidate = candidate.replace(year=next_year, month=3, day=1)
    else:
        return None

    return candidate.astimezone(timezone.utc)


def _serialize_event(doc: dict) -> dict:
    date_iso = doc.get("date_iso", "")
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "date_iso": date_iso,
        "date_jalali": to_jalali(date_iso),
        "repeat": doc.get("repeat", "none"),
        "notify_status": doc.get("notify_status", "pending"),
        "tz_name": doc.get("tz_name", "UTC"),
        "category": doc.get("category", "general"),
        "pinned": bool(doc.get("pinned", False)),
        "note": doc.get("note", ""),
    }


def _parse_event_input(payload: dict) -> dict:
    title = str(payload.get("title", "")).strip()
    date_str = str(payload.get("date", "")).strip()
    tz_name_raw = str(payload.get("timezone", "UTC")).strip()
    repeat = str(payload.get("repeat", "none")).strip().lower()
    category = _clean_category(payload.get("category", "general"))
    note = _clean_note(payload.get("note", ""))
    pinned = _coerce_bool(payload.get("pinned", False))

    if not title or not date_str:
        raise HTTPException(400, "BAD_INPUT")
    if len(title) > MAX_TITLE_LEN:
        raise HTTPException(400, "TITLE_TOO_LONG")
    if repeat not in VALID_REPEATS:
        raise HTTPException(400, "INVALID_REPEAT")

    tz, tz_name = _safe_zoneinfo(tz_name_raw)

    try:
        local_dt = datetime.strptime(date_str, "%Y-%m-%d")
        notify_local = local_dt.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=tz)
        event_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
        notify_utc = notify_local.astimezone(timezone.utc)
        event_utc = event_local.astimezone(timezone.utc)
    except ValueError as exc:
        raise HTTPException(400, "INVALID_DATE") from exc

    return {
        "title": title,
        "date_iso": date_str,
        "next_notify_at": notify_utc,
        "event_ts_utc": event_utc,
        "expire_at": _expire_for_repeat(notify_utc, repeat),
        "repeat": repeat,
        "tz_name": tz_name,
        "notify_status": "pending",
        "notify_attempts": 0,
        "processing_started_at": None,
        "category": category,
        "note": note,
        "pinned": pinned,
    }


async def validate_request(request: Request, init_data: str) -> str:
    if not BOT_TOKEN:
        raise HTTPException(500, "MISCONFIGURED")
    if not init_data:
        raise HTTPException(403, "NO_DATA")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_check = parsed.pop("hash", None)
    if not hash_check:
        raise HTTPException(403, "NO_HASH")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, hash_check):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Bad HMAC: ip=%s", client_ip)
        raise HTTPException(403, "BAD_HASH")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(403, "NO_USER")
    try:
        user_data = json.loads(unquote(user_raw))
    except json.JSONDecodeError as exc:
        raise HTTPException(403, "INVALID_USER_JSON") from exc

    user_id = str(user_data.get("id", ""))
    if not user_id.isdigit():
        raise HTTPException(403, "INVALID_ID")

    try:
        auth_date = int(parsed.get("auth_date", 0))
    except ValueError as exc:
        raise HTTPException(403, "INVALID_AUTH_DATE") from exc
    if abs(time.time() - auth_date) > AUTH_EXPIRE_SECS:
        raise HTTPException(403, "EXPIRED")

    _check_rate_limit(user_id)
    return user_id


async def recover_stale_processing() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSING_SECS)
    result = await events_coll.update_many(
        {
            "notify_status": "processing",
            "processing_started_at": {"$lte": cutoff},
        },
        {
            "$set": {"notify_status": "pending"},
            "$unset": {"processing_started_at": ""},
        },
    )
    if result.modified_count:
        logger.warning("Recovered stuck processing events: %s", result.modified_count)


async def reminder_daemon(bot: Bot):
    logger.info("Daemon loop running.")
    while True:
        try:
            await recover_stale_processing()
            now = datetime.now(timezone.utc)
            cursor = events_coll.find(
                {"next_notify_at": {"$lte": now}, "notify_status": "pending"}
            ).sort("next_notify_at", 1).limit(REMINDER_BATCH_SIZE)

            async for evt in cursor:
                claimed = await events_coll.find_one_and_update(
                    {"_id": evt["_id"], "notify_status": "pending"},
                    {
                        "$set": {
                            "notify_status": "processing",
                            "processing_started_at": now,
                        }
                    },
                )
                if not claimed:
                    continue

                repeat = evt.get("repeat", "none")
                repeat_label = _repeat_label(repeat)
                date_iso = evt.get("date_iso", "")
                jalali_date = to_jalali(date_iso)
                category = evt.get("category", "general")
                pin_mark = "📌 " if evt.get("pinned") else ""
                title = html.escape(evt.get("title", ""))

                msg_text = (
                    f"🔔 <b>Reminder</b>\n"
                    f"{pin_mark}{title}\n"
                    f"📅 {date_iso}  •  {jalali_date}\n"
                    f"🏷️ {html.escape(category.title())}\n"
                    f"🔄 {repeat_label}"
                )

                try:
                    await bot.send_message(
                        chat_id=evt["user_id"],
                        text=msg_text,
                        parse_mode="HTML",
                    )

                    tz, _ = _safe_zoneinfo(evt.get("tz_name", "UTC"))
                    base_date = evt.get("event_ts_utc", now)
                    if base_date.tzinfo is None:
                        base_date = base_date.replace(tzinfo=timezone.utc)

                    if repeat != "none":
                        next_notify = calc_next_notify(base_date, repeat, tz)
                        expire_anchor = next_notify or now
                        await events_coll.update_one(
                            {"_id": evt["_id"]},
                            {
                                "$set": {
                                    "notify_status": "pending",
                                    "next_notify_at": next_notify,
                                    "expire_at": _expire_for_repeat(expire_anchor, repeat),
                                    "notify_attempts": 0,
                                },
                                "$unset": {"processing_started_at": ""},
                            },
                        )
                    else:
                        await events_coll.update_one(
                            {"_id": evt["_id"]},
                            {
                                "$set": {"notify_status": "done", "next_notify_at": None},
                                "$unset": {"processing_started_at": ""},
                            },
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    attempts = evt.get("notify_attempts", 0) + 1
                    status = "failed" if attempts >= 5 else "pending"
                    await events_coll.update_one(
                        {"_id": evt["_id"]},
                        {
                            "$set": {
                                "notify_attempts": attempts,
                                "notify_status": status,
                            },
                            "$unset": {"processing_started_at": ""},
                        },
                    )
                    logger.error("Notify fail: %s | %s", evt["_id"], exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Daemon loop error: %s", exc)

        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client, mdb, events_coll, users_coll

    _validate_env()

    db_client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    mdb = db_client["time_manager_pro"]
    events_coll = mdb["events"]
    users_coll = mdb["users"]

    await events_coll.create_index("expire_at", expireAfterSeconds=0)
    await events_coll.create_index([("notify_status", 1), ("next_notify_at", 1)])
    await events_coll.create_index("user_id")
    await events_coll.create_index([("user_id", 1), ("pinned", -1), ("event_ts_utc", 1)])
    await events_coll.create_index([("user_id", 1), ("category", 1)])
    await events_coll.create_index([("notify_status", 1), ("processing_started_at", 1)])
    logger.info("Indexes verified.")

    bot = Bot(token=BOT_TOKEN)
    task = asyncio.create_task(reminder_daemon(bot))
    logger.info("Reminder daemon started.")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Reminder daemon stopped safely.")
        db_client.close()


app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
tm_renderer = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/health")
async def health():
    try:
        await asyncio.wait_for(mdb.command("ping"), timeout=3.0)
        return {
            "status": "ok",
            "db": "connected",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    except asyncio.TimeoutError as exc:
        raise HTTPException(503, "db_timeout") from exc
    except Exception as exc:
        raise HTTPException(503, "db_down") from exc


@app.get("/")
async def root():
    return RedirectResponse(url="/webapp", status_code=302)


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(BASE_DIR, "static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    raise HTTPException(404, "favicon_not_found")


@app.get("/webapp", response_class=HTMLResponse)
async def render_webapp(request: Request):
    return tm_renderer.TemplateResponse(request, "index.html")


@app.post("/api/list")
async def api_list(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))

    skip_raw = payload.get("skip", 0)
    try:
        skip = max(0, min(int(skip_raw), 5000))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "INVALID_SKIP") from exc

    cursor = (
        events_coll.find({"user_id": user_id})
        .sort([("pinned", -1), ("event_ts_utc", 1)])
        .skip(skip)
        .limit(50)
    )

    targets = []
    async for event in cursor:
        targets.append(_serialize_event(event))

    return {"success": True, "targets": targets, "has_more": len(targets) == 50}


@app.post("/api/add")
async def api_add(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))
    count = await events_coll.count_documents({"user_id": user_id})
    if count >= MAX_EVENTS_PER_USER:
        raise HTTPException(400, "EVENT_LIMIT_REACHED")

    data = _parse_event_input(payload)
    now = datetime.now(timezone.utc)
    data.update({"user_id": user_id, "created_at": now, "updated_at": now})

    await users_coll.update_one(
        {"_id": user_id},
        {"$set": {"timezone": data["tz_name"], "updated_at": now}},
        upsert=True,
    )
    await events_coll.insert_one(data)
    logger.info(
        "Event added: user=%s, repeat=%s, category=%s, pinned=%s",
        user_id,
        data["repeat"],
        data["category"],
        data["pinned"],
    )
    return {"success": True}


@app.post("/api/edit")
async def api_edit(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    oid = _safe_oid(event_id)
    existing = await events_coll.find_one({"_id": oid, "user_id": user_id})
    if not existing:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")

    data = _parse_event_input(payload)
    data["updated_at"] = datetime.now(timezone.utc)

    await events_coll.update_one({"_id": oid, "user_id": user_id}, {"$set": data})
    logger.info("Event edited: %s by %s", event_id, user_id)
    return {"success": True}


@app.post("/api/delete")
async def api_delete(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    result = await events_coll.delete_one({"_id": _safe_oid(event_id), "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")

    logger.info("Event deleted: %s by %s", event_id, user_id)
    return {"success": True}


@app.post("/api/note")
async def api_note(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    note = _clean_note(payload.get("note", ""))
    result = await events_coll.update_one(
        {"_id": _safe_oid(event_id), "user_id": user_id},
        {"$set": {"note": note, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")
    return {"success": True, "note": note}


@app.post("/api/pin")
async def api_pin(request: Request, payload: dict = Body(...)):
    user_id = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    pinned = _coerce_bool(payload.get("pinned", False))
    result = await events_coll.update_one(
        {"_id": _safe_oid(event_id), "user_id": user_id},
        {"$set": {"pinned": pinned, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")
    return {"success": True, "pinned": pinned}
'''
Path('output').mkdir(exist_ok=True)
path = Path('output/main.py')
path.write_text(code, encoding='utf-8')
ast.parse(code)
print(path)
