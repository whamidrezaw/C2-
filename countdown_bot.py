import logging
import threading
import json
import os
import re
import time
from datetime import datetime
from flask import Flask, render_template, request, abort
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    Defaults
)
from pymongo import MongoClient
import certifi
import jdatetime
import ssl

app = Flask(__name__, template_folder='templates')

# --- 1. SECURITY & CONFIGURATION ---
# Load secrets from Environment Variables ONLY
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0)) # Default to 0 if missing
except:
    ADMIN_ID = None

# Fail Fast: If critical secrets are missing, stop immediately.
if not BOT_TOKEN or not MONGO_URI:
    print("❌ CRITICAL ERROR: BOT_TOKEN or MONGO_URI is missing from Environment Variables.")
    exit(1)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger("TimeManagerBot")

# --- 2. DATABASE CONNECTION ---
users_collection = None
try:
    ca = certifi.where()
    client = MongoClient(
        MONGO_URI, 
        tls=True, 
        tlsCAFile=ca, 
        serverSelectionTimeoutMS=5000,
        retryWrites=True
    )
    client.admin.command('ping')
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅ MongoDB Connected Securely")
except Exception as e:
    logger.critical(f"❌ DB Connection Failed: {e}")
    exit(1) # Cannot run without DB

# --- 3. RATE LIMITING (Simple In-Memory) ---
user_timestamps = {}

def check_rate_limit(user_id):
    """Simple rate limit: 1 request per second per user"""
    now = time.time()
    last_time = user_timestamps.get(user_id, 0)
    if now - last_time < 1.0: # 1 second limit
        return False
    user_timestamps[user_id] = now
    return True

# --- 4. FLASK SERVER ---
@app.route('/')
def home(): return "Status: Online 🟢"

@app.route('/healthz')
def health():
    """Health check endpoint for UptimeRobot"""
    try:
        client.admin.command('ping')
        return "OK", 200
    except:
        return "DB Fail", 500

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    # Display logic for dates
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: item['shamsi_date'] = ""

    return render_template('index.html', user_data=targets)

def run_server():
    # In production, use Gunicorn. For this setup, threading is acceptable for low traffic.
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()

# --- 5. DATA HELPERS (Atomic) ---
def get_user_data(uid):
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            users_collection.insert_one({"_id": str(uid), "targets": {}, "joined_at": datetime.utcnow()})
            return {"_id": str(uid), "targets": {}}
        return data
    except Exception as e:
        logger.error(f"DB Read Error: {e}")
        return {"_id": str(uid), "targets": {}}

def update_db(uid, data):
    try:
        users_collection.update_one({"_id": str(uid)}, {"$set": data}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"DB Write Error: {e}")
        return False

# --- 6. LOGIC & PARSING ---
def parse_smart_date(date_str):
    date_str = str(date_str).strip()[:20] # Limit input length
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    date_str = re.sub(r'[/\-\s,]+', '.', date_str)
    parts = [p for p in date_str.split('.') if p]
    
    if len(parts) != 3: return None
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None

        final = None
        if y > 1900: final = datetime(y, m, d)
        elif y < 1500: 
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
        
        if final: return final.strftime("%d.%m.%Y")
    except: return None
    return None

# --- 7. TELEGRAM HANDLERS ---
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

def main_kb(uid):
    if WEBAPP_URL_BASE:
        url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
        btn = KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))
    else: btn = KeyboardButton("⚠️ WebApp Error")
    
    return ReplyKeyboardMarkup([
        [btn],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# -- Global Error Handler --
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# -- Handlers --
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_rate_limit(user.id): return # Anti-Spam
    
    get_user_data(user.id)
    await update.message.reply_text(
        f"👋 **Hello {user.first_name}!**\n\n"
        "I help you track deadlines securely.\n"
        "👇 **Select an option:**",
        reply_markup=main_kb(user.id), parse_mode=ParseMode.MARKDOWN
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    await update.message.reply_text("❓ Please use the buttons below:", reply_markup=main_kb(update.effective_user.id))

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ **Text only please.**", reply_markup=main_kb(update.effective_user.id))

# -- Add Flow --
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    if len(msg) > 50: # Validation
        await update.message.reply_text("⚠️ Name too long (Max 50 chars).")
        return 1
        
    context.user_data['title'] = msg
    await update.message.reply_text("📅 **Enter Date:**\n(e.g. 2026.12.30 or 1405.10.20)", parse_mode=ParseMode.MARKDOWN)
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    formatted = parse_smart_date(msg)
    if formatted:
        data = get_user_data(uid)
        import uuid
        new_id = f"evt_{uuid.uuid4().hex[:8]}"
        
        # Atomic update using dot notation for specific field
        try:
            users_collection.update_one(
                {"_id": str(uid)},
                {"$set": {f"targets.{new_id}": {
                    "title": context.user_data['title'],
                    "date": formatted,
                    "type": "personal"
                }}},
                upsert=True
            )
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"DB Error: {e}")
            await update.message.reply_text("⛔ Database Error.", reply_markup=main_kb(uid))
            
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again.", parse_mode=ParseMode.MARKDOWN)
        return 2

# -- Support --
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    await update.message.reply_text("💌 **Write message for Admin:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return GET_SUPPORT

async def support_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    if msg == "❌ Cancel": return await cancel(update, context)
    
    if ADMIN_ID:
        try:
            text = f"📩 **Support**\nFrom: `{user.id}`\n\n{msg[:1000]}" # Limit length
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode=ParseMode.MARKDOWN)
            await update.message.reply_text("✅ **Sent!**", reply_markup=main_kb(user.id), parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ Failed to send.", reply_markup=main_kb(user.id))
    else:
        await update.message.reply_text("⚠️ Support disabled.", reply_markup=main_kb(user.id))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# -- Delete --
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 **Empty.**", parse_mode=ParseMode.MARKDOWN)
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Tap to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    key = query.data.replace("del_", "")
    
    try:
        # Atomic delete
        users_collection.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
        await query.answer("Deleted!")
        await query.delete_message()
    except:
        await query.answer("Error")

def main():
    keep_alive()
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()
    
    app.add_error_handler(error_handler)

    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add)"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    conv_sup = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Support)"), support_start)],
        states={GET_SUPPORT: [MessageHandler(filters.TEXT, support_rec)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )

    app.add_handler(conv_add)
    app.add_handler(conv_sup)
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    
    # Security Filters
    app.add_handler(MessageHandler(filters.ATTACHMENT, handle_files))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))
    
    print(f"Bot Running Securely (Admin: {ADMIN_ID})...")
    app.run_polling()

if __name__ == "__main__":
    main()