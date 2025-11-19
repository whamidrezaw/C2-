import logging
import threading
import os
import re
import sys
import asyncio
import traceback
import html
import json
from datetime import datetime

from flask import Flask, render_template
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

# --- 1. ENVIRONMENT & CONFIGURATION (Security: No Hardcoded Secrets) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except (TypeError, ValueError):
    ADMIN_ID = None

# Fail Fast: Stop execution if critical secrets are missing
if not BOT_TOKEN or not MONGO_URI:
    print("🚨 CRITICAL ERROR: BOT_TOKEN or MONGO_URI is missing in Environment Variables.")
    sys.exit(1)

# --- 2. LOGGING SETUP (Production Grade) ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TimeManagerBot")

# Quiet down external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# --- 3. DATABASE LAYER (MongoDB - Solves JSON Concurrency Issues) ---
users_collection = None

def connect_db():
    global users_collection
    try:
        ca = certifi.where()
        client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # Fail fast check
        db = client['time_manager_db']
        users_collection = db['users']
        logger.info("✅ Database Connected Successfully")
    except Exception as e:
        logger.critical(f"❌ Database Connection Failed: {e}")
        sys.exit(1) # Exit if DB is critical

connect_db()

# --- 4. HELPERS & UTILS ---

def get_user_data(uid):
    """Fetch user data, create if not exists."""
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            new_user = {
                "_id": str(uid),
                "joined_at": datetime.utcnow(),
                "targets": {},
                "is_blocked": False
            }
            users_collection.insert_one(new_user)
            return new_user
        return data
    except Exception as e:
        logger.error(f"DB Read Error for {uid}: {e}")
        return None

def update_db(uid, data):
    """Atomic update."""
    try:
        users_collection.update_one({"_id": str(uid)}, {"$set": data}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"DB Write Error for {uid}: {e}")
        return False

def parse_smart_date(date_str):
    """Parses Gregorian and Jalali dates with Persian/English digits."""
    if not date_str: return None, None
    
    # Normalize
    date_str = str(date_str).strip()
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    date_str = re.sub(r'[/\-\s,]+', '.', date_str)
    
    parts = [p for p in date_str.split('.') if p]
    if len(parts) != 3: return None, None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        
        # Heuristic for Year
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None, None

        final_date = None
        
        if y > 1900: # Gregorian
            final_date = datetime(y, m, d)
        elif y < 1500: # Jalali
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        
        if final_date:
            return final_date, final_date.strftime("%d.%m.%Y")
    except: return None, None
    return None, None

# --- 5. FLASK SERVER (Mini App Backend) ---
app = Flask(__name__, template_folder='templates')

@app.route('/')
def home(): return "Status: Online 🟢"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {}) if data else {}
    
    # View preparation
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: 
            item['shamsi_date'] = ""
            
    return render_template('index.html', user_data=targets)

def run_flask():
    # Disable Flask banner to clean up logs
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

# --- 6. TELEGRAM BOT LOGIC ---

# -- Keyboards --
def main_kb(uid):
    if WEBAPP_URL_BASE:
        url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
        btn_app = KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))
    else:
        btn_app = KeyboardButton("⚠️ WebApp Error")

    return ReplyKeyboardMarkup([
        [btn_app],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# -- Error Handler (Global) --
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    if ADMIN_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>{html.escape(tb_string)[-4000:]}</pre>"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode=ParseMode.HTML)
        except: pass

# -- Admin Commands (Security Check Included) --
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Show stats"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return # Silently ignore non-admins
    
    total = users_collection.count_documents({})
    active = users_collection.count_documents({"is_blocked": False})
    
    await update.message.reply_text(
        f"📊 **Statistics**\n\n"
        f"👥 Total Users: `{total}`\n"
        f"✅ Active Users: `{active}`",
        parse_mode=ParseMode.MARKDOWN
    )

# -- User Handlers --
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    first_name = update.effective_user.first_name
    
    # Ensure user exists in DB
    get_user_data(uid)
    
    await update.message.reply_text(
        f"👋 **Hello {first_name}!**\n\n"
        "Welcome to **Time Manager Bot**.\n"
        "I help you track deadlines securely.\n\n"
        "👇 Use the menu below:",
        reply_markup=main_kb(uid),
        parse_mode=ParseMode.MARKDOWN
    )

# -- Conversation States --
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

# -- Add Event Flow --
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 **Enter Event Name:**", 
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    # Input Sanitization (Basic)
    clean_title = html.escape(msg)
    context.user_data['title'] = clean_title
    
    await update.message.reply_text(
        "📅 **Enter Date:**\n"
        "Examples: `2026.12.30` or `1405.10.20`",
        parse_mode=ParseMode.MARKDOWN
    )
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    dt_obj, formatted = parse_smart_date(msg)
    if dt_obj:
        data = get_user_data(uid)
        if not data:
            await update.message.reply_text("⛔ DB Error. Try /start again.", reply_markup=main_kb(uid))
            return ConversationHandler.END

        new_id = f"evt_{int(datetime.now().timestamp())}"
        
        # Creating user object if it was empty
        if 'targets' not in data: data['targets'] = {}

        data['targets'][new_id] = {
            "title": context.user_data['title'],
            "date": formatted, 
            "type": "personal"
        }
        
        if update_db(uid, data):
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("⛔ DB Write Error.", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again.", parse_mode=ParseMode.MARKDOWN)
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("❌ Canceled.", reply_markup=main_kb(uid))
    return ConversationHandler.END

# -- Delete Flow --
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {}) if data else {}
    
    if not targets: 
        return await update.message.reply_text("📭 **List is empty.**", parse_mode=ParseMode.MARKDOWN)
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']} ({v['date']})", callback_data=f"del_{k}")])
    
    await update.message.reply_text("🗑 **Tap to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    
    targets = data.get('targets', {}) if data else {}

    if key in targets:
        del targets[key]
        data['targets'] = targets
        update_db(uid, data)
        await query.answer("Deleted!")
        try:
            await query.delete_message()
        except: pass
    else: 
        await query.answer("Item not found or already deleted.")
        try:
            await query.delete_message()
        except: pass

# -- Support Flow --
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💌 **Support**\n"
        "Write your message/bug report below:",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_SUPPORT

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    
    if msg == "❌ Cancel": return await cancel(update, context)
    
    # Reply to user
    await update.message.reply_text("✅ **Message Sent!**\nThanks for your feedback.", reply_markup=main_kb(user.id), parse_mode=ParseMode.MARKDOWN)

    # Send to Admin
    if ADMIN_ID:
        admin_text = (
            f"📩 **New Support Message**\n"
            f"👤 User: {user.full_name} (`{user.id}`)\n"
            f"📄 Message:\n{html.escape(msg)}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Failed to forward support msg: {e}")
            
    return ConversationHandler.END

# -- Fallback for Unknown Text --
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        "❓ **Please use the buttons below:**", 
        reply_markup=main_kb(uid), 
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        "⛔ **Files are not allowed.** Please send text only.",
        reply_markup=main_kb(uid),
        parse_mode=ParseMode.MARKDOWN
    )

# --- MAIN EXECUTION ---
def main():
    # Start Flask in background
    keep_alive()

    # Setup Telegram Bot
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    # 1. Error Handler
    app.add_error_handler(error_handler)

    # 2. Conversation Handlers
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

    # 3. Commands & Buttons
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command)) # Admin Only
    app.add_handler(CallbackQueryHandler(delete_cb))
    
    # 4. Security Filters (Reject Files)
    app.add_handler(MessageHandler(filters.ATTACHMENT | filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_files))

    # 5. Catch-All (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))

    print(f"Bot Started. Admin ID: {ADMIN_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()