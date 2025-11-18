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

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION ---
BOT_TOKEN = "8527713338:AAEhR5T_JISPJqnecfEobu6hELJ6a9RAQrU"
GEMINI_API_KEY = "AIzaSyAMNyRzBnssfBI5wKK8rsQJAIWrE1V_XdM"
MONGO_URI = "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0"
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"

# Setup AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP ---
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("Connected to MongoDB")
except Exception as e:
    logger.error(f"MongoDB Connection Failed: {e}")

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is running (Smart Numerals)"

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
            item['shamsi_date'] = "N/A"

    return render_template('index.html', user_data=targets)

def run_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# --- DATA HELPERS ---
def get_user_data(user_id):
    uid = str(user_id)
    data = users_collection.find_one({"_id": uid})
    if not data:
        new_data = {"_id": uid, "targets": {}}
        users_collection.insert_one(new_data)
        return new_data
    return data

def update_user_data(user_id, data):
    users_collection.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)

# --- SMART DATE PARSER (با پشتیبانی اعداد فارسی) ---
def parse_smart_date(date_str):
    """
    1. Converts Persian/Arabic digits to English.
    2. Detects Gregorian or Jalali.
    3. Returns Standard Gregorian DD.MM.YYYY
    """
    # 1. تبدیل اعداد فارسی/عربی به انگلیسی
    persian_nums = "۰۱۲۳۴۵۶۷۸۹"
    arabic_nums = "٠١٢٣٤٥٦٧٨٩"
    english_nums = "0123456789"
    
    trans_table = str.maketrans(persian_nums + arabic_nums, english_nums * 2)
    date_str = date_str.translate(trans_table)

    # 2. نرمال‌سازی جداکننده‌ها
    date_str = date_str.replace('/', '.').replace('-', '.')
    parts = date_str.split('.')
    
    if len(parts) != 3: return None, None
    
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        final_date = None
        
        # اگر سال > 1900 -> میلادی
        if y > 1900:
            final_date = datetime(y, m, d)
        # اگر سال < 1500 -> شمسی (فرض بر جلالی)
        elif y < 1500:
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        else:
            return None, None 

        return final_date, final_date.strftime("%d.%m.%Y")
    except: return None, None

# --- UI TEXTS ---
UI = {
    "en": { 
        "welcome": "👋 **Welcome!**\nTime Management Bot.\nUse buttons below:",
        "open_app": "📱 Open App", "add": "➕ Add Event", "del": "🗑 Delete", "mentor": "🧠 AI Mentor",
        "ask_name": "📝 **Enter Event Name:**",
        "ask_date": "📅 **Enter Date:**\n(Support Persian/English Digits)\nExamples:\n• `2026.12.30`\n• `۱۴۰۵/۱۰/۲۰`",
        "saved": "✅ **Event Saved!**", "error": "❌ **Invalid Date!**\nTry again: `YYYY.MM.DD`", "cancel": "❌ Cancel",
        "empty": "📭 List is empty.", "del_ask": "🗑 **Delete Item:**", "deleted": "✅ Deleted.",
        "mentor_thinking": "🧠 **AI Analyzing...**"
    }
}
def get_text(lang, key): return UI["en"][key]

# --- KEYBOARDS ---
def get_main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("🧠 AI Mentor")],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete")]
    ], resize_keyboard=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_data(user.id)
    await update.message.reply_text(get_text('en', "welcome"), reply_markup=get_main_kb(user.id), parse_mode='Markdown')

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text('en', "ask_name"), reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if "❌" in msg: return await cancel(update, context)
    context.user_data['title'] = msg
    await update.message.reply_text(get_text('en', "ask_date"), parse_mode='Markdown')
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if "❌" in msg: return await cancel(update, context)
    
    # Smart Parsing (Persian Digits Support)
    dt_obj, formatted_date = parse_smart_date(msg)
    
    if dt_obj:
        data = get_user_data(uid)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "title": context.user_data['title'],
            "date": formatted_date, # Always Gregorian English Digits
            "type": "personal"
        }
        update_user_data(uid, data)
        await update.message.reply_text(get_text('en', "saved"), reply_markup=get_main_kb(uid), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await update.message.reply_text(get_text('en', "error"), parse_mode='Markdown')
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text('en', "cancel"), reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text("📭 List is empty.")
    
    kb = []
    for k, v in data['targets'].items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Delete Item:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    
    if key in data['targets']:
        del data['targets'][key]
        update_user_data(uid, data)
        await query.answer("Deleted")
        await query.delete_message()
    else: await query.answer("Not found")

async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text("📭 List is empty.")
    
    await update.message.reply_text("🧠 **AI Analyzing...**", parse_mode='Markdown')
    
    events_txt = "\n".join([f"- {v['title']}: {v['date']}" for v in data['targets'].values()])
    prompt = f"Analyze these deadlines and give short advice in English:\n{events_txt}"
    
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
    
    print("Bot Running (Smart Persian Input)...")
    app.run_polling()

if __name__ == "__main__":
    main()