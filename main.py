import hmac, hashlib, json, time, html, logging, asyncio, os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import parse_qsl, unquote

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import certifi
from cachetools import TTLCache
from telegram import Bot
import jdatetime

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TM_PRO")

MAX_TITLE_LEN       = 200
MAX_EVENTS_PER_USER = 500
RATE_LIMIT_COUNT    = 30
AUTH_EXPIRE_SECS    = 300
VALID_REPEATS       = {"none", "daily", "weekly", "monthly", "yearly"}

# ==================== ENV VALIDATION ====================
def _validate_env():
    missing = [k for k, v in {"BOT_TOKEN": BOT_TOKEN, "MONGO_URI": MONGO_URI}.items() if not v]
    if missing:
        raise RuntimeError(f"❌ Missing env vars: {', '.join(missing)}")

# ==================== DATABASE & CACHE ====================
db_client   = AsyncIOMotorClient(MONGO_URI or "mongodb://localhost", tlsCAFile=certifi.where())
mdb         = db_client["time_manager_pro"]
events_coll = mdb["events"]
users_coll  = mdb["users"]
rate_cache  = TTLCache(maxsize=10000, ttl=60)

# ==================== LIFESPAN ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    await events_coll.create_index("expire_at", expireAfterSeconds=0)
    await events_coll.create_index("next_notify_at")
    await events_coll.create_index("user_id")
    await events_coll.create_index([("user_id", 1), ("event_ts_utc", 1)])
    logger.info("✅ Indexes verified.")
    bot  = Bot(token=BOT_TOKEN)
    task = asyncio.create_task(reminder_daemon(bot))
    logger.info("🚀 Daemon started.")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("🛑 Daemon stopped safely.")

app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
tm_renderer = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ==================== SECURITY ====================
async def validate_request(request: Request, init_data: str) -> str:
    if not init_data:
        raise HTTPException(403, "NO_DATA")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(403, "NO_USER")
    try:
        user_data = json.loads(unquote(user_raw))
    except json.JSONDecodeError:
        raise HTTPException(403, "INVALID_USER_JSON")
    user_id = str(user_data.get("id", ""))
    if not user_id.isdigit():
        raise HTTPException(403, "INVALID_ID")

    rl_key = f"rl:{user_id}"
    now    = time.time()
    hist   = [t for t in rate_cache.get(rl_key, []) if now - t < 60]
    if len(hist) >= RATE_LIMIT_COUNT:
        logger.warning(f"Rate limit: {user_id}")
        raise HTTPException(429, "RATE_LIMIT")
    hist.append(now)
    rate_cache[rl_key] = hist

    try:
        auth_date = int(parsed.get("auth_date", 0))
    except ValueError:
        raise HTTPException(403, "INVALID_AUTH_DATE")
    if now - auth_date > AUTH_EXPIRE_SECS:
        raise HTTPException(403, "EXPIRED")

    hash_check = parsed.pop("hash", None)
    if not hash_check:
        raise HTTPException(403, "NO_HASH")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed   = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, hash_check):
        raise HTTPException(403, "BAD_HASH")

    return user_id


def _safe_oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except Exception:
        raise HTTPException(400, "INVALID_ID_FORMAT")


# ==================== RECURRENCE ENGINE ====================
def calc_next_notify(base_date: datetime, repeat: str, tz: ZoneInfo) -> datetime | None:
    """
    محاسبه دقیق زمان بعدی نوتیف — همیشه ساعت ۹ صبح به وقت محلی.
    """
    if repeat == "none":
        return None

    now_local  = datetime.now(tz)
    base_local = base_date.astimezone(tz)

    if repeat == "daily":
        candidate = now_local.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)

    elif repeat == "weekly":
        candidate = now_local.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(weeks=1)

    elif repeat == "monthly":
        m = now_local.month + 1
        y = now_local.year + (1 if m > 12 else 0)
        m = m if m <= 12 else 1
        try:
            candidate = now_local.replace(year=y, month=m, day=base_local.day,
                                           hour=9, minute=0, second=0, microsecond=0)
        except ValueError:
            # روز ماه کوتاه — اول ماه بعدی
            candidate = now_local.replace(year=y, month=m, day=1,
                                           hour=9, minute=0, second=0, microsecond=0)

    elif repeat == "yearly":
        next_year = now_local.year + 1
        try:
            candidate = base_local.replace(year=next_year,
                                            hour=9, minute=0, second=0, microsecond=0)
        except ValueError:
            # ۲۹ فوریه در سال‌های غیر کبیسه
            candidate = base_local.replace(year=next_year, month=3, day=1,
                                            hour=9, minute=0, second=0, microsecond=0)
    else:
        return None

    return candidate.astimezone(timezone.utc)


def _expire_for_repeat(event_utc: datetime, repeat: str) -> datetime:
    """تعیین expire_at بر اساس نوع تکرار"""
    delta = {
        "none":    timedelta(days=30),
        "daily":   timedelta(days=2),
        "weekly":  timedelta(days=10),
        "monthly": timedelta(days=40),
        "yearly":  timedelta(days=400),
    }
    return event_utc + delta.get(repeat, timedelta(days=30))


def _repeat_label(repeat: str) -> str:
    return {
        "none":    "One-time",
        "daily":   "🔁 Daily",
        "weekly":  "🔁 Weekly",
        "monthly": "🔁 Monthly",
        "yearly":  "🎂 Yearly",
    }.get(repeat, "One-time")


# ==================== JALALI HELPER ====================
def to_jalali(date_iso: str) -> str:
    """تبدیل تاریخ میلادی به شمسی — مثلاً ۱۴۰۴/۱/۲۲"""
    try:
        d  = datetime.strptime(date_iso, "%Y-%m-%d")
        jd = jdatetime.date.fromgregorian(date=d.date())
        return jd.strftime("%Y/%m/%d")
    except Exception:
        return date_iso


# ==================== REMINDER DAEMON ====================
async def reminder_daemon(bot: Bot):
    logger.info("✅ Daemon loop running.")
    while True:
        try:
            now    = datetime.now(timezone.utc)
            cursor = events_coll.find({
                "next_notify_at": {"$lte": now},
                "notify_status":  "pending"
            }).limit(50)

            async for evt in cursor:
                updated = await events_coll.find_one_and_update(
                    {"_id": evt["_id"], "notify_status": "pending"},
                    {"$set": {"notify_status": "processing"}}
                )
                if not updated:
                    continue

                repeat       = evt.get("repeat", "none")
                repeat_label = _repeat_label(repeat)
                date_iso     = evt.get("date_iso", "")
                jalali_date  = to_jalali(date_iso)

                msg_text = (
                    f"🔔 <b>Reminder</b>\n"
                    f"📌 {html.escape(evt['title'])}\n"
                    f"📅 {date_iso}  •  {jalali_date}\n"
                    f"🔄 {repeat_label}"
                )

                try:
                    await bot.send_message(
                        chat_id    = evt["user_id"],
                        text       = msg_text,
                        parse_mode = "HTML"
                    )

                    tz_name   = evt.get("tz_name", "UTC")
                    tz        = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
                    base_date = evt.get("event_ts_utc", now)
                    if base_date.tzinfo is None:
                        base_date = base_date.replace(tzinfo=timezone.utc)

                    if repeat != "none":
                        next_notify = calc_next_notify(base_date, repeat, tz)
                        await events_coll.update_one(
                            {"_id": evt["_id"]},
                            {"$set": {
                                "notify_status":   "pending",
                                "next_notify_at":  next_notify,
                                "expire_at":       _expire_for_repeat(base_date, repeat),
                                "notify_attempts": 0
                            }}
                        )
                        logger.info(f"✅ Recurring sent & rescheduled: {evt['_id']} → {next_notify}")
                    else:
                        await events_coll.update_one(
                            {"_id": evt["_id"]},
                            {"$set": {"notify_status": "done", "next_notify_at": None}}
                        )
                        logger.info(f"✅ One-time sent: {evt['_id']}")

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    attempts = evt.get("notify_attempts", 0) + 1
                    status   = "failed" if attempts >= 5 else "pending"
                    await events_coll.update_one(
                        {"_id": evt["_id"]},
                        {"$set": {"notify_attempts": attempts, "notify_status": status}}
                    )
                    logger.error(f"❌ Notify fail: {evt['_id']} | {e}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Daemon loop error: {e}")

        await asyncio.sleep(30)


# ==================== INPUT PARSER ====================
def _parse_event_input(payload: dict) -> dict:
    title    = payload.get("title", "").strip()
    date_str = payload.get("date",  "").strip()
    tz_name  = payload.get("timezone", "UTC").strip()
    repeat   = payload.get("repeat", "none").strip().lower()

    if not title or not date_str:
        raise HTTPException(400, "BAD_INPUT")
    if len(title) > MAX_TITLE_LEN:
        raise HTTPException(400, "TITLE_TOO_LONG")
    if repeat not in VALID_REPEATS:
        raise HTTPException(400, "INVALID_REPEAT")

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz      = ZoneInfo("UTC")
        tz_name = "UTC"

    try:
        local_dt   = datetime.strptime(date_str, "%Y-%m-%d")
        notify_utc = local_dt.replace(hour=9, minute=0, second=0, tzinfo=tz).astimezone(timezone.utc)
        event_utc  = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(400, "INVALID_DATE")

    return {
        "title":           html.escape(title),
        "date_iso":        date_str,
        "next_notify_at":  notify_utc,
        "event_ts_utc":    event_utc,
        "expire_at":       _expire_for_repeat(event_utc, repeat),
        "repeat":          repeat,
        "tz_name":         tz_name,
        "notify_status":   "pending",
        "notify_attempts": 0,
    }


# ==================== ROUTES ====================

@app.get("/health")
async def health():
    try:
        await mdb.command("ping")
        return {"status": "ok", "db": "connected", "ts": datetime.now(timezone.utc).isoformat()}
    except Exception:
        raise HTTPException(500, "db_down")


@app.get("/webapp", response_class=HTMLResponse)
async def render_webapp(request: Request):
    return tm_renderer.TemplateResponse(request, "index.html")


@app.post("/api/list")
async def api_list(request: Request, payload: dict):
    user_id = await validate_request(request, payload.get("initData", ""))
    cursor  = events_coll.find({"user_id": user_id}).sort("event_ts_utc", 1).limit(100)
    targets = []
    async for e in cursor:
        date_iso = e.get("date_iso", "")
        targets.append({
            "id":            str(e["_id"]),
            "title":         e["title"],
            "date_iso":      date_iso,
            "date_jalali":   to_jalali(date_iso),
            "repeat":        e.get("repeat", "none"),
            "notify_status": e.get("notify_status", "pending"),
            "tz_name":       e.get("tz_name", "UTC"),
        })
    return {"success": True, "targets": targets}


@app.post("/api/add")
async def api_add(request: Request, payload: dict):
    user_id = await validate_request(request, payload.get("initData", ""))
    count   = await events_coll.count_documents({"user_id": user_id})
    if count >= MAX_EVENTS_PER_USER:
        raise HTTPException(400, "EVENT_LIMIT_REACHED")

    data = _parse_event_input(payload)
    data.update({"user_id": user_id, "created_at": datetime.now(timezone.utc)})

    await users_coll.update_one(
        {"_id": user_id},
        {"$set": {"timezone": data["tz_name"], "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    await events_coll.insert_one(data)
    logger.info(f"Event added: user={user_id}, repeat={data['repeat']}, tz={data['tz_name']}")
    return {"success": True}


@app.post("/api/delete")
async def api_delete(request: Request, payload: dict):
    user_id  = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    result = await events_coll.delete_one({"_id": _safe_oid(event_id), "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")

    logger.info(f"Event deleted: {event_id} by {user_id}")
    return {"success": True}


@app.post("/api/edit")
async def api_edit(request: Request, payload: dict):
    user_id  = await validate_request(request, payload.get("initData", ""))
    event_id = payload.get("event_id", "")
    if not event_id:
        raise HTTPException(400, "NO_EVENT_ID")

    oid      = _safe_oid(event_id)
    existing = await events_coll.find_one({"_id": oid, "user_id": user_id})
    if not existing:
        raise HTTPException(404, "NOT_FOUND_OR_UNAUTHORIZED")

    data = _parse_event_input(payload)
    data["updated_at"] = datetime.now(timezone.utc)

    await events_coll.update_one({"_id": oid, "user_id": user_id}, {"$set": data})
    logger.info(f"Event edited: {event_id} by {user_id}")
    return {"success": True}
