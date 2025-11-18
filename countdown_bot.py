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

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION (اطلاعات خود را دقیق وارد کنید) ---
BOT_TOKEN = "8527713338:AAEhR5T_JISPJqnecfEobu6hELJ6a9RAQrU"
GEMINI_API_KEY = "AIzaSyAMNyRzBnssfBI5wKK8rsQJAIWrE1V_XdM" 
MONGO_URI = "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0"
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"

# Setup AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
except: pass

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE MANAGER (NEW & ROBUST) ---
mongo_client = None
users_collection = None

def connect_to_mongo():
    """تلاش برای اتصال به دیتابیس و بازگرداندن وضعیت"""
    global mongo_client, users_collection
    try:
        if mongo_client:
            mongo_client.close() # بستن اتصال قبلی اگر خراب است
        
        ca = certifi.where()
        mongo_client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping') # تست واقعی اتصال
        
        db = mongo_client['time_manager_db']
        users_collection = db['users']
        logger.info("✅ MongoDB Re-Connected Successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB Connection Failed: {e}")
        users_collection = None
        return False

# اتصال اولیه
connect_to_mongo()

# --- DATA FUNCTIONS ---
def get_user_data(user_id):
    # اگر اتصال قطع بود، دوباره وصل شو
    if users_collection is None:
        if not connect_to_mongo():
            return {"_id": str(user_id), "targets": {}} # هنوز قطع است
            
    try:
        uid = str(user_id)
        data = users_collection.find_one({"_id": uid})
        if not data:
            new_data = {"_id": uid, "targets": {}}
            users_collection.insert_one(new_data)
            return new_data
        return data
    except Exception as e:
        logger.error(f"Read Error: {e}")
        return {"_id": str(user_id), "targets": {}}

def update_user_data(user_id, data):
    # اگر اتصال قطع بود، تلاش کن وصل شوی
    if users_collection is None:
        if not connect_to_mongo():
            return False # شکست در اتصال

    try:
        users_collection.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Write Error: {e}")
        return False

# --- FLASK ---
@app.route('/')
def home(): return "Bot is running (Robust DB)"

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

# --- HELPERS ---
def parse_smart_date(date_str):
    date_str = date_str.replace('/', '.').replace('-', '.')
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    parts = date_str.split('.')
    if len(parts) != 3: return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        if y > 1900: final = datetime(y, m, d)
        elif y < 1500: 
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
        else: return None
        return final.strftime("%d.%m.%Y")
    except: return None

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
    # تست اتصال هنگام استارت
    if get_user_data(uid):
        await update.message.reply_text("👋 **Welcome!**\nDB Connected ✅", reply_markup=get_main_kb(uid), parse_mode='Markdown')
    else:
        await update.message.reply_text("⚠️ **Database Error!**\nI cannot save data right now.", reply_markup=get_main_kb(uid))

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "❌" in update.message.text: return await cancel(update, context)
    context.user_data['title'] = update.message.text
    await update.message.reply_text("📅 **Enter Date:**\n(e.g. 2026.12.30 or 1405.10.10)", parse_mode='Markdown')
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if "❌" in msg: return await cancel(update, context)
    
    formatted_date = parse_smart_date(msg)
    if formatted_date:
        data = get_user_data(uid)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "title": context.user_data['title'],
            "date": formatted_date,
            "type": "personal"
        }
        
        # تلاش برای ذخیره و بررسی نتیجه
        success = update_user_data(uid, data)
        
        if success:
            await update.message.reply_text("✅ **Saved Successfully!**", reply_markup=get_main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ **Error Saving!**\nDatabase connection lost.", reply_markup=get_main_kb(uid), parse_mode='Markdown')
            
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date.**", parse_mode='Markdown')
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    if not data.get('targets'): return await update.message.reply_text("📭 Empty List.")
    kb = []
    for k, v in data['targets'].items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 **Delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    if key in data.get('targets', {}):
        del data['targets'][key]
        if update_user_data(uid, data):
            await query.answer("Deleted!")
            await query.delete_message()
        else:
            await query.answer("DB Error!")
    else: await query.answer("Not found")

async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty.")
    await update.message.reply_text("🧠 Analyzing...")
    try:
        txt = "\n".join([f"- {v['title']}: {v['date']}" for v in targets.values()])
        response = model.generate_content(f"Analyze deadlines: {txt}")
        await update.message.reply_text(response.text)
    except: await update.message.reply_text("AI Error.")

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
    print("Bot Running (Robust DB Check)...")
    app.run_polling()

if __name__ == "__main__":
    main()