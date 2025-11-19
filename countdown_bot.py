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
import ssl

app = Flask(__name__, template_folder='templates')

# --- SECURITY: Load from Environment Variables ---
# این متغیرها باید در سایت Render بخش Environment تعریف شده باشند
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

# تلاش برای خواندن آیدی ادمین (اگر نبود، نادیده بگیر)
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except:
    ADMIN_ID = None

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
users_collection = None

if not MONGO_URI:
    logger.error("❌ CRITICAL: MONGO_URI is missing in Environment Variables!")
else:
    try:
        # اتصال امن با استفاده از گواهی certifi
        ca = certifi.where()
        client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
        
        # تست اتصال
        client.admin.command('ping')
        
        db = client['time_manager_db']
        users_collection = db['users']
        logger.info("✅ MONGODB CONNECTED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"❌ DB CONNECTION FAILED: {e}")
        users_collection = None

# --- FLASK SERVER ---
@app.route('/')
def home(): return "Bot is Running (Secure Mode)"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    
    # محاسبه تاریخ شمسی برای نمایش در مینی‌اپ
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
    Converts Persian/Arabic digits & detects Jalali/Gregorian dates.
    Returns: DD.MM.YYYY (Gregorian)
    """
    # 1. تبدیل اعداد فارسی/عربی به انگلیسی
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    
    # 2. استانداردسازی جداکننده‌ها
    date_str = re.sub(r'[/\-\s,]+', '.', date_str)
    parts = [p for p in date_str.split('.') if p]
    
    if len(parts) != 3: return None, None
    
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        
        # تشخیص سال (۴ رقمی)
        if p1 > 1000: y, m, d = p1, p2, p3 # YYYY.MM.DD
        elif p3 > 1000: y, m, d = p3, p2, p1 # DD.MM.YYYY
        else: return None, None

        final_date = None
        if y > 1900: # میلادی
            final_date = datetime(y, m, d)
        elif y < 1500: # شمسی
            j_date = jdatetime.date(y, m, d).togregorian()
            final_date = datetime(j_date.year, j_date.month, j_date.day)
        
        if final_date:
            return final_date, final_date.strftime("%d.%m.%Y")
    except: return None, None
    return None, None

# --- KEYBOARDS ---
def main_kb(uid):
    # اگر آدرس سایت در متغیرها نبود، دکمه مینی‌اپ کار نمی‌کند (جلوگیری از کرش)
    if WEBAPP_URL_BASE:
        url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
        btn_app = KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))
    else:
        btn_app = KeyboardButton("⚠️ Setup URL Env Var")

    return ReplyKeyboardMarkup([
        [btn_app],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# --- STATES ---
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome to Time Manager!**\n\n"
        "I help you track your important dates.\n"
        "• **Add Event:** Supports Gregorian & Persian dates.\n"
        "• **Mini App:** Visual dashboard.\n\n"
        "👇 **Select an option below:**",
        reply_markup=main_kb(uid), parse_mode='Markdown'
    )

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        "❓ **I didn't understand.**\nPlease use the buttons below:",
        reply_markup=main_kb(uid), parse_mode='Markdown'
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
        "Examples:\n"
        "• `2026.12.30` (Gregorian)\n"
        "• `1405.10.20` (Jalali)\n"
        "• `۲۰.۱۰.۱۴۰۵`",
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
            await update.message.reply_text("✅ **Saved! Check the App.**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ **Database Error.**", reply_markup=main_kb(uid), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again.", parse_mode='Markdown')
        return 2

# --- SUPPORT FLOW ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💌 **Support**\n"
        "Please write your message for the Admin:",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return GET_SUPPORT

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    if msg == "❌ Cancel": return await cancel(update, context)
    
    # تشکر از کاربر
    await update.message.reply_text("✅ **Sent to Admin!**\nThank you for your feedback.", reply_markup=main_kb(user.id), parse_mode='Markdown')

    # ارسال به ادمین (اگر در تنظیمات ست شده باشد)
    if ADMIN_ID:
        text = f"📩 **New Message**\nFrom: {user.full_name} (`{user.id}`)\n\n{msg}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE FLOW ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 **List is empty.**", parse_mode='Markdown')
    
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

def main():
    # چک کردن متغیر محیطی برای توکن
    if not BOT_TOKEN:
        print("❌ STOP: BOT_TOKEN is missing in Environment Variables!")
        return

    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
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
    
    # Catch-All
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))
    
    print("Bot Running (Secure & Clean)...")
    app.run_polling()

if __name__ == "__main__":
    main()