import logging
import threading
import random
import jdatetime
import pytz
import json
import os
import copy
from flask import Flask, render_template, request # render_template اضافه شد
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

# ==========================================
# بخش ۱: سرور و مینی اپ
# ==========================================
# تنظیم پوشه تمپلیت برای Flask
app = Flask(__name__, template_folder='templates')

# مسیر اصلی (برای زنده ماندن ربات)
@app.route('/')
def home():
    return "Bot is alive!"

# مسیر مینی اپ (اینجا HTML نمایش داده می‌شود)
@app.route('/webapp/<user_id>')
def webapp(user_id):
    # دریافت اطلاعات کاربر از فایل
    data = get_user_data(user_id)
    targets = data.get("targets", {})
    lang = data.get("lang", "en")
    
    # ارسال داده‌ها به HTML
    return render_template('index.html', user_data=targets, lang=lang)

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# ==========================================
# بخش ۲: تنظیمات
# ==========================================
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"
DATA_FILE = "users_data.json"
# آدرس سایت رندر شما (بسیار مهم)
# بعد از دیپلوی، آدرس سایت خود را اینجا بگذارید. الان موقتی میگذاریم
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com" 

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# (بقیه تنظیمات ثابت می‌ماند)
TZ_GERMANY = pytz.timezone('Europe/Berlin')
TZ_IRAN = pytz.timezone('Asia/Tehran')
GET_TITLE, GET_DATE = range(2)

DEFAULT_TARGETS = {}
all_users_data = {}

# ==========================================
# بخش ۳: مدیریت داده
# ==========================================
def load_data():
    global all_users_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                all_users_data = json.load(f)
        except Exception:
            all_users_data = {}
    else:
        all_users_data = {}

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_users_data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in all_users_data:
        all_users_data[user_id] = {"targets": {}, "lang": "en"}
        save_data()
    return all_users_data[user_id]

def update_user_data(user_id, data):
    user_id = str(user_id)
    all_users_data[user_id] = data
    save_data()

load_data()

# ==========================================
# بخش ۴: مترجم
# ==========================================
def translate_all(text):
    try:
        en = GoogleTranslator(source='auto', target='en').translate(text)
        de = GoogleTranslator(source='auto', target='de').translate(text)
        fa = GoogleTranslator(source='auto', target='fa').translate(text)
        return {"en": en, "de": de, "fa": fa}
    except:
        return {"en": text, "de": text, "fa": text}

# ==========================================
# بخش ۵: کیبوردها (با دکمه مینی اپ)
# ==========================================

def get_main_menu_keyboard(user_id):
    # ساخت آدرس اختصاصی برای هر کاربر
    user_url = f"{WEBAPP_URL_BASE}/webapp/{user_id}"
    
    keyboard = [
        [KeyboardButton("📱 مشاهده در مینی‌اپ", web_app=WebAppInfo(url=user_url))],
        [KeyboardButton("➕ افزودن"), KeyboardButton("🗑 حذف")],
        [KeyboardButton("🇩🇪 DE"), KeyboardButton("🇬🇧 EN"), KeyboardButton("🇮🇷 FA")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==========================================
# بخش ۶: هندلرهای افزودن
# ==========================================
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📝 نام رویداد؟ (فارسی یا آلمانی)", reply_markup=ReplyKeyboardMarkup([["❌"]], resize_keyboard=True))
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌":
        user_id = update.effective_user.id
        await update.message.reply_text("لغو شد.", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    await update.message.reply_text("🔄 ...")
    titles = translate_all(update.message.text)
    context.user_data['titles'] = titles
    await update.message.reply_text(f"✅ عنوان ثبت شد.\n📅 تاریخ؟ (DD.MM.YYYY)")
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "❌":
        await update.message.reply_text("لغو شد.", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END
    
    try:
        datetime.strptime(text, "%d.%m.%Y")
        user_data = get_user_data(user_id)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        user_data['targets'][new_id] = {
            "date": text,
            "labels": context.user_data['titles'],
            "icon": "📌",
            "type": "personal"
        }
        update_user_data(user_id, user_data)
        await update.message.reply_text("✅ اضافه شد!", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ فرمت اشتباه: DD.MM.YYYY")
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    await update.message.reply_text("لغو.", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# ==========================================
# بخش ۷: هندلرهای اصلی
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    get_user_data(user_id)
    await update.message.reply_text("👋 خوش آمدید! از دکمه‌های زیر استفاده کنید:", reply_markup=get_main_menu_keyboard(user_id))

async def handle_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if "DE" in text: user_data['lang'] = "de"
    elif "FA" in text: user_data['lang'] = "fa"
    elif "EN" in text: user_data['lang'] = "en"
    
    update_user_data(user_id, user_data)
    await update.message.reply_text(f"Language changed to {user_data['lang']}", reply_markup=get_main_menu_keyboard(user_id))

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add|Hinzufügen)"), add_start)],
        states={GET_TITLE: [MessageHandler(filters.TEXT, receive_title)], GET_DATE: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^(🇩🇪|🇮🇷|🇬🇧)"), handle_lang))
    application.add_handler(CommandHandler("start", start))
    
    print("Bot Started with Mini App...")
    application.run_polling()

if __name__ == "__main__":
    main()