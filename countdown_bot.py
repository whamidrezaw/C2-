import logging
import threading
import json
import os
import google.generativeai as genai
from flask import Flask, render_template
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION (اطلاعات خود را اینجا وارد کنید) ---
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"
GEMINI_API_KEY = "AIzaSyAMNyRzBnssfBI5wKK8rsQJAIWrE1V_XdM" 
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"
DATA_FILE = "users_data.json"

# تنظیم جمینی
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- UI TEXTS ---
UI = {
    "en": { 
        "open": "📱 Open App", "add": "➕ Add Event", "del": "🗑 Delete", "mentor": "🧠 AI Mentor",
        "welcome": "👋 Welcome! Manage your time smartly.",
        "ask_name": "📝 Event Name:", "translating": "✨ Translating...",
        "ask_date": "📅 Date (DD.MM.YYYY):", "saved": "✅ Saved!",
        "error": "❌ Error!", "cancel": "❌ Cancel", "empty": "📭 List is empty.",
        "del_ask": "🗑 Delete which one?", "deleted": "✅ Deleted.", "not_found": "❌ Not found.",
        "mentor_thinking": "🧠 Thinking & Analyzing your schedule...",
        "remind_msg": "🔔 <b>Reminder!</b>\n📌 Event: <b>{title}</b>\n⏳ Time left: <b>{days} days</b>"
    },
    "de": {
        "open": "📱 App öffnen", "add": "➕ Hinzufügen", "del": "🗑 Löschen", "mentor": "🧠 KI-Mentor",
        "welcome": "👋 Willkommen!", "ask_name": "📝 Ereignisname:", 
        "translating": "✨ Übersetzung...", "ask_date": "📅 Datum (TT.MM.JJJJ):",
        "saved": "✅ Gespeichert!", "error": "❌ Fehler!", "cancel": "❌ Abbrechen",
        "empty": "📭 Leer.", "del_ask": "🗑 Löschen:", "deleted": "✅ Gelöscht.", "not_found": "❌ Nicht gefunden.",
        "mentor_thinking": "🧠 Analysiere deinen Zeitplan...",
        "remind_msg": "🔔 <b>Erinnerung!</b>\n📌 Ereignis: <b>{title}</b>\n⏳ Verbleibend: <b>{days} Tage</b>"
    },
    "fa": {
        "open": "📱 مشاهده برنامه", "add": "➕ افزودن", "del": "🗑 حذف", "mentor": "🧠 مشاور هوشمند",
        "welcome": "👋 خوش آمدید!", "ask_name": "📝 نام رویداد:", 
        "translating": "✨ در حال ترجمه...", "ask_date": "📅 تاریخ (DD.MM.YYYY):",
        "saved": "✅ ذخیره شد!", "error": "❌ خطا!", "cancel": "❌ انصراف",
        "empty": "📭 لیست خالی است.", "del_ask": "🗑 انتخاب برای حذف:", "deleted": "✅ حذف شد.", "not_found": "❌ پیدا نشد.",
        "mentor_thinking": "🧠 در حال تحلیل وضعیت زمانی شما...",
        "remind_msg": "🔔 <b>یادآوری مهم!</b>\n📌 رویداد: <b>{title}</b>\n⏳ باقی‌مانده: <b>{days} روز</b>"
    },
    "ar": {
        "open": "📱 فتح التطبيق", "add": "➕ إضافة", "del": "🗑 حذف", "mentor": "🧠 المستشار الذكي",
        "welcome": "👋 أهلاً بك!", "ask_name": "📝 اسم الحدث:", 
        "translating": "✨ ترجمة...", "ask_date": "📅 التاريخ (DD.MM.YYYY):",
        "saved": "✅ تم الحفظ!", "error": "❌ خطأ!", "cancel": "❌ إلغاء",
        "empty": "📭 فارغ.", "del_ask": "🗑 حذف:", "deleted": "✅ تم الحذف.", "not_found": "❌ غير موجود.",
        "mentor_thinking": "🧠 جاري تحليل جدولك...",
        "remind_msg": "🔔 <b>تذكير!</b>\n📌 الحدث: <b>{title}</b>\n⏳ متبقي: <b>{days} أيام</b>"
    },
    "tr": {
        "open": "📱 Uygulama", "add": "➕ Ekle", "del": "🗑 Sil", "mentor": "🧠 AI Mentor",
        "welcome": "👋 Hoş geldiniz!", "ask_name": "📝 Etkinlik adı:", 
        "translating": "✨ Çeviriliyor...", "ask_date": "📅 Tarih (GG.AA.YYYY):",
        "saved": "✅ Kaydedildi!", "error": "❌ Hata!", "cancel": "❌ İptal",
        "empty": "📭 Boş.", "del_ask": "🗑 Sil:", "deleted": "✅ Silindi.", "not_found": "❌ Bulunamadı.",
        "mentor_thinking": "🧠 Programınız analiz ediliyor...",
        "remind_msg": "🔔 <b>Hatırlatma!</b>\n📌 Etkinlik: <b>{title}</b>\n⏳ Kalan: <b>{days} gün</b>"
    }
}

# --- SERVER ---
@app.route('/')
def home(): return "Bot Alive (Mentor + Reminder)"

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

def translate_with_ai(text):
    try:
        prompt = f"""Translate '{text}' to English, German, Persian, Arabic, Turkish. Return JSON keys: en, de, fa, ar, tr."""
        response = model.generate_content(prompt)
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except: return {"en": text, "de": text, "fa": text, "ar": text, "tr": text}

# --- KEYBOARD ---
def get_kb(uid, lang):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    t_mentor = get_text(lang, "mentor")
    return ReplyKeyboardMarkup([
        [KeyboardButton(get_text(lang, "open"), web_app=WebAppInfo(url=url))],
        [KeyboardButton(t_mentor)], # دکمه جدید مشاور
        [KeyboardButton(get_text(lang, "add")), KeyboardButton(get_text(lang, "del"))]
    ], resize_keyboard=True)

# --- AI MENTOR LOGIC ---
async def mentor_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code
    data = get_user_data(user.id)
    targets = data.get('targets', {})

    if not targets:
        return await update.message.reply_text(get_text(lang, "empty"))

    await update.message.reply_text(get_text(lang, "mentor_thinking"))

    # آماده‌سازی داده‌ها برای جمینی
    events_list = ""
    for k, v in targets.items():
        # محاسبه روز باقیمانده
        try:
            dt = datetime.strptime(v['date'], "%d.%m.%Y")
            days_left = (dt - datetime.now()).days
            label = v['labels'].get(lang, v['labels']['en'])
            events_list += f"- Event: {label} | Date: {v['date']} | Days left: {days_left}\n"
        except: continue

    # پرامپت هوشمند
    prompt = f"""
    Act as a strict but supportive Time Management Mentor.
    User Language: {lang} (Reply ONLY in this language).
    Current Date: {datetime.now().strftime("%Y-%m-%d")}
    
    User's Events:
    {events_list}
    
    Analyze the schedule. 
    1. If there are urgent deadlines (less than 30 days), give a warning and study/work strategy.
    2. If events are far, give advice on consistency.
    3. Use emojis. Be concise (max 4 sentences).
    """

    try:
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Mentor Error: {e}")
        await update.message.reply_text("⚠️ AI is busy. Try again later.")

# --- BACKGROUND REMINDER JOB ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """هر ساعت اجرا می‌شود و چک می‌کند"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # کپی برای جلوگیری از ارور تغییر دیکشنری در حین حلقه
    all_data_copy = DATA.copy()

    for user_id, user_data in all_data_copy.items():
        targets = user_data.get('targets', {})
        lang = user_data.get('lang', 'en') # اگر زبان ذخیره نشده بود، انگلیسی
        # سعی می‌کنیم زبان را از آخرین تعامل بفهمیم، اگر نه پیش‌فرض انگلیسی
        
        modified = False
        for key, item in targets.items():
            try:
                target_date = datetime.strptime(item['date'], "%d.%m.%Y")
                days_left = (target_date - datetime.now()).days + 1
                
                # زمان‌های هشدار: 30، 7، 3، 1 روز
                if days_left in [30, 7, 3, 1]:
                    # چک کنیم امروز یادآوری شده یا نه
                    last_reminded = item.get('last_reminded', "")
                    
                    if last_reminded != today_str:
                        # ارسال پیام
                        title = item['labels'].get(lang, item['labels']['en'])
                        msg = get_text(lang, "remind_msg").format(title=title, days=days_left)
                        
                        try:
                            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode='HTML')
                            # بروزرسانی تاریخ یادآوری
                            item['last_reminded'] = today_str
                            modified = True
                        except Exception as e:
                            logger.error(f"Failed to send reminder to {user_id}: {e}")
            except: continue
        
        if modified:
            update_user_data(user_id, user_data)

# --- STANDARD HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # ذخیره زبان کاربر برای استفاده در جاب‌ها
    data = get_user_data(user.id)
    data['lang'] = user.language_code
    update_user_data(user.id, data)
    
    await update.message.reply_text(get_text(user.language_code, "welcome"), reply_markup=get_kb(user.id, user.language_code))

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    await update.message.reply_text(get_text(lang, "ask_name"), reply_markup=ReplyKeyboardMarkup([[get_text(lang, "cancel")]], resize_keyboard=True))
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    if "❌" in update.message.text: return await cancel(update, context)
    await update.message.reply_text(get_text(lang, "translating"))
    context.user_data['titles'] = translate_with_ai(update.message.text)
    await update.message.reply_text(get_text(lang, "ask_date"))
    return 2

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
            "icon": "📌", "type": "personal",
            "last_reminded": "" # برای یادآوری
        }
        update_user_data(uid, data)
        await update.message.reply_text(get_text(lang, "saved"), reply_markup=get_kb(uid, lang))
        return ConversationHandler.END
    except:
        await update.message.reply_text(get_text(lang, "error"))
        return 2

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = update.effective_user.language_code
    await update.message.reply_text(get_text(lang, "canceled"), reply_markup=get_kb(update.effective_user.id, lang))
    return ConversationHandler.END

async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = update.effective_user.language_code
    data = get_user_data(uid)
    if not data['targets']: return await update.message.reply_text(get_text(lang, "empty"))
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
    
    # تعریف JobQueue برای یادآوری‌ها
    job_queue = app.job_queue
    # اجرای چک کردن یادآوری‌ها هر 3600 ثانیه (۱ ساعت)
    job_queue.run_repeating(check_reminders, interval=3600, first=10)

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^🗑"), delete_trigger))
    # هندلر دکمه مشاور (فقط با ایموجی مغز تشخیص میدهد)
    app.add_handler(MessageHandler(filters.Regex("^🧠"), mentor_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    
    print("Bot Running with Mentor & Reminders...")
    app.run_polling()

if __name__ == "__main__":
    main()