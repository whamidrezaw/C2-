import logging
import threading
import random
import jdatetime
import pytz
import json
import os
import copy
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

# ==========================================
# بخش ۱: سرور زنده نگه دارنده
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive (Trilingual Mode)!"

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# ==========================================
# بخش ۲: تنظیمات و داده‌ها
# ==========================================
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"
DATA_FILE = "users_data.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# تعریف مناطق زمانی
TZ_MAPPING = {
    "fa": pytz.timezone('Asia/Tehran'),
    "de": pytz.timezone('Europe/Berlin'),
    "en": pytz.timezone('America/New_York') # پیش‌فرض انگلیسی
}

GET_TITLE, GET_DATE = range(2)

# ۳۰ جمله انگیزشی به ۳ زبان
QUOTES = [
    {"de": "Zeit ist das wertvollste Gut.", "fa": "زمان باارزش‌ترین دارایی است.", "en": "Time is the most valuable asset."},
    {"de": "Der beste Weg, die Zukunft vorherzusagen, ist, sie zu gestalten.", "fa": "بهترین راه پیش‌بینی آینده، ساختن آن است.", "en": "The best way to predict the future is to create it."},
    {"de": "Auch der längste Weg beginnt mit dem ersten Schritt.", "fa": "طولانی‌ترین مسیرها هم با اولین قدم آغاز می‌شوند.", "en": "Even the longest journey begins with a single step."},
    {"de": "Disziplin bedeutet, das zu tun, was getan werden muss.", "fa": "نظم یعنی انجام کاری که باید انجام شود.", "en": "Discipline means doing what needs to be done."},
    {"de": "Das Gestern ist Geschichte, das Morgen ein Rätsel.", "fa": "دیروز تاریخ است، فردا راز است.", "en": "Yesterday is history, tomorrow is a mystery."},
    {"de": "Träume groß, aber beginne klein.", "fa": "بزرگ رویاپردازی کن، اما کوچک شروع کن.", "en": "Dream big, but start small."},
    {"de": "Mach den Moment perfekt.", "fa": "لحظه را دریاب و عالی‌اش کن.", "en": "Make the moment perfect."},
    {"de": "Wer nicht kämpft, hat schon verloren.", "fa": "کسی که نمی‌جنگد از قبل باخته است.", "en": "He who does not fight has already lost."},
    {"de": "Geduld ist bitter, aber ihre Frucht ist süß.", "fa": "صبر تلخ است، اما میوه‌اش شیرین است.", "en": "Patience is bitter, but its fruit is sweet."},
    {"de": "Fokussiere dich auf die Zukunft.", "fa": "روی آینده تمرکز کن.", "en": "Focus on the future."},
    {"de": "Erfolg ist eine Treppe, keine Tür.", "fa": "موفقیت یک پله است، نه یک در.", "en": "Success is a staircase, not a door."},
    {"de": "Niemals aufgeben.", "fa": "هرگز تسلیم نشو.", "en": "Never give up."},
    {"de": "Sei stärker als deine Ausreden.", "fa": "از بهانه‌هایت قوی‌تر باش.", "en": "Be stronger than your excuses."},
    {"de": "Alles ist schwer, bevor es leicht wird.", "fa": "همه چیز سخت است قبل از اینکه آسان شود.", "en": "Everything is hard before it is easy."},
    {"de": "Glaube an dich selbst.", "fa": "به خودت ایمان داشته باش.", "en": "Believe in yourself."},
    {"de": "Jeder Tag ist eine neue Chance.", "fa": "هر روز یک شانس دوباره است.", "en": "Every day is a fresh start."},
    {"de": "Fokus ist der Schlüssel.", "fa": "تمرکز کلید موفقیت است.", "en": "Focus is the key."},
    {"de": "Schmerz ist vorübergehend.", "fa": "درد موقتی است.", "en": "Pain is temporary."},
    {"de": "Du bist der Autor deines Lebens.", "fa": "تو نویسنده زندگی خودت هستی.", "en": "You are the author of your life."},
    {"de": "Mut steht am Anfang des Handelns.", "fa": "شجاعت آغازگر عمل است.", "en": "Courage is at the start of action."},
    {"de": "Kleine Schritte führen zum Ziel.", "fa": "قدم‌های کوچک به هدف می‌رسند.", "en": "Small steps lead to the goal."},
    {"de": "Wissen ist Macht.", "fa": "دانایی توانایی است.", "en": "Knowledge is power."},
    {"de": "Zeit wartet auf niemanden.", "fa": "زمان منتظر هیچکس نمی‌ماند.", "en": "Time waits for no one."},
    {"de": "Verändere deine Gedanken.", "fa": "افکارت را تغییر بده.", "en": "Change your thoughts."},
    {"de": "Lerne aus Fehlern.", "fa": "از اشتباهات درس بگیر.", "en": "Learn from mistakes."},
    {"de": "Sei die Veränderung.", "fa": "تو همان تغییری باش.", "en": "Be the change."},
    {"de": "Handeln statt Reden.", "fa": "عمل کردن به جای حرف زدن.", "en": "Action over words."},
    {"de": "Dein Potenzial ist unbegrenzt.", "fa": "پتانسیل تو نامحدود است.", "en": "Your potential is limitless."},
    {"de": "Bleib hungrig, bleib töricht.", "fa": "مشتاق باش، دیوانه‌وار دنبال کن.", "en": "Stay hungry, stay foolish."},
    {"de": "Das Leben passiert jetzt.", "fa": "زندگی همین الان در جریان است.", "en": "Life is happening now."}
]

