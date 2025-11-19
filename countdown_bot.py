import logging
import threading
import json
import os
import re
import hmac
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, abort
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from pymongo import MongoClient
import certifi
import jdatetime
import ssl

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except:
    ADMIN_ID = None

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION (Persistent) ---
users_collection = None
if MONGO_URI:
    try:
        ca = certifi.where()
        client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client['time_manager_db']
        users_collection = db['users']
        logger.info("✅ MONGODB CONNECTED")
    except Exception as e:
        logger.error(f"❌ DB CONNECTION FAILED: {e}")

# --- SECURITY HELPER ---
def generate_secure_url(user_id):
    """Generate a signed URL to prevent ID spoofing"""
    if not BOT_TOKEN or not WEBAPP_URL_BASE: return None
    # Create a hash signature using the user_id and bot_token
    signature = hmac.new(BOT_TOKEN.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{WEBAPP_URL_BASE}/webapp/{user_id}?sig={signature}"

def verify_signature(user_id, signature):
    """Verify the URL signature"""
    if not BOT_TOKEN: return False
    expected = hmac.new(BOT_TOKEN.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is Running (Secure)"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    # Security Check
    signature = request.args.get('sig')
    if not signature or not verify_signature(user_id, signature):
        return "⛔ Access Denied: Invalid Signature", 403

    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    # Display Logic
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: item['shamsi_date'] = ""
            
    return render_template('index.html', user_data=targets)

def run_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# --- ATOMIC DB OPERATIONS ---
def get_user_data(uid):
    if users_collection is None: return {"_id": str(uid), "targets": {}}
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            # Atomic Insert
            users_collection.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except: return {"_id": str(uid), "targets": {}}

def add_event_db(uid, event_data):
    if users_collection is None: return False
    # Generate unique ID
    event_id = f"evt_{uuid.uuid4().hex[:8]}" 
    try:
        # Atomic Update: Only adds the new event field
        users_collection.update_one(
            {"_id": str(uid)},
            {"$set": {f"targets.{event_id}": event_data}},
            upsert=True
        )
        return True
    except: return False

def delete_event_db(uid, event_id):
    if users_collection is None: return False
    try:
        # Atomic Delete: Only removes the specific field
        users_collection.update_one(
            {"_id": str(uid)},
            {"$unset": {f"targets.{event_id}": ""}}
        )
        return True
    except: return False

# --- PARSER ---
def parse_smart_date(date_str):
    date_str = str(date_str).strip()
    # Validation: Check length
    if len(date_str) > 20: return None
    
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

# --- KEYBOARD ---
def main_kb(uid):
    # Secure URL Generation
    url = generate_secure_url(uid)
    if not url: return None # Should not happen if env vars are set
    
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome!**\nSecure Time Manager.\nSelect an option:",
        reply_markup=main_kb(uid), parse_mode='Markdown'
    )

async def unknown_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("❓ **Use buttons below:**", reply_markup=main_kb(uid), parse_mode='Markdown')

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("⛔ **Text only please.**", reply_markup=main_kb(uid), parse_mode='Markdown')

# --- ADD ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 **Event Name:**", 
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), 
        parse_mode='Markdown'
    )
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    # Validation: Max length
    if len(msg) > 50:
        await update.message.reply_text("⚠️ Name too long (Max 50 chars). Try again.")
        return 1
        
    context.user_data['title'] = msg
    await update.message.reply_text("📅 **Date:**\n(e.g. 2026.12.30)", parse_mode='Markdown')
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    formatted = parse_smart_date(msg)
    if formatted:
        event_data = {
            "title": context.user_data['title'],
            "date": formatted, 
            "type": "personal"
        }
        
        if add_event_to_db(uid, event_data):
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ DB Error.", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date.** Try again.", parse_mode='Markdown')
        return 2

# --- SUPPORT ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💌 **Message for Admin:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_SUPPORT

async def support_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    if msg == "❌ Cancel": return await cancel(update, context)
    
    if ADMIN_ID:
        try:
            # Clean input
            safe_msg = msg[:1000] # Max length limit
            text = f"📩 **Support**\nUser: `{user.id}`\n\n{safe_msg}"
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode='Markdown')
            await update.message.reply_text("✅ **Sent!**", reply_markup=main_kb(user.id), parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ Send failed.", reply_markup=main_kb(user.id))
    else:
        await update.message.reply_text("⚠️ Not configured.", reply_markup=main_kb(user.id))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE ---
async def delete_trig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty.")
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    key = query.data.replace("del_", "")
    
    if delete_event_from_db(uid, key):
        await query.answer("Deleted!")
        await query.delete_message()
    else: await query.answer("Not found")

def main():
    if not BOT_TOKEN:
        print("❌ STOP: Missing BOT_TOKEN")
        return

    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
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
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trig))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    
    # Security: Reject files
    app.add_handler(MessageHandler(filters.ATTACHMENT | filters.PHOTO | filters.Document.ALL, handle_files))
    # Fallback
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_msg))
    
    print("Bot Running (High Security)...")
    app.run_polling()

if __name__ == "__main__":
    main()