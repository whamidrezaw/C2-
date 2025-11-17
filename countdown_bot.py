cat <<EOF > countdown_bot.py
import logging
import threading
import random
import jdatetime
import pytz
import json
import os
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# ==========================================
# بخش ۱: سرور
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive with Buttons!"

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
DATA_FILE = "events.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TZ_GERMANY = pytz.timezone('Europe/Berlin')
TZ_IRAN = pytz.timezone('Asia/Tehran')

GET_TITLE, GET_DATE = range(2)

QUOTES = [
    ("Zeit ist das wertvollste Gut, das wir besitzen.", "زمان باارزش‌ترین دارایی است که ما داریم."),
    ("Der beste Weg, die Zukunft vorherzusagen, ist, sie zu gestalten.", "بهترین راه پیش‌بینی آینده، ساختن آن است."),
    ("Auch der längste Weg beginnt mit dem ersten Schritt.", "طولانی‌ترین مسیرها هم با اولین قدم آغاز می‌شوند."),
    ("Disziplin bedeutet, das zu tun, was getan werden muss.", "نظم یعنی انجام کاری که باید انجام شود."),
    ("Das Gestern ist Geschichte, das Morgen ein Rätsel, das Heute ein Geschenk.", "دیروز تاریخ است، فردا راز است، امروز یک هدیه است."),
    ("Träume groß, aber beginne klein.", "بزرگ رویاپردازی کن، اما کوچک شروع کن."),
    ("Warte nicht auf den perfekten Moment, nimm den Moment und mach ihn perfekt.", "منتظر لحظه عالی نباش، لحظه را دریاب و عالی‌اش کن."),
    ("Wer kämpft, kann verlieren. Wer nicht kämpft, hat schon verloren.", "کسی که می‌جنگد ممکن است ببازد، اما کسی که نمی‌جنگد از قبل باخته است."),
    ("Geduld ist bitter, aber ihre Frucht ist süß.", "صبر تلخ است، اما میوه‌اش شیرین است."),
    ("Fokussiere dich auf die Zukunft, denn dort wirst du den Rest deines Lebens verbringen.", "روی آینده تمرکز کن، چون بقیه عمرت را آنجا سپری خواهی کرد.")
]

DE_MONTHS = {1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni", 7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"}

DEFAULT_TARGETS = {
    "residence": {"date": "22.09.2026", "de_label": "Ablauf Aufenthaltstitel", "fa_label": "پایان کارت اقامت", "icon": "🔴", "type": "official"},
    "iran_entry": {"date": "18.12.2026", "de_label": "Geplante Einreise (Iran)", "fa_label": "ورود احتمالی به ایران", "icon": "🟡", "type": "official"},
    "passport": {"date": "11.01.2028", "de_label": "Ablauf Reisepass", "fa_label": "پایان اعتبار پاسپورت", "icon": "🟢", "type": "official"},
    "nowruz_05": {"date": "21.03.2026", "de_label": "Nouruz-Fest 1405", "fa_label": "عید نوروز ۱۴۰۵", "icon": "🔹", "type": "event"},
    "nowruz_06": {"date": "21.03.2027", "de_label": "Nouruz-Fest 1406", "fa_label": "عید نوروز ۱۴۰۶", "icon": "🔹", "type": "event"},
}

current_targets = {}

# ==========================================
# بخش ۳: مدیریت داده
# ==========================================

def load_data():
    global current_targets
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                current_targets = json.load(f)
        except Exception:
            current_targets = DEFAULT_TARGETS.copy()
    else:
        current_targets = DEFAULT_TARGETS.copy()

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_targets, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving: {e}")

load_data()

# ==========================================
# بخش ۴: توابع نمایش و کیبورد اصلی
# ==========================================

def format_duration(delta, lang="de"):
    parts = []
    if lang == "de":
        if delta.years > 0: parts.append(f"{delta.years} J")
        if delta.months > 0: parts.append(f"{delta.months} M")
        if delta.days > 0: parts.append(f"{delta.days} T")
        return ", ".join(parts) if parts else "Heute!"
    else:
        if delta.years > 0: parts.append(f"{delta.years} سال")
        if delta.months > 0: parts.append(f"{delta.months} ماه")
        if delta.days > 0: parts.append(f"{delta.days} روز")
        return " و ".join(parts) if parts else "همین امروز!"

def get_german_view():
    now = datetime.now(TZ_GERMANY)
    date_str = f"{now.day}. {DE_MONTHS[now.month]} {now.year}"
    time_str = now.strftime("%H:%M")
    quote = random.choice(QUOTES)[0]

    msg = f"📅 **Aktueller Status | {date_str}**\n"
    msg += f"⌚️ Uhrzeit: {time_str} (Deutschland)\n\n"
    
    officials = {k: v for k, v in current_targets.items() if v.get('type') == 'official'}
    events = {k: v for k, v in current_targets.items() if v.get('type') == 'event'}
    personal = {k: v for k, v in current_targets.items() if v.get('type') == 'personal'}

    if officials:
        msg += "╭ 🚧 **Behörden & Aufenthalt**\n│\n"
        for key, item in officials.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None)
            delta = relativedelta(t_date, now_naive)
            msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 {item['date']} | ⏳ {format_duration(delta, 'de')}\n│\n"
        msg += "╰\n\n"

    if personal:
        msg += "╭ 📌 **Persönliche Termine**\n│\n"
        for key, item in personal.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None)
            delta = relativedelta(t_date, now_naive)
            msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 {item['date']} | ⏳ {format_duration(delta, 'de')}\n│\n"
        msg += "╰\n\n"

    if events:
        msg += "╭ 🎉 **Kommende Ereignisse**\n│\n"
        for key, item in events.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None)
            delta = relativedelta(t_date, now_naive)
            msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 {item['date']} | ⏳ {format_duration(delta, 'de')}\n│\n"
        msg += "╰\n\n"
    
    msg += f"💡 *\"{quote}\"*"
    return msg

