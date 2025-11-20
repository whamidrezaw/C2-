import logging
import threading
import json
import os
import re
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, abort
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Defaults
from telegram.constants import ParseMode
from pymongo import MongoClient
import certifi
import jdatetime
import ssl
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

app = Flask(_name_, template_folder='templates')

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except:
    ADMIN_ID = None
    logging.warning("⚠ ADMIN_ID is missing! Support messages will be lost.")

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(_name_)

if not BOT_TOKEN or not MONGO_URI:
    logger.critical("❌ MISSING CRITICAL ENV VARS (BOT_TOKEN / MONGO_URI)")
    exit(1)

# --- DATABASE CONNECTION (Robust with Retry) ---
users_collection = None
rate_limit_collection = None

try:
    ca = certifi.where()
    # retryWrites=true and connectTimeoutMS helps with stability
    client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000, retryWrites=True)
    client.admin.command('ping')
    
    db = client['time_manager_db']
    users_collection = db['users']
    rate_limit_collection = db['rate_limit'] # New collection for rate limiting
    
    logger.info("✅ MONGODB CONNECTED SUCCESSFULLY")
except Exception as e:
    logger.critical(f"❌ DB CONNECTION FAILED: {e}")
    exit(1)

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is Running (Secure V2)"

@app.route('/healthz')
def health():
    """Health check for UptimeRobot"""
    try:
        client.admin.command('ping')
        return "OK", 200
    except:
        return "DB ERROR", 500

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: 
            item['shamsi_date'] = ""
            
    return render_template('index.html', user_data=targets)

def run_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# --- DATA HELPERS (With Retry) ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
def get_user_data(uid):
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            users_collection.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except Exception as e:
        logger.error(f"DB Read Error: {e}")
        raise e

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
def update_db(uid, data):
    try:
        users_collection.update_one({"_id": str(uid)}, {"$set": data}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"DB Write Error: {e}")
        raise e

# --- RATE LIMITING (Database Based) ---
def check_rate_limit(uid):
    """Allows 10 requests per 60 seconds"""
    try:
        now = datetime.utcnow()
        record = rate_limit_collection.find_one({"_id": str(uid)})
        
        if not record:
            rate_limit_collection.insert_one({"_id": str(uid), "count": 1, "reset_at": now + timedelta(seconds=60)})
            return True
            
        if now > record['reset_at']:
            # Reset window
            rate_limit_collection.update_one({"_id": str(uid)}, {"$set": {"count": 1, "reset_at": now + timedelta(seconds=60)}})
            return True
            
        if record['count'] >= 10:
            return False # Blocked
            
        rate_limit_collection.update_one({"_id": str(uid)}, {"$inc": {"count": 1}})
        return True
    except:
        return True # Fail-open if DB error (don't block user)

# --- SMART DATE PARSER ---
def parse_smart_date(date_str):
    date_str = str(date_str).strip()[:20] # Limit length
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

# --- KEYBOARDS ---
def main_kb(uid):
    # If WebApp URL is missing, disable button
    btn_app = KeyboardButton("⚠ Config Error")
    if WEBAPP_URL_BASE:
        url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
        btn_app = KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))

    return ReplyKeyboardMarkup([
        [btn_app],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not check_rate_limit(uid): return # Ignore spam
    
    get_user_data(uid)
    await update.message.reply_text(
        "👋 *Welcome to Time Manager!*\n\n"
        "I help you track your deadlines.\n"
        "• *Add Event:* Supports Gregorian & Persian dates.\n"
        "• *Mini App:* Visual dashboard.\n\n"
        "👇 *Select an option below:*",
        reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("❓ *Please use the buttons below:*", reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN)

# --- ADD FLOW ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    await update.message.reply_text(
        "📝 *Enter Event Name:*", 
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), 
        parse_mode=ParseMode.MARKDOWN
    )
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    if len(msg) > 50:
        await update.message.reply_text("⚠ Name too long. Try again.")
        return 1
        
    context.user_data['title'] = msg
    await update.message.reply_text("📅 *Enter Date:*\n(e.g. 2026.12.30 or 1405.10.20)", parse_mode=ParseMode.MARKDOWN)
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    dt_obj = parse_smart_date(msg)
    if dt_obj:
        data = get_user_data(uid)
        import uuid
        new_id = f"evt_{uuid.uuid4().hex[:8]}"
        
        # Atomic Update
        try:
            users_collection.update_one(
                {"_id": str(uid)}, 
                {"$set": {f"targets.{new_id}": {
                    "title": context.user_data['title'],
                    "date": dt_obj, 
                    "type": "personal"
                }}}, 
                upsert=True
            )
            await update.message.reply_text("✅ *Saved! Check the App.*", reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN)
        except:
             await update.message.reply_text("⛔ *Database Error.*", reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN)
             
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ *Invalid Date!* Try again.", parse_mode=ParseMode.MARKDOWN)
        return 2

# --- SUPPORT FLOW ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    await update.message.reply_text(
        "💌 *Support*\n"
        "Please write your message for the Admin:",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_SUPPORT

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    if msg == "❌ Cancel": return await cancel(update, context)
    
    await update.message.reply_text("✅ *Sent to Admin!*\nThank you for your feedback.", reply_markup=main_kb(user.id), parse_mode=ParseMode.MARKDOWN)

    if ADMIN_ID:
        text = f"📩 *New Message*\nFrom: {user.full_name} ({user.id})\n\n{msg[:1000]}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode=ParseMode.MARKDOWN)
        except: pass # Admin might have blocked bot
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE FLOW ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id): return
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 *List is empty.*", parse_mode=ParseMode.MARKDOWN)
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']} ({v['date']})", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 *Tap to delete:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    key = query.data.replace("del_", "")
    
    try:
        users_collection.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
        await query.answer("Deleted!")
        await query.delete_message()
    except: 
        await query.answer("Error")

def main():
    if not BOT_TOKEN:
        print("❌ STOP: BOT_TOKEN is missing!")
        return

    keep_alive()
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()
    
    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add)"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    conv_support = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Support)"), support_start)],
        states={GET_SUPPORT: [MessageHandler(filters.TEXT, support_receive)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )

    app.add_handler(conv_add)
    app.add_handler(conv_support)
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))
    
    print("Bot Running (Secured & Robust)...")
    app.run_polling()

if _name_ == "_main_":
    main()