# دیکشنری متون رابط کاربری (UI)
TEXTS = {
    "fa": {
        "welcome": "👋 سلام! به ربات مدیریت زمان خوش آمدید.\nلطفاً زبان خود را انتخاب کنید:",
        "dashboard_title": "📅 **وضعیت زمانی شما**",
        "time_label": "⌚️ ساعت",
        "official_sec": "🚧 **رویدادهای مهم**",
        "personal_sec": "📌 **برنامه‌های شخصی**",
        "events_sec": "🎉 **مناسبت‌ها**",
        "empty_list": "📭 لیست شما خالی است. با دکمه 'افزودن' شروع کنید.",
        "add_btn": "➕ افزودن رویداد",
        "del_btn": "🗑 حذف رویداد",
        "lang_btn": "🌐 تغییر زبان",
        "add_prompt": "📝 **عنوان رویداد** را به هر زبانی بنویسید (من ترجمه می‌کنم):\n\n(انصراف: /cancel)",
        "translating": "🔄 در حال ترجمه و آماده‌سازی...",
        "title_received": "✅ عنوان ثبت شد:\n🇺🇸: {en}\n🇩🇪: {de}\n🇮🇷: {fa}\n\n📅 حالا **تاریخ میلادی** را وارد کنید (`DD.MM.YYYY`):",
        "date_error": "❌ فرمت اشتباه! لطفاً میلادی وارد کنید: `10.12.2025`",
        "success_add": "✅ رویداد با موفقیت اضافه شد!",
        "cancel": "❌ عملیات لغو شد.",
        "del_prompt": "🗑 **کدام مورد حذف شود؟**",
        "del_success": "✅ حذف شد: {item}",
        "del_close": "🔙 بستن منو",
        "menu_closed": "✅ منو بسته شد.",
        "item_not_found": "❌ آیتم یافت نشد.",
        "year": "سال", "month": "ماه", "day": "روز", "days_total": "روز"
    },
    "de": {
        "welcome": "👋 Hallo! Willkommen beim Zeitmanagement-Bot.\nBitte wähle deine Sprache:",
        "dashboard_title": "📅 **Dein Zeitstatus**",
        "time_label": "⌚️ Uhrzeit",
        "official_sec": "🚧 **Wichtige Ereignisse**",
        "personal_sec": "📌 **Persönliche Termine**",
        "events_sec": "🎉 **Anlässe**",
        "empty_list": "📭 Deine Liste ist leer. Nutze 'Hinzufügen'.",
        "add_btn": "➕ Hinzufügen",
        "del_btn": "🗑 Löschen",
        "lang_btn": "🌐 Sprache ändern",
        "add_prompt": "📝 **Titel eingeben** (in jeder Sprache):\n\n(Abbrechen: /cancel)",
        "translating": "🔄 Übersetzung läuft...",
        "title_received": "✅ Titel gespeichert:\n🇺🇸: {en}\n🇩🇪: {de}\n🇮🇷: {fa}\n\n📅 Jetzt **Datum** eingeben (`DD.MM.YYYY`):",
        "date_error": "❌ Falsches Format! Bitte so eingeben: `10.12.2025`",
        "success_add": "✅ Ereignis erfolgreich hinzugefügt!",
        "cancel": "❌ Abgebrochen.",
        "del_prompt": "🗑 **Was soll gelöscht werden?**",
        "del_success": "✅ Gelöscht: {item}",
        "del_close": "🔙 Schließen",
        "menu_closed": "✅ Menü geschlossen.",
        "item_not_found": "❌ Element nicht gefunden.",
        "year": "Jahr", "month": "Monat", "day": "Tag", "days_total": "Tage"
    },
    "en": {
        "welcome": "👋 Hello! Welcome to Time Manager Bot.\nPlease select your language:",
        "dashboard_title": "📅 **Your Time Status**",
        "time_label": "⌚️ Time",
        "official_sec": "🚧 **Key Events**",
        "personal_sec": "📌 **Personal Plans**",
        "events_sec": "🎉 **Occasions**",
        "empty_list": "📭 Your list is empty. Start by 'Add Event'.",
        "add_btn": "➕ Add Event",
        "del_btn": "🗑 Delete Event",
        "lang_btn": "🌐 Change Language",
        "add_prompt": "📝 Enter **Event Title** (any language):\n\n(Cancel: /cancel)",
        "translating": "🔄 Translating...",
        "title_received": "✅ Title saved:\n🇺🇸: {en}\n🇩🇪: {de}\n🇮🇷: {fa}\n\n📅 Now enter **Date** (`DD.MM.YYYY`):",
        "date_error": "❌ Wrong format! Please use: `10.12.2025`",
        "success_add": "✅ Event added successfully!",
        "cancel": "❌ Operation cancelled.",
        "del_prompt": "🗑 **Select item to delete:**",
        "del_success": "✅ Deleted: {item}",
        "del_close": "🔙 Close",
        "menu_closed": "✅ Menu closed.",
        "item_not_found": "❌ Item not found.",
        "year": "Year", "month": "Month", "day": "Day", "days_total": "Days"
    }
}

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
    except Exception as e:
        logger.error(f"Error saving: {e}")

