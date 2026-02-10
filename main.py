import logging
import os
import uuid
import hmac
import hashlib
import json
import asyncio
import time
import random
from datetime import datetime
from urllib.parse import unquote
from typing import Dict, Any, Optional

import jdatetime
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator

from telegram import MenuButtonWebApp
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except:
    ADMIN_ID = None

# ==================== LOGGING SETUP ====================
formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger("TimeManager-Pro")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# ==================== RATE LIMITER (MEMORY SAFE) ====================
request_history: Dict[str, list] = {}

async def rate_limit(request: Request, max_requests: int = 30, window: int = 60):
    """Rate limiting with automatic memory cleanup"""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Cleanup old entries (10% probability to avoid overhead)
    if random.randint(1, 10) == 1:
        cutoff = now - window
        for ip in list(request_history.keys()):
            request_history[ip] = [t for t in request_history[ip] if t > cutoff]
            if not request_history[ip]:
                del request_history[ip]
    
    if client_ip not in request_history:
        request_history[client_ip] = []
    
    # Filter old requests for this specific IP
    request_history[client_ip] = [t for t in request_history[client_ip] if now - t < window]
    
    if len(request_history[client_ip]) >= max_requests:
        logger.warning(f"Rate limit hit for IP: {client_ip}")
        raise HTTPException(429, "Too many requests. Please slow down.")
    
    request_history[client_ip].append(now)

# ==================== DATABASE CONNECTION ====================
db_client: Optional[AsyncIOMotorClient] = None

def get_db():
    if db_client is None:
        raise HTTPException(503, "Database not connected")
    return db_client['time_manager_db']['users']

# ==================== SECURITY UTILS ====================
def validate_telegram_data(init_data: str) -> Optional[dict]:
    """Validate Telegram WebApp data with HMAC"""
    if not BOT_TOKEN or not init_data:
        return None
    
    try:
        parsed_data = {}
        for pair in init_data.split('&'):
            if '=' not in pair:
                continue
            key, value = pair.split('=', 1)
            parsed_data[key] = value
        
        hash_check = parsed_data.pop('hash', None)
        if not hash_check:
            return None
        
        # Check timestamp (24 hours TTL)
        auth_date = int(parsed_data.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            logger.warning("Telegram data expired")
            return None
        
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, hash_check):
            return None
        
        if 'user' in parsed_data:
            return json.loads(unquote(parsed_data['user']))
        return None
        
    except Exception as e:
        logger.error(f"Validation Error: {e}")
        return None

def parse_date(text: str) -> Optional[str]:
    """Smart date parser (Shamsi/Gregorian)"""
    if not text:
        return None
    
    text = text.replace('/', '.').replace('-', '.')
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    text = text.translate(trans)
    parts = [p for p in text.split('.') if p.isdigit()]
    
    if len(parts) != 3:
        return None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = (p1, p2, p3) if p1 > 1000 else (p3, p2, p1)
        
        if y < 1500:  # Shamsi to Gregorian
            g = jdatetime.date(y, m, d).togregorian()
            return datetime(g.year, g.month, g.day).strftime("%d.%m.%Y")
        
        return datetime(y, m, d).strftime("%d.%m.%Y")
    except:
        return None

# ==================== PYDANTIC MODELS ====================
class EventModel(BaseModel):
    initData: str = Field(..., min_length=20)
    title: Optional[str] = Field(None, max_length=100)
    date: Optional[str] = Field(None, max_length=15)
    key: Optional[str] = Field(None, max_length=50)

    @validator('title')
    def validate_title(cls, v):
        if v and not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip() if v else v

# ==================== FASTAPI APP ====================
templates = Jinja2Templates(directory="templates")

async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global db_client
    
    # 1. Database Connection & Indexing
    if MONGO_URI:
        db_client = AsyncIOMotorClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            maxPoolSize=10,
            minPoolSize=1
        )
        try:
            await db_client['time_manager_db']['users'].create_index("_id")
            logger.info("✅ Database Connected & Indexed")
        except Exception as e:
            logger.error(f"❌ Database Init Error: {e}")
    
    # 2. Telegram Bot Start
    if BOT_TOKEN:
        await bot_app.initialize()
        await bot_app.start()
        asyncio.create_task(bot_app.updater.start_polling(drop_pending_updates=True))
        logger.info("✅ Telegram Bot Started")
    
    yield  # Application runs here
    
    # 3. Graceful Shutdown
    if BOT_TOKEN:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    if db_client:
        db_client.close()
    logger.info("🛑 Shutdown Complete")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== GLOBAL EXCEPTION HANDLER ====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal Server Error"}
    )

