import logging
import threading
import json
import os
from flask import Flask, render_template
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

app = Flask(__name__, template_folder='templates')

# --- CONFIG ---
# 1. توکن ربات را اینجا بگذارید:
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"

# 2. آدرس سایت رندر خود را اینجا بگذارید (با https):
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"

DATA_FILE = "users_data.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- UI TEXTS (5 Languages) ---
UI = {
    "en": { 
        "open": "📱 Open App", "add": "➕ Add Event", "del": "🗑 Delete",
        "welcome": "👋 Welcome! Manage your time smartly.",
        "ask_name": "📝 Enter event name (Auto-Translate):", "translating": "🔄 Translating...",
        "ask_date": "📅 Enter Date (DD.MM.YYYY):", "saved": "✅ Saved!",
        "error": "❌ Error! Use DD.MM.YYYY", "cancel": "❌ Cancel", "empty": "📭 Empty.",
        "del_ask": "🗑 Delete which one?", "deleted": "✅ Deleted.", "not_found": "❌ Not found."
    },
    "de": {
        "open": "📱 App öffnen", "add": "➕ Hinzufügen", "del": "🗑 Löschen",
        "welcome": "👋 Willkommen!", "ask_name": "📝 Ereignisname:", 
        "translating": "🔄 Übersetzung...", "ask_date": "📅 Datum (TT.MM.JJJJ):",
        "saved": "✅ Gespeichert!", "error": "❌ Fehler! TT.MM.JJJJ", "cancel": "❌ Abbrechen",
        "empty": "📭 Leer.", "del_ask": "🗑 Löschen:", "deleted": "✅ Gelöscht.", "not_found": "❌ Nicht gefunden."
    },
    "fa": {
        "open": "📱 مشاهده برنامه", "add": "➕ افزودن رویداد", "del": "🗑 حذف رویداد",
        "welcome": "👋 خوش آمدید!", "ask_name": "📝 نام رویداد (هر زبانی):", 
        "translating": "🔄 در حال ترجمه...", "ask_date": "📅 تاریخ (DD.MM.YYYY):",
        "saved": "✅ ذخیره شد!", "error": "❌ فرمت اشتباه!", "cancel": "❌ انصراف",
        "empty": "📭 خالی است.", "del_ask": "🗑 انتخاب برای حذف:", "deleted": "✅ حذف شد.", "not_found": "❌ پیدا نشد."
    },
    "ar": {
        "open": "📱 فتح التطبيق", "add": "➕ إضافة", "del": "🗑 حذف",
        "welcome": "👋 أهلاً بك!", "ask_name": "📝 اسم الحدث:", 
        "translating": "🔄 ترجمة...", "ask_date": "📅 التاريخ (DD.MM.YYYY):",
        "saved": "✅ تم الحفظ!", "error": "❌ خطأ!", "cancel": "❌ إلغاء",
        "empty": "📭 فارغ.", "del_ask": "🗑 اختر للحذف:", "deleted": "✅ تم الحذف.", "not_found": "❌ غير موجود."
    },
    "tr": {
        "open": "📱 Uygulama", "add": "➕ Ekle", "del": "🗑 Sil",
        "welcome": "👋 Hoş geldiniz!", "ask_name": "📝 Etkinlik adı:", 
        "translating": "🔄 Çeviriliyor...", "ask_date": "📅 Tarih (GG.AA.YYYY):",
        "saved": "✅ Kaydedildi!", "error": "❌ Hata!", "cancel": "❌ İptal",
        "empty": "📭 Boş.", "del_ask": "🗑 Seçin:", "deleted": "✅ Silindi.", "not_found": "❌ Bulunamadı."
    }
}

# --- SERVER ROUTES ---
@app.route('/')
def home(): return "Bot Alive"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    return render_template('index.html', user_data=data.get('targets', {}))

def run_web_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_web_server, daemon=True).start()

# --- DATA MANAGER ---
DATA = {}
def load_data():
    global DATA
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f: DATA = json.load(f)
        except: DATA = {}
def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(DATA, f, ensure_ascii=False, indent=4)
    except: pass

def get_user_data(uid):
    uid = str(uid)
    if uid not in DATA:
        DATA[uid] = {"targets": {}}
        save_data()
    return DATA[uid]

def update_user_data(uid, val):
    DATA[str(uid)] = val
    save_data()
load_data()

# --- HELPERS ---
def get_text(lang, key):
    return UI.get(lang, UI["en"]).get(key, UI["en"][key])

def translate_all(text):
    try:
        return {
            "en": GoogleTranslator(source='auto', target='en').translate(text),
            "de": GoogleTranslator(source='auto', target='de').translate(text),
            "fa": GoogleTranslator(source='auto', target='fa').translate(text),
            "ar": GoogleTranslator(source='auto', target='ar').translate(text),
            "tr": GoogleTranslator(source='auto', target='tr').translate(text)
        }
    except: return {"en": text, "de": text, "fa": text, "ar": text, "tr": text}

# --- KEYBOARD ---
def get_kb(uid, lang):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_text(lang, "open"), web_app=WebAppInfo(url=url))],
        [KeyboardButton(get_text(lang, "add")), KeyboardButton(get_text(lang, "del"))]
    ], resize_keyboard=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code
    get_user_data(user.id)
    await update.message.reply_text(get_text(lang, "welcome"), reply_markup=get_kb(user.id, lang))

# --- ADD ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    await update.message.reply_text(get_text(lang, "ask_name"), reply_markup=ReplyKeyboardMarkup([[get_text(lang, "cancel")]], resize_keyboard=True))
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    if "❌" in update.message.text: return await cancel(update, context)
    await update.message.reply_text(get_text(lang, "translating"))
    context.user_data['titles'] = translate_all(update.message.text)
    await update.message.reply_text(get_text(lang, "ask_date"))
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    uid = update.effective_user.id
    if "❌" in update.message.text: return await cancel(update, context)
    try:
        datetime.strptime(update.message.text, "%d.%m.%Y")
        data = get_user_data(uid)
        new_id = f"evt_{int(datetime.now().timestamp())}"
        data['targets'][new_id] = {
            "date": update.message.text,
            "labels": context.user_data['titles'],
            "icon": "📌", "type": "personal"
        }
        update_user_data(uid, data)
        await update.message.reply_text(get_text(lang, "saved"), reply_markup=get_kb(uid, lang))
        return ConversationHandler.END
    except:
        await update.message.reply_text(get_text(lang, "error"))
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    await update.message.reply_text(get_text(lang, "canceled"), reply_markup=get_kb(update.effective_user.id, lang))
    return ConversationHandler.END

# --- DELETE ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = update.effective_user.language_code
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text(get_text(lang, "empty"))
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = []
    for k, v in data['targets'].items():
        label = v['labels'].get(lang, v['labels']['en'])
        kb.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"del_{k}")])
    await update.message.reply_text(get_text(lang, "del_ask"), reply_markup=InlineKeyboardMarkup(kb))

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    lang = update.effective_user.language_code
    data = get_user_data(uid)
    key = query.data.replace("del_", "")
    if key in data['targets']:
        del data['targets'][key]
        update_user_data(uid, data)
        await query.answer(get_text(lang, "deleted"))
        await query.delete_message()
    else: await query.answer(get_text(lang, "not_found"))

def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕"), add_start)],
        states={GET_TITLE: [MessageHandler(filters.TEXT, receive_title)], GET_DATE: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^🗑"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    print("Bot Running Universal...")
    app.run_polling()

if __name__ == "__main__":
    main()