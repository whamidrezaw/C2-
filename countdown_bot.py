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

# Your MongoDB URI
MONGO_URI = "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0"

# Your Render URL (Ensure https)
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"

# Setup AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅ Connected to MongoDB")
except Exception as e:
    logger.error(f"❌ MongoDB Error: {e}")

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is running (English Core)"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    # Fetch user data for the Mini App
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    # Pre-calculate Numeric Jalali dates for display
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            # Format: YYYY.MM.DD (Numeric)
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except:
            item['shamsi_date'] = ""

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

# --- SMART DATE PARSER ---
def parse_smart_date(date_str):
    """
    1. Converts Persian/Arabic digits to English.
    2. Detects Gregorian vs Jalali based on year.
    3. Returns Standard Gregorian String (DD.MM.YYYY).
    """
    # Convert digits
    persian_nums = "۰۱۲۳۴۵۶۷۸۹"
    arabic_nums = "٠١٢٣٤٥٦٧٨٩"
    english_nums = "0123456789"
    trans_table = str.maketrans(persian_nums + arabic_nums, english_nums * 2)
    date_str = date_str.translate(trans_table)

    # Normalize separators
    date_str = date_str.replace('/', '.').replace('-', '.')
    parts = date_str.split('.')
    
    if len(parts) != 3: return None, None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        
        # Determine which part is the Year (usually first or last)
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None, None # Can't determine year

        final_date = None
        
        # Logic: Year > 1900 = Gregorian, Year < 1500 = Jalali
        if y > 1900:
            final_date = datetime(y, m, d)
        elif y < 1500:
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        else:
            return None, None

        return final_date.strftime("%d.%m.%Y")
    except Exception as e:
        logger.error(f"Date Parse Error: {e}")
        return None, None

# --- KEYBOARDS ---
def get_main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open Mini App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("🧠 AI Mentor")],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")]
    ], resize_keyboard=True)

# --- BOT HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome!**\nI am your Time Manager.\n\n"
        "Use the buttons below to manage your events.",
        reply_markup=get_main_kb(uid),
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
        "You can type Gregorian (2026.12.01) or Shamsi (1405.09.10).\n"
        "I support Persian/English numbers.",
        parse_mode='Markdown'
    )
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
            "title": context.user_data['title'], # Raw input, no translation
            "date": formatted_date, # Always stored as DD.MM.YYYY (Gregorian)
            "type": "personal"
        }
        update_user_data(uid, data)
        await update.message.reply_text("✅ **Event Saved Successfully!**", reply_markup=get_main_kb(uid), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!**\nPlease try again (e.g., 2025.12.01 or 1404.09.10)", parse_mode='Markdown')
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE FLOW ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text("📭 List is empty.")
    
    kb = []
    for k, v in data['targets'].items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']} ({v['date']})", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Select item to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    
    if key in data['targets']:
        del data['targets'][key]
        update_user_data(uid, data)
        await query.answer("Deleted!")
        await query.delete_message()
    else: await query.answer("Item not found")

# --- AI MENTOR ---
async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text("📭 Add events first!")
    
    await update.message.reply_text("🧠 **AI is analyzing your schedule...**", parse_mode='Markdown')
    
    events_txt = "\n".join([f"- {v['title']}: {v['date']}" for v in data['targets'].values()])
    prompt = f"You are a strict time management mentor. Analyze these deadlines and give short, actionable advice in English:\n{events_txt}"
    
    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("⚠️ AI is currently unavailable.")

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
    
    print("Bot Started (English Final)...")
    app.run_polling()

if __name__ == "__main__":
    main()