# ==================== BOT HANDLERS ====================
SUPPORT_MSG = range(1)

async def start_command(update: Update, context):
    uid = str(update.effective_user.id)
    coll = get_db()
    await coll.update_one(
        {"_id": uid},
        {"$setOnInsert": {"targets": {}, "created_at": datetime.utcnow()}},
        upsert=True
    )
    
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}" if WEBAPP_URL_BASE else "https://telegram.org"
    
    await context.bot.set_chat_menu_button(
        chat_id=update.effective_chat.id,
        menu_button=MenuButtonWebApp(text="📱 Open App", web_app=WebAppInfo(url=url))
    )
    
    kb = ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("📞 Contact Support")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 **Hello {update.effective_user.first_name}!**\n\n"
        "Tap **Open App** below to start.",
        reply_markup=kb,
        parse_mode='Markdown'
    )
async def support_start(update: Update, context):
    """Support conversation start"""
    await update.message.reply_text(
        "📬 **Type your message:**",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
    )
    return SUPPORT_MSG

async def support_receive(update: Update, context):
    """Support message receiver"""
    if update.message.text == "❌ Cancel":
        await start_command(update, context)
        return ConversationHandler.END
    
    if ADMIN_ID:
        await context.bot.send_message(
            ADMIN_ID,
            f"📩 **Support:**\nUser: `{update.effective_user.id}`\n\n{update.message.text}",
            parse_mode='Markdown'
        )
        await update.message.reply_text("✅ Message sent to support team.")
    
    return ConversationHandler.END

# Setup Telegram Bot
bot_app = None
if BOT_TOKEN:
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Contact)"), support_start)],
        states={SUPPORT_MSG: [MessageHandler(filters.TEXT, support_receive)]},
        fallbacks=[MessageHandler(filters.ALL, start_command)]
    ))

# ==================== ROUTES ====================
@app.get("/")
def home():
    return HTMLResponse("<h3>TimeManager Pro 🚀</h3><p>System Operational</p>")

@app.get("/health")
def health():
    return {"status": "healthy", "time": time.time()}

@app.get("/webapp/{user_id}", response_class=HTMLResponse)
async def render_webapp(request: Request, user_id: str):
    """Render webapp for user"""
    coll = get_db()
    user_doc = await coll.find_one({"_id": user_id})
    targets = user_doc.get('targets', {}) if user_doc else {}
    
    # Convert dates to Shamsi for display
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y/%m/%d")
        except:
            item['shamsi_date'] = ""
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user_data": targets
    })

@app.post("/api/add")
async def api_add(payload: EventModel, request: Request):
    """Add new event"""
    await rate_limit(request)
    
    user_info = validate_telegram_data(payload.initData)
    if not user_info:
        raise HTTPException(403, "Invalid Security Data")
    
    formatted_date = parse_date(payload.date)
    if not formatted_date:
        return JSONResponse(
            {"success": False, "error": "Invalid Date Format"},
            status_code=400
        )
    
    evt_id = f"evt_{uuid.uuid4().hex[:8]}"
    coll = get_db()
    
    await coll.update_one(
        {"_id": str(user_info['id'])},
        {"$set": {
            f"targets.{evt_id}": {
                "title": payload.title,
                "date": formatted_date,
                "created_at": datetime.utcnow()
            }
        }},
        upsert=True
    )
    
    logger.info(f"Event added for user {user_info['id']}: {payload.title}")
    return {"success": True}

@app.post("/api/delete")
async def api_delete(payload: EventModel, request: Request):
    """Delete event"""
    await rate_limit(request)
    
    user_info = validate_telegram_data(payload.initData)
    if not user_info:
        raise HTTPException(403, "Invalid Security Data")
    
    coll = get_db()
    await coll.update_one(
        {"_id": str(user_info['id'])},
        {"$unset": {f"targets.{payload.key}": ""}}
    )
    
    logger.info(f"Event deleted for user {user_info['id']}: {payload.key}")
    return {"success": True}
