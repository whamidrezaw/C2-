import logging
import threading
import random
import jdatetime
import pytz
import json
import os
from flask import Flask, render_template
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

app = Flask(__name__, template_folder='templates')

# --- CONFIG ---
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"
DATA_FILE = "users_data.json"
# آدرس سایت رندر خود را اینجا بگذارید
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com" 

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ROUTES ---
@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    # ارسال داده‌ها به HTML
    return render_template('index.html', user_data=data.get('targets', {}), lang=data.get('lang', 'en'))

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# --- DATA MANAGER ---
DEFAULT_TARGETS = {}
all_users_data = {}

def load_data():
    global all_users_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                all_users_data = json.load(f)
        except: all_users_data = {}
    else: all_users_data = {}

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_users_data, f, ensure_ascii=False, indent=4)
    except: pass

def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in all_users_data:
        all_users_data[user_id] = {"targets": {}, "lang": "en"}
        save_data()
    return all_users_data[user_id]

def update_user_data(user_id, data):
    all_users_data[str(user_id)] = data
    save_data()

load_data()

# --- TRANSLATOR ---
def translate_all(text):
    try:
        en = GoogleTranslator(source='auto', target='en').translate(text)
        de = GoogleTranslator(source='auto', target='de').translate(text)
        fa = GoogleTranslator(source='auto', target='fa').translate(text)
        return {"en": en, "de": de, "fa": fa}
    except: return {"en": text, "de": text, "fa": text}

# --- BOT LOGIC ---
GET_TITLE, GET_DATE = range(2)

def get_main_kb(user_id):
    url = f"{WEBAPP_URL_BASE}/webapp/{user_id}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 مشاهده در مینی‌اپ (WebApp)", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ افزودن"), KeyboardButton("🗑 حذف")],
        [KeyboardButton("🇩🇪 DE"), KeyboardButton("🇬🇧 EN"), KeyboardButton("🇮🇷 FA")]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user_data(user_id)
    await update.message.reply_text("👋 به ربات مدیریت زمان خوش آمدید!", reply_markup=get_main_kb(user_id))

async def handle_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    if "DE" in text: data['lang'] = 'de'
    elif "FA" in text: data['lang'] = 'fa'
    else: data['lang'] = 'en'
    update_user_data(user_id, data)
    await update.message.reply_text(f"Language: {data['lang']}", reply_markup=get_main_kb(user_id))

# --- ADD SCENARIO ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 نام رویداد؟ (هر زبانی)", reply_markup=ReplyKeyboardMarkup([["❌"]], resize_keyboard=True))
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌": return await cancel(update, context)
    await update.message.reply_text("🔄 ...")
    context.user_data['titles'] = translate_all(update.message.text)
    await update.message.reply_text("📅 تاریخ؟ (DD.MM.YYYY)")
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌": return await cancel(update, context)
    try:
        datetime.strptime(update.message.text, "%d.%m.%Y")
        user_id = update.effective_user.id
        data = get_user_data(user_id)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "date": update.message.text,
            "labels": context.user_data['titles'],
            "icon": "📌", "type": "personal"
        }
        update_user_data(user_id, data)
        await update.message.reply_text("✅ ذخیره شد!", reply_markup=get_main_kb(user_id))
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ فرمت اشتباه: DD.MM.YYYY")
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.", reply_markup=get_main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE SCENARIO (Simple) ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    if not data['targets']:
        return await update.message.reply_text("لیست خالی است.")
    
    kb = []
    for k, v in data['targets'].items():
        label = v['labels'].get(data['lang'], v['labels']['en'])
        kb.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"del_{k}")])
    await update.message.reply_text("حذف کدام؟", reply_markup=InlineKeyboardMarkup(kb))

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    key = query.data.replace("del_", "")
    if key in data['targets']:
        del data['targets'][key]
        update_user_data(user_id, data)
        await query.answer("حذف شد.")
        await query.delete_message()
    else:
        await query.answer("یافت نشد.")

def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add|Hinzufügen)"), add_start)],
        states={GET_TITLE: [MessageHandler(filters.TEXT, receive_title)], GET_DATE: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^(🇩🇪|🇮🇷|🇬🇧)"), handle_lang))
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    
    print("Running...")
    app.run_polling()

if __name__ == "__main__":
    main()