def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in all_users_data:
        # Default language English, Empty targets
        all_users_data[user_id] = {"targets": {}, "lang": "en"}
        save_data()
    return all_users_data[user_id]

def update_user_data(user_id, data):
    user_id = str(user_id)
    all_users_data[user_id] = data
    save_data()

load_data()

# ==========================================
# بخش ۴: منطق ترجمه و تاریخ
# ==========================================

def translate_all(text):
    try:
        en = GoogleTranslator(source='auto', target='en').translate(text)
        de = GoogleTranslator(source='auto', target='de').translate(text)
        fa = GoogleTranslator(source='auto', target='fa').translate(text)
        return {"en": en, "de": de, "fa": fa}
    except:
        return {"en": text, "de": text, "fa": text}

def get_display_date(date_str, lang):
    """تبدیل تاریخ برای نمایش"""
    if lang == 'fa':
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        j_date = jdatetime.date.fromgregorian(date=dt.date())
        jdatetime.set_locale('fa_IR')
        return j_date.strftime("%d %B %Y")
    return date_str

def format_full_duration(delta, lang):
    """محاسبه دقیق + روز کل"""
    # محاسبه روز کل
    total_days = 0
    # تخمین تقریبی یا استفاده از ورودی، اینجا دلتا فقط اختلاف را دارد.
    # برای محاسبه دقیق روز کل باید تاریخ مبدا و مقصد را داشته باشیم که در تابع اصلی داریم.
    
    parts = []
    txt = TEXTS[lang]
    
    if delta.years > 0: parts.append(f"{delta.years} {txt['year']}")
    if delta.months > 0: parts.append(f"{delta.months} {txt['month']}")
    if delta.days > 0: parts.append(f"{delta.days} {txt['day']}")
    
    main_text = " / ".join(parts) if parts else ("0 " + txt['day'])
    return main_text