def get_persian_view():
    now_iran = datetime.now(TZ_IRAN)
    j_date = jdatetime.datetime.fromgregorian(datetime=now_iran)
    jdatetime.set_locale('fa_IR')
    date_str = j_date.strftime("%d %B %Y")
    time_str = now_iran.strftime("%H:%M")
    quote = random.choice(QUOTES)[1]

    msg = f"\u200f📅 **وضعیت زمانی شما | {date_str}**\n"
    msg += f"\u200f⌚️ ساعت: {time_str} (ایران)\n\n"
    
    officials = {k: v for k, v in current_targets.items() if v.get('type') == 'official'}
    events = {k: v for k, v in current_targets.items() if v.get('type') == 'event'}
    personal = {k: v for k, v in current_targets.items() if v.get('type') == 'personal'}

    if officials:
        msg += "\u200f🚧 **پرونده‌های اداری و مهاجرتی**\n"
        msg += "➖➖➖➖➖➖➖➖➖➖\n"
        for key, item in officials.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y")
            delta = relativedelta(t_date, datetime.now())
            msg += f"\u200f{item['icon']} **{item['fa_label']}**\n"
            msg += f"\u200f   📅 {item['date']} | ⏳ {format_duration(delta, 'fa')}\n\n"
    
    if personal:
        msg += "\u200f📌 **برنامه‌های شخصی شما**\n"
        msg += "➖➖➖➖➖➖➖➖➖➖\n"
        for key, item in personal.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y")
            delta = relativedelta(t_date, datetime.now())
            msg += f"\u200f{item['icon']} **{item['fa_label']}**\n"
            msg += f"\u200f   📅 {item['date']} | ⏳ {format_duration(delta, 'fa')}\n\n"

    if events:
        msg += "\u200f🎉 **مناسبت‌های پیش‌رو**\n"
        msg += "➖➖➖➖➖➖➖➖➖➖\n"
        for key, item in events.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y")
            delta = relativedelta(t_date, datetime.now())
            msg += f"\u200f{item['icon']} **{item['fa_label']}**\n"
            msg += f"\u200f   📅 {item['date']} | ⏳ {format_duration(delta, 'fa')}\n\n"
    
    msg += f"\u200f💡 *\"{quote}\"*"
    return msg

def get_main_menu_keyboard():
    keyboard = [
        ["🇩🇪 Deutsch (آلمان)", "🇮🇷 فارسی (ایران)"],
        ["➕ افزودن رویداد", "🗑 حذف رویداد"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==========================================
# بخش ۵: افزودن رویداد
# ==========================================

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 **عنوان رویداد** را بنویسید:\n\n(اگر منصرف شدید دکمه 'انصراف' یا دستور /cancel را بزنید)", 
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True)
    )
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "❌ انصراف":
        await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
        
    context.user_data['new_event_title'] = text
    await update.message.reply_text(
        "📅 **تاریخ** را وارد کنید (`DD.MM.YYYY`):\nمثال: `10.12.2025`", 
        parse_mode='Markdown'
    )
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "❌ انصراف":
        await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    try:
        datetime.strptime(text, "%d.%m.%Y")
        title = context.user_data['new_event_title']
        new_id = f"custom_{int(datetime.now().timestamp())}"
        
        current_targets[new_id] = {
            "date": text, "de_label": title, "fa_label": title,
            "icon": "📌", "type": "personal"
        }
        save_data()
        await update.message.reply_text(
            f"✅ رویداد **{title}** اضافه شد.", 
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ فرمت اشتباه. دوباره تلاش کنید:\n`10.12.2025`", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

# ==========================================
# بخش ۶: حذف رویداد
# ==========================================

async def delete_menu_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []
    for key, item in current_targets.items():
        btn_text = f"🗑 {item['fa_label']} ({item['date']})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بستن منو", callback_data="close_delete")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("🗑 **کدام رویداد حذف شود؟**", reply_markup=reply_markup, parse_mode='Markdown')

async def delete_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    
    if data.startswith("del_"):
        key_to_delete = data.replace("del_", "")
        if key_to_delete in current_targets:
            deleted_item = current_targets.pop(key_to_delete)
            save_data()
            await query.answer(f"حذف شد: {deleted_item['fa_label']}")
            
            keyboard = []
            for key, item in current_targets.items():
                btn_text = f"🗑 {item['fa_label']} ({item['date']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{key}")])
            keyboard.append([InlineKeyboardButton("🔙 بستن منو", callback_data="close_delete")])
            
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.answer("این آیتم قبلاً حذف شده است.")
            
    elif data == "close_delete":
        await query.answer()
        await query.edit_message_text("✅ منوی حذف بسته شد.")

# ==========================================
# بخش ۷: هندلر اصلی
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "سلام! 👋\nبه ربات مدیریت زمان خوش آمدید.\nاز منوی پایین استفاده کنید:",
        reply_markup=get_main_menu_keyboard()
    )

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    if "Deutsch" in text:
        await update.message.reply_text(get_german_view(), parse_mode='Markdown')
        
    elif "فارسی" in text:
        await update.message.reply_text(get_persian_view(), parse_mode='Markdown')

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن رویداد"), add_start)],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ انصراف$"), cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^🗑 حذف رویداد"), delete_menu_trigger))
    application.add_handler(MessageHandler(filters.Regex("^(🇩🇪|🇮🇷)"), handle_main_menu_buttons))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(delete_callback_handler))
    
    print("Bot started with Buttons...")
    application.run_polling()

if __name__ == "__main__":
    main()
EOF