import logging
import threading
import json
import os
from datetime import datetime
from flask import Flask, render_template
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from pymongo import MongoClient
import certifi
import jdatetime
import google.generativeai as genai
import ssl
import config  # Importing configuration from config.py

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION IMPORT ---
# We read variables from config.py now
BOT_TOKEN = config.BOT_TOKEN
GEMINI_API_KEY = config.GEMINI_API_KEY
MONGO_URI = config.MONGO_URI
WEBAPP_URL_BASE = config.WEBAPP_URL_BASE

# Setup AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
except: pass

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION (SSL ULTRA FIX) ---
try:
    ca = certifi.where()
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=ca,
        serverSelectionTimeoutMS=5000
    )
    # Test Connection
    client.admin.command('ping')
    
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅✅✅ MONGODB CONNECTED SUCCESSFULLY! ✅✅✅")
    
except Exception as e:
    logger.error(f"❌ CONNECTION FAILED: {e}")
    users_collection = None 

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is running (Config Separated)"

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

# --- DATA HELPERS ---
def get_user_data(user_id):
    if users_collection is None: return {"_id": str(user_id), "targets": {}}
    
    uid = str(user_id)
    try:
        data = users_collection.find_one({"_id": uid})
        if not data:
            new_data = {"_id": uid, "targets": {}}
            users_collection.insert_one(new_data)
            return new_data
        return data
    except: return {"_id": uid, "targets": {}}

def update_user_data(user_id, data):
    if users_collection is None: return
    try: users_collection.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)
    except: pass

# --- SMART DATE PARSER ---
def parse_smart_date(date_str):
    date_str = date_str.replace('/', '.').replace('-', '.')
    persian_nums = "۰۱۲۳۴۵۶۷۸۹"
    arabic_nums = "٠١٢٣٤٥٦٧٨٩"
    english_nums = "0123456789"
    trans_table = str.maketrans(persian_nums + arabic_nums, english_nums * 2)
    date_str = date_str.translate(trans_table)
    
    parts = date_str.split('.')
    if len(parts) != 3: return None, None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None, None

        if y > 1900: final_date = datetime(y, m, d)
        elif y < 1500: 
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        else: return None, None

        return final_date.strftime("%d.%m.%Y")
    except: return None, None

# --- KEYBOARDS ---
def get_main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open Mini App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("🧠 AI Mentor")],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")]
    ], resize_keyboard=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome!**\nManage your time effectively.", 
        reply_markup=get_main_kb(uid), parse_mode='Markdown'
    )

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    context.user_data['title'] = msg
    await update.message.reply_text("📅 **Enter Date:**\n(e.g. 2026.12.30 or 1405.10.10)", parse_mode='Markdown')
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if msg == "❌ Cancel": return await cancel(update, context)
    
    formatted_date = parse_smart_date(msg)
    if formatted_date:
        data = get_user_data(uid)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "title": context.user_data['title'],
            "date": formatted_date,
            "type": "personal"
        }
        update_user_data(uid, data)
        await update.message.reply_text("✅ **Saved!**", reply_markup=get_main_kb(uid), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date.** Try again.", parse_mode='Markdown')
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty List.")
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Delete Item:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    if key in data.get('targets', {}):
        del data['targets'][key]
        update_user_data(uid, data)
        await query.answer("Deleted!")
        await query.delete_message()
    else: await query.answer("Not found")

async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty List.")
    
    await update.message.reply_text("🧠 **AI Analyzing...**", parse_mode='Markdown')
    events_txt = "\n".join([f"- {v['title']}: {v['date']}" for v in targets.values()])
    prompt = f"Analyze these deadlines and give advice in English:\n{events_txt}"
    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ AI Error")

def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add)"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(MessageHandler(filters.Regex("^(🧠|AI)"), mentor_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    print("Bot Running (Separated Config)...")
    app.run_polling()

if __name__ == "__main__":
    main()