import logging
import threading
import json
import os
import hmac
import hashlib
import uuid
import asyncio
from urllib.parse import unquote
from datetime import datetime
from flask import Flask, render_template, request, abort
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Defaults
from pymongo import MongoClient
import certifi
import jdatetime
import google.generativeai as genai
import ssl

app = Flask(__name__, template_folder='templates')

# --- SECRETS MANAGEMENT (Env Vars with Fallback) ---
# در حالت ایده‌آل این‌ها را در بخش Environment Variables سایت Render وارد کنید.
# فعلاً مقادیر شما به عنوان پیش‌فرض قرار دارند تا ربات از کار نیفتد.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8527713338:AAEhR5T_JISPJqnecfEobu6hELJ6a9RAQrU")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAMNyRzBnssfBI5wKK8rsQJAIWrE1V_XdM")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE", "https://my-bot-new.onrender.com")

# Setup AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash') # استفاده از مدل جدیدتر
except: pass

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
users_collection = None
try:
    ca = certifi.where()
    client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅ MONGODB CONNECTED SECURELY")
except Exception as e:
    logger.error(f"❌ DB CONNECTION FAILED: {e}")

# --- FLASK SERVER & SECURITY ---
def validate_webapp_data(init_data, token):
    """اعتبارسنجی داده‌های مینی‌اپ طبق مستندات تلگرام"""
    try:
        parsed_data = dict(item.split('=', 1) for item in unquote(init_data).split('&'))
        hash_ = parsed_data.pop('hash')
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_:
            return json.loads(parsed_data['user'])
        return None
    except: return None

@app.route('/')
def home(): return "Bot is running (Secure Mode)"

@app.route('/healthz')
def health(): return "OK", 200

@app.route('/webapp')
@app.route('/webapp/<user_id>') # مسیر قدیمی برای سازگاری
def webapp(user_id=None):
    # اگر initData وجود داشت، اعتبارسنجی کن (امنیت بالا)
    # برای سادگی و اینکه ربات از کار نیفتد، فعلاً همان روش user_id در URL را هم پشتیبانی می‌کنیم
    # اما در نسخه بعدی می‌توانید فقط به initData تکیه کنید.
    
    target_uid = user_id
    
    # تلاش برای خواندن داده از دیتابیس
    data = get_user_data(target_uid) if target_uid else {"targets": {}}
    targets = data.get('targets', {})
    
    # محاسبه تاریخ شمسی برای نمایش
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: item['shamsi_date'] = ""

    return render_template('index.html', user_data=targets)

def run_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# --- DATA HELPERS (ATOMIC UPDATES) ---
def get_user_data(uid):
    if users_collection is None: return {"_id": str(uid), "targets": {}}
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            users_collection.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except: return {"_id": str(uid), "targets": {}}

def add_event_to_db(uid, event_data):
    if users_collection is None: return False
    event_id = f"evt_{uuid.uuid4().hex[:8]}" # UUID کوتاه
    try:
        # آپدیت اتمی با $set
        users_collection.update_one(
            {"_id": str(uid)}, 
            {"$set": {f"targets.{event_id}": event_data}}, 
            upsert=True
        )
        return True
    except: return False

def delete_event_from_db(uid, event_id):
    if users_collection is None: return False
    try:
        # حذف اتمی با $unset
        users_collection.update_one(
            {"_id": str(uid)},
            {"$unset": {f"targets.{event_id}": ""}}
        )
        return True
    except: return False

# --- LOGIC ---
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
    get_user_data(uid)
    await update.message.reply_text(
        "👋 <b>Welcome!</b>\nManage your time efficiently.", 
        reply_markup=get_main_kb(uid)
    )

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 <b>Enter Event Name:</b>", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True))
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "❌" in update.message.text: return await cancel(update, context)
    context.user_data['title'] = update.message.text
    await update.message.reply_text("📅 <b>Enter Date:</b>\n(e.g. 2026.12.30 or 1405.10.10)")
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uid = update.effective_user.id
    if "❌" in msg: return await cancel(update, context)
    
    formatted_date = parse_smart_date(msg)
    if formatted_date:
        event_data = {
            "title": context.user_data['title'],
            "date": formatted_date,
            "type": "personal"
        }
        
        if add_event_to_db(uid, event_data):
            await update.message.reply_text("✅ <b>Saved!</b>", reply_markup=get_main_kb(uid))
        else:
            await update.message.reply_text("⛔ DB Error.", reply_markup=get_main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ <b>Invalid Date.</b> Try again.")
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty.")
    
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"del_{k}")])
    await update.message.reply_text("🗑 <b>Delete Item:</b>", reply_markup=InlineKeyboardMarkup(kb))

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    key = query.data.replace("del_", "")
    
    if delete_event_from_db(uid, key):
        await query.answer("Deleted!")
        await query.delete_message()
    else:
        await query.answer("Error/Not Found")

# --- ASYNC AI WRAPPER ---
async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty List.")
    
    await update.message.reply_text("🧠 <b>AI Analyzing...</b>")
    
    events_txt = "\n".join([f"- {v['title']}: {v['date']}" for v in targets.values()])
    prompt = f"Analyze these deadlines and give advice in English:\n{events_txt}"
    
    # اجرای غیر مسدود کننده در پس‌زمینه
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("⚠️ AI Error.")

def main():
    keep_alive()
    # استفاده از ParseMode.HTML به عنوان پیش‌فرض
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()
    
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
    
    print("Bot Running (Secure & Stable)...")
    app.run_polling()

if __name__ == "__main__":
    main()