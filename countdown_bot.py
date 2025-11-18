import logging
import threading
import json
import os
import re
from datetime import datetime
from flask import Flask, render_template
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from pymongo import MongoClient
import certifi
import jdatetime
import config  # Imports from config.py if available

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION ---
# Replace these with your actual values if you don't use config.py
BOT_TOKEN = getattr(config, 'BOT_TOKEN', "8527713338:AAEhR5T_JISPJqnecfEobu6hELJ6a9RAQrU")
MONGO_URI = getattr(config, 'MONGO_URI', "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0")
WEBAPP_URL_BASE = getattr(config, 'WEBAPP_URL_BASE', "https://my-bot-new.onrender.com")

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
users_collection = None
try:
    # Secure SSL connection for Render
    ca = certifi.where()
    client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
    
    # Ping to test connection
    client.admin.command('ping')
    
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅ MONGODB CONNECTED SUCCESSFULLY")
except Exception as e:
    logger.error(f"❌ DB CONNECTION FAILED: {e}")

# --- FLASK SERVER ---
@app.route('/')
def home(): 
    return "Bot is Running (English Version)"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    # Calculate display dates (Gregorian to Shamsi for display only)
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            # Format: YYYY.MM.DD
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: 
            item['shamsi_date'] = ""
            
    return render_template('index.html', user_data=targets)

def run_server(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run_server, daemon=True).start()

# --- DATA HELPERS ---
def get_user_data(uid):
    if users_collection is None: return {"_id": str(uid), "targets": {}}
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            users_collection.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except: return {"_id": str(uid), "targets": {}}

def update_db(uid, data):
    if users_collection is None: return False
    try:
        users_collection.update_one({"_id": str(uid)}, {"$set": data}, upsert=True)
        return True
    except: return False

# --- SMART DATE PARSER ---
def parse_smart_date(date_str):
    """
    Parses inputs like: 
    2026.12.01, 01/12/2026, 1405-10-20
    Handles Persian/Arabic digits.
    Returns: (datetime_object, "DD.MM.YYYY")
    """
    # 1. Convert Persian/Arabic digits to English
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    
    # 2. Normalize separators (replace / - space with dot)
    date_str = re.sub(r'[/\-\s,]+', '.', date_str)
    
    # 3. Extract parts
    parts = [p for p in date_str.split('.') if p]
    
    if len(parts) != 3: return None, None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        
        # Detect Year (4 digits)
        if p1 > 1000: # Format YYYY.MM.DD
            y, m, d = p1, p2, p3
        elif p3 > 1000: # Format DD.MM.YYYY
            y, m, d = p3, p2, p1
        else: 
            return None, None

        final_date = None
        
        # Detect Calendar System
        if y > 1900: # Gregorian
            final_date = datetime(y, m, d)
        elif y < 1500: # Jalali (Shamsi)
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        
        if final_date:
            return final_date, final_date.strftime("%d.%m.%Y")
            
    except Exception as e:
        logger.error(f"Date Parse Error: {e}")
        return None, None
    return None, None

# --- KEYBOARDS ---
def main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")]
    ], resize_keyboard=True, is_persistent=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome!**\n\nManage your time effectively.\nUse the buttons below:",
        reply_markup=main_kb(uid), parse_mode='Markdown'
    )

# --- CATCH-ALL HANDLER (For random text) ---
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        "❓ **I didn't understand that.**\n\nPlease use the buttons below to manage events:",
        reply_markup=main_kb(uid),
        parse_mode='Markdown'
    )

# --- ADD FLOW ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 **Enter Event Name:**", 
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), 
        parse_mode='Markdown'
    )
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    context.user_data['title'] = msg
    await update.message.reply_text(
        "📅 **Enter Date:**\n"
        "Accepts Gregorian or Shamsi.\n"
        "Examples: `2026.12.01` or `1405.10.20`",
        parse_mode='Markdown'
    )
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    dt_obj, formatted = parse_smart_date(msg)
    
    if dt_obj:
        data = get_user_data(uid)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "title": context.user_data['title'],
            "date": formatted, 
            "type": "personal"
        }
        
        if update_db(uid, data):
            await update.message.reply_text("✅ **Saved Successfully!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ **Database Error!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again.", parse_mode='Markdown')
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE FLOW ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    
    if not targets: 
        return await update.message.reply_text("📭 **List is empty.**", parse_mode='Markdown')
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']} ({v['date']})", callback_data=f"del_{k}")])
    
    await update.message.reply_text("🗑 **Tap to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    
    if key in data.get('targets', {}):
        del data['targets'][key]
        update_db(uid, data)
        await query.answer("Deleted!")
        await query.delete_message()
    else: 
        await query.answer("Item not found")

# --- MAIN ---
def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation for Adding
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add)"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    app.add_handler(conv)
    
    # Button Handlers
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    
    # Start Command
    app.add_handler(CommandHandler("start", start))
    
    # Callback for Delete
    app.add_handler(CallbackQueryHandler(delete_cb))

    # Catch-All Handler (Must be last) - Responds to random text
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))
    
    print("Bot Running (Final English Version)...")
    app.run_polling()

if __name__ == "__main__":
    main()