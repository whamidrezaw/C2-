import logging
import threading
import os
import uuid
from datetime import datetime
import jdatetime
import certifi
from flask import Flask, render_template
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# --- CONFIGURATION ---
app = Flask(__name__, template_folder='templates')

# Load Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")  # e.g. https://your-app.render.com

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
client = None
users_collection = None

def connect_db():
    """Establishes or refreshes DB connection safely."""
    global client, users_collection
    if not MONGO_URI:
        logger.error("❌ MONGO_URI is missing!")
        return None
    try:
        # Only connect if not already connected
        if client is None:
            ca = certifi.where()
            client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
            client.admin.command('ping') # Test connection
            db = client['time_manager_db']
            users_collection = db['users']
            logger.info("✅ MONGODB CONNECTED")
        return users_collection
    except Exception as e:
        logger.error(f"❌ DB CONNECTION FAILED: {e}")
        return None

# --- FLASK SERVER ---
@app.route('/')
def home():
    return "Bot is Running. Go to Telegram."

@app.route('/webapp/<user_id>')
def webapp(user_id):
    coll = connect_db()
    if not coll:
        return "Database Error", 500

    # Fetch data
    raw_data = coll.find_one({"_id": str(user_id)})
    targets = raw_data.get('targets', {}) if raw_data else {}
    
    # Pre-process for frontend
    for key, item in targets.items():
        try:
            # Add Persian Date for display
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y/%m/%d")
        except Exception: 
            item['shamsi_date'] = ""
            
    return render_template('index.html', user_data=targets)

def run_flask():
    # Run Flask on port 10000 (common for Render) or 5000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# --- DATA HELPERS ---
def get_user_data(uid):
    coll = connect_db()
    if coll is None: return {"_id": str(uid), "targets": {}}
    
    try:
        data = coll.find_one({"_id": str(uid)})
        if not data:
            coll.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except:
        return {"_id": str(uid), "targets": {}}

# --- DATE PARSER ---
def parse_smart_date(date_str):
    if not date_str: return None
    # Normalize
    date_str = date_str.replace('/', '.').replace('-', '.')
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    
    parts = [p for p in date_str.split('.') if p.isdigit()]
    if len(parts) != 3: return None

    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        
        # Logic: Year is usually > 1000
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None # Ambiguous
        
        final = None
        if y > 1900: 
            final = datetime(y, m, d)
        elif y < 1500: 
            # Convert Jalali to Gregorian
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
            
        return final.strftime("%d.%m.%Y") if final else None
    except: 
        return None

# --- KEYBOARDS ---
def main_kb(uid):
    if not WEBAPP_URL_BASE:
        url = "https://telegram.org" # Fallback
    else:
        url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
        
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 My Events", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")]
    ], resize_keyboard=True)

# --- TELEGRAM HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid) # Init DB entry
    await update.message.reply_text("👋 **Welcome!** Manage your time.", reply_markup=main_kb(uid), parse_mode='Markdown')

# --- THE BRIDGE: Handle Data from Mini App ---
async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    
    if data == "add":
        # Start the Add Conversation
        await add_start(update, context)
        # We need to manually set the state because we are entering from a different handler
        return GET_TITLE 
    elif data == "delete":
        # Trigger Delete logic
        await delete_trigger(update, context)

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    context.user_data['title'] = update.message.text
    await update.message.reply_text("📅 **Enter Date (e.g., 2024.12.25 or 1403.10.01):**", parse_mode='Markdown')
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    uid = update.effective_user.id
    formatted = parse_smart_date(update.message.text)
    
    if formatted:
        coll = connect_db()
        if coll is not None:
            new_id = f"evt_{uuid.uuid4().hex[:8]}"
            new_item = {
                "title": context.user_data['title'],
                "date": formatted,
                "type": "personal"
            }
            coll.update_one({"_id": str(uid)}, {"$set": {f"targets.{new_id}": new_item}}, upsert=True)
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ DB Error", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again:", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    
    if not targets: 
        return await update.message.reply_text("📭 Your list is empty.")
        
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    
    await update.message.reply_text("🗑 **Select an event to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    key = query.data.replace("del_", "")
    
    coll = connect_db()
    if coll is not None:
        coll.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
        await query.answer("Deleted")
        await query.delete_message()
        # Optional: Send confirmation
        # await context.bot.send_message(chat_id=uid, text="🗑 Event deleted.", reply_markup=main_kb(uid))
    else: 
        await query.answer("Error")

def main():
    # 1. Start Flask in Background
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Start Bot
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN is missing")
        return

    app_bot = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation Handler
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(➕|Add)"), add_start),
            # BRIDGE: Listen for Web App Data specifically to start Adding
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data) 
        ],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT, receive_date)]
        },
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    
    app_bot.add_handler(conv)
    app_bot.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(delete_cb))
    
    print("✅ Bot and Mini App are running...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()