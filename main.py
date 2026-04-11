import hmac, hashlib, json, time, html, logging, asyncio, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl, unquote
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from cachetools import TTLCache
from telegram import Bot

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "YOUR_MONGO_URI")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TM_PRO")

# ==================== DATABASE & CACHE ====================
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["time_manager_pro"]
events_coll = db["events"]
users_coll = db["users"]
rate_cache = TTLCache(maxsize=10000, ttl=60)

app = FastAPI()

# Mount Static and Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
render_engine = Jinja2Templates(directory="templates")

# ==================== SECURITY UTILS ====================
async def validate_request(request: Request, init_data: str):
    if not init_data: raise HTTPException(403, "NO_DATA")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    user_raw = parsed.get("user")
    if not user_raw: raise HTTPException(403, "NO_USER")
    
    user_data = json.loads(unquote(user_raw))
    user_id = str(user_data.get("id"))
    if not user_id.isdigit(): raise HTTPException(403, "INVALID_ID")

    # Rate Limit
    rl_key = f"{user_id}:{request.client.host}"
    now = time.time()
    hist = rate_cache.get(rl_key, [])
    hist = [t for t in hist if now - t < 60]
    if len(hist) >= 25: 
        logger.warning(f"Rate limit hit: {user_id}")
        raise HTTPException(429, "RATE_LIMIT")
    hist.append(now)
    rate_cache[rl_key] = hist

    # HMAC Protection
    hash_check = parsed.pop("hash", None)
    if now - int(parsed.get("auth_date", 0)) > 300: raise HTTPException(403, "EXPIRED")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest(), hash_check):
        raise HTTPException(403, "BAD_HASH")
    return user_id

# ==================== DAEMON: REMINDER ENGINE ====================
async def reminder_daemon(bot: Bot):
    await events_coll.create_index("expire_at", expireAfterSeconds=0)
    await events_coll.create_index("next_notify_at")
    logger.info("✅ Daemon started and indexes verified.")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            cursor = events_coll.find({
                "next_notify_at": {"$lte": now}, 
                "notify_status": "pending"
            }).limit(50)

            async for evt in cursor:
                # Atomic Lock to prevent double-send
                updated = await events_coll.find_one_and_update(
                    {"_id": evt["_id"], "notify_status": "pending"},
                    {"$set": {"notify_status": "processing"}}
                )
                if not updated: continue
                try:
                    await bot.send_message(
                        chat_id=evt["user_id"], 
                        text=f"🔔 <b>Reminder:</b>\n{evt['title']}", 
                        parse_mode="HTML"
                    )
                    await events_coll.update_one(
                        {"_id": evt["_id"]}, 
                        {"$set": {"notify_status": "done", "next_notify_at": None}}
                    )
                    logger.info(f"Notify sent: {evt['_id']}")
                except Exception as e:
                    attempts = evt.get("notify_attempts", 0) + 1
                    status = "failed" if attempts >= 5 else "pending"
                    await events_coll.update_one(
                        {"_id": evt["_id"]}, 
                        {"$set": {"notify_attempts": attempts, "notify_status": status}}
                    )
                    logger.error(f"Notify fail: {evt['_id']} | Error: {e}")
        except Exception as e: 
            logger.error(f"Daemon Loop Error: {e}")
        await asyncio.sleep(30)

# ==================== ROUTES ====================

@app.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "db": "connected"}
    except:
        raise HTTPException(500, "db_down")

# مسیر اصلی وب‌اپ که ارور 404 را برطرف می‌کند
@app.get("/webapp", response_class=HTMLResponse)
async def render_webapp(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/list")
async def api_list(request: Request, payload: dict):
    user_id = await validate_request(request, payload.get("initData"))
    cursor = events_coll.find({"user_id": user_id}).sort("event_ts_utc", 1).limit(100)
    targets = []
    async for e in cursor:
        targets.append({
            "id": str(e["_id"]),
            "title": e["title"],
            "date_iso": e.get("date_iso", "")
        })
    return {"success": True, "targets": targets}

@app.post("/api/add")
async def api_add(request: Request, payload: dict):
    user_id = await validate_request(request, payload.get("initData"))
    title, date_str = payload.get("title"), payload.get("date")
    if not title or not date_str: raise HTTPException(400, "BAD_INPUT")
    
    user = await users_coll.find_one({"_id": user_id}) or {}
    tz_name = user.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
        local_dt = datetime.strptime(date_str, "%Y-%m-%d")
        notify_utc = local_dt.replace(hour=9, minute=0, second=0, tzinfo=tz).astimezone(timezone.utc)
        event_utc = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
    except: raise HTTPException(400, "INVALID_DATE")

    await events_coll.insert_one({
        "user_id": user_id, 
        "title": html.escape(title.strip()),
        "date_iso": date_str, 
        "next_notify_at": notify_utc,
        "event_ts_utc": event_utc,
        "expire_at": event_utc + timedelta(days=30),
        "notify_status": "pending", 
        "notify_attempts": 0
    })
    logger.info(f"Event added: user={user_id}")
    return {"success": True}

# ==================== LIFESPAN ====================
@app.on_event("startup")
async def startup_event():
    # شروع Daemon در پس‌زمینه
    bot = Bot(token=BOT_TOKEN)
    asyncio.create_task(reminder_daemon(bot))
    logger.info("🚀 System Startup: Daemon Task Scheduled")