# ==========================================
# بخش ۵: تولید ویو (View Generation)
# ==========================================

def get_dashboard_view(user_id):
    data = get_user_data(user_id)
    targets = data.get("targets", {})
    lang = data.get("lang", "en")
    
    # انتخاب متن‌ها بر اساس زبان
    t = TEXTS[lang]
    
    # محاسبه ساعت بر اساس زبان (کشور)
    tz = TZ_MAPPING.get(lang, pytz.utc)
    now = datetime.now(tz)
    
    date_str = now.strftime("%d.%m.%Y")
    if lang == 'fa':
        j_now = jdatetime.datetime.fromgregorian(datetime=now)
        jdatetime.set_locale('fa_IR')
        date_str = j_now.strftime("%d %B %Y")
    
    time_str = now.strftime("%H:%M")
    
    # انتخاب جمله انگیزشی
    quote_obj = random.choice(QUOTES)
    quote = quote_obj.get(lang, quote_obj['en'])

    # ساخت پیام
    msg = f"{t['dashboard_title']} | {date_str}\n"
    msg += f"{t['time_label']}: {time_str}\n\n"
    
    if not targets:
        msg += t['empty_list'] + "\n\n"
    else:
        # مرتب سازی بر اساس نوع (اختیاری)
        for key, item in targets.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None) # حذف اطلاعات زمانی برای محاسبه اختلاف
            
            delta = relativedelta(t_date, now_naive)
            total_days = (t_date - now_naive).days + 1 # +1 برای احتیاط
            
            duration_str = format_full_duration(delta, lang)
            
            # لیبل رویداد به زبان کاربر
            label = item['labels'].get(lang, item['labels']['en'])
            display_date = get_display_date(item['date'], lang)
            days_word = t['days_total']
            
            msg += f"📌 **{label}**\n"
            msg += f"   📅 {display_date}\n"
            msg += f"   ⏳ {duration_str} ({total_days} {days_word})\n\n"
            
    msg += f"💡 *\"{quote}\"*"
    return msg

def get_keyboard(lang):
    t = TEXTS[lang]
    keyboard = [
        [t['add_btn'], t['del_btn']],
        [t['lang_btn']]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==========================================
# بخش ۶: هندلرها
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    get_user_data(user_id) # اطمینان از وجود کاربر
    
    # پیام خوش‌آمدگویی ۳ زبانه (فقط یک بار)
    welcome_msg = (
        "🇬🇧 Welcome! Please choose your language:\n"
        "🇩🇪 Willkommen! Bitte wähle deine Sprache:\n"
        "🇮🇷 خوش آمدید! لطفاً زبان خود را انتخاب کنید:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang_de")],
        [InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang_fa")]
    ]
    
    await update.message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    lang_code = data.split("_")[-1] # en, de, fa
    
    # ذخیره زبان
    user_data = get_user_data(user_id)
    user_data['lang'] = lang_code
    update_user_data(user_id, user_data)
    
    await query.answer()
    await query.delete_message() # حذف پیام انتخاب زبان برای تمیزی
    
    # نمایش داشبورد
    await context.bot.send_message(
        chat_id=user_id,
        text=get_dashboard_view(user_id),
        parse_mode='Markdown',
        reply_markup=get_keyboard(lang_code)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    lang = user_data['lang']
    t = TEXTS[lang]
    
    if text == t['lang_btn']:
        await start(update, context) # بازگشت به انتخاب زبان
    elif text == t['add_btn']:
        await add_start(update, context) # شروع سناریوی افزودن (باید هندل شود)
    elif text == t['del_btn']:
        await delete_menu_trigger(update, context)
    else:
        # رفرش صفحه (نمایش مجدد داشبورد)
        await update.message.reply_text(
            get_dashboard_view(user_id), 
            parse_mode='Markdown',
            reply_markup=get_keyboard(lang)
        )

# --- Conversation Add ---

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_data(user_id)['lang']
    t = TEXTS[lang]
    
    # دکمه انصراف موقت
    cancel_kb = ReplyKeyboardMarkup([[t['cancel'].split()[0]]], resize_keyboard=True) 
    
    await update.message.reply_text(t['add_prompt'], parse_mode='Markdown', reply_markup=cancel_kb)
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.effective_user.id
    lang = get_user_data(user_id)['lang']
    t = TEXTS[lang]
    
    # چک انصراف (ساده)
    if len(text) < 2 or text.startswith("/"): 
        await update.message.reply_text(t['cancel'], reply_markup=get_keyboard(lang))
        return ConversationHandler.END
    
    await update.message.reply_text(t['translating'])
    
    titles = translate_all(text)
    context.user_data['new_titles'] = titles
    
    msg = t['title_received'].format(en=titles['en'], de=titles['de'], fa=titles['fa'])
    await update.message.reply_text(msg, parse_mode='Markdown')
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.effective_user.id
    lang = get_user_data(user_id)['lang']
    t = TEXTS[lang]
    
    try:
        datetime.strptime(text, "%d.%m.%Y")
        
        user_data = get_user_data(user_id)
        titles = context.user_data['new_titles']
        
        new_id = f"evt_{int(datetime.now().timestamp())}"
        user_data['targets'][new_id] = {
            "date": text,
            "labels": titles, # ذخیره هر ۳ زبان
            "icon": "📌",
            "type": "personal"
        }
        update_user_data(user_id, user_data)
        
        await update.message.reply_text(
            t['success_add'], 
            parse_mode='Markdown',
            reply_markup=get_keyboard(lang)
        )
        # نمایش داشبورد جدید
        await update.message.reply_text(get_dashboard_view(user_id), parse_mode='Markdown')
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(t['date_error'], parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_data(user_id)['lang']
    await update.message.reply_text(TEXTS[lang]['cancel'], reply_markup=get_keyboard(lang))
    return ConversationHandler.END

# --- Delete ---

async def delete_menu_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    lang = data['lang']
    t = TEXTS[lang]
    
    targets = data['targets']
    if not targets:
        await update.message.reply_text(t['empty_list'])
        return

    keyboard = []
    for key, item in targets.items():
        label = item['labels'][lang]
        keyboard.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"del_{key}")])
    
    keyboard.append([InlineKeyboardButton(t['del_close'], callback_data="close_delete")])
    
    await update.message.reply_text(t['del_prompt'], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    data_in = query.data
    
    user_data = get_user_data(user_id)
    lang = user_data['lang']
    t = TEXTS[lang]
    
    if data_in.startswith("del_"):
        key = data_in.replace("del_", "")
        if key in user_data['targets']:
            item = user_data['targets'].pop(key)
            update_user_data(user_id, user_data)
            
            await query.answer(t['del_success'].format(item=item['labels'][lang]))
            await delete_menu_trigger(update, context) # رفرش منو
        else:
            await query.answer(t['item_not_found'])
            
    elif data_in == "close_delete":
        await query.answer()
        await query.delete_message()
        await context.bot.send_message(user_id, t['menu_closed'])

# ==========================================
# MAIN
# ==========================================

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation Add
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add|Hinzufügen)"), add_start)],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^(❌|Cancel|Abbrechen)"), cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^set_lang_"))
    application.add_handler(CallbackQueryHandler(delete_callback))
    application.add_handler(conv_handler)
    
    # هندل کردن دکمه‌های منو (حذف، تغییر زبان، رفرش)
    # چون متن دکمه‌ها متغیر است، همه متن‌ها را میگیریم و در تابع هندل میکنیم
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("Bot Started Trilingual...")
    application.run_polling()

if __name__ == "__main__":
    main()