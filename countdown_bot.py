import logging
import threading
import random
import jdatetime
import pytz  # کتابخانه مدیریت مناطق زمانی
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# بخش ۱: سرور زنده نگه دارنده
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running with Timezones!"

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تنظیم مناطق زمانی دقیق
TZ_GERMANY = pytz.timezone('Europe/Berlin')
TZ_IRAN = pytz.timezone('Asia/Tehran')

# جملات انگیزشی
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

# داده‌های هدف
TARGETS = {
    "residence": {"date": "22.09.2026", "de_label": "Ablauf Aufenthaltstitel", "fa_label": "پایان کارت اقامت", "icon": "🔴"},
    "iran_entry": {"date": "18.12.2026", "de_label": "Geplante Einreise (Iran)", "fa_label": "ورود احتمالی به ایران", "icon": "🟡"},
    "passport": {"date": "11.01.2028", "de_label": "Ablauf Reisepass", "fa_label": "پایان اعتبار پاسپورت", "icon": "🟢"},
    "nowruz_05": {"date": "21.03.2026", "de_label": "Nouruz-Fest 1405", "fa_label": "عید نوروز ۱۴۰۵", "icon": "🔹"},
    "nowruz_06": {"date": "21.03.2027", "de_label": "Nouruz-Fest 1406", "fa_label": "عید نوروز ۱۴۰۶", "icon": "🔹"},
}

# ==========================================
# بخش ۳: توابع تولید پیام
# ==========================================

def format_duration(delta, lang="de"):
    parts = []
    if lang == "de":
        if delta.years > 0: parts.append(f"{delta.years} Jahr{'e' if delta.years > 1 else ''}")
        if delta.months > 0: parts.append(f"{delta.months} Monat{'e' if delta.months > 1 else ''}")
        if delta.days > 0: parts.append(f"{delta.days} Tag{'e' if delta.days > 1 else ''}")
        return ", ".join(parts) if parts else "Heute!"
    else:
        if delta.years > 0: parts.append(f"{delta.years} سال")
        if delta.months > 0: parts.append(f"{delta.months} ماه")
        if delta.days > 0: parts.append(f"{delta.days} روز")
        return " و ".join(parts) if parts else "همین امروز!"

def get_german_view():
    """تولید پیام آلمانی با ساعت آلمان"""
    # ساعت دقیق برلین
    now = datetime.now(TZ_GERMANY)
    date_str = f"{now.day}. {DE_MONTHS[now.month]} {now.year}"
    time_str = now.strftime("%H:%M")
    
    quote = random.choice(QUOTES)[0] # جمله آلمانی

    msg = f"📅 **Aktueller Status | {date_str}**\n"
    msg += f"⌚️ Uhrzeit: {time_str} (Deutschland)\n\n"
    
    msg += "╭ 🚧 **Behörden & Aufenthalt**\n│\n"
    for key in ["residence", "iran_entry", "passport"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None) # حذف تایم‌زون برای محاسبه ساده
        now_naive = now.replace(tzinfo=None)
        delta = relativedelta(t_date, now_naive)
        msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 Frist: {item['date']}\n│ └ ⏳ Restzeit: {format_duration(delta, 'de')}\n│\n"
    msg += "╰\n\n"

    msg += "╭ 🎉 **Kommende Ereignisse**\n│\n"
    for key in ["nowruz_05", "nowruz_06"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
        now_naive = now.replace(tzinfo=None)
        delta = relativedelta(t_date, now_naive)
        msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 Datum: {item['date']}\n│ └ ⏳ Restzeit: {format_duration(delta, 'de')}\n│\n"
    msg += "╰\n\n"
    
    msg += f"💡 *\"{quote}\"*"
    return msg

def get_persian_view():
    """تولید پیام فارسی با ساعت ایران"""
    # ساعت دقیق تهران
    now_iran = datetime.now(TZ_IRAN)
    
    # تبدیل به شمسی
    j_date = jdatetime.datetime.fromgregorian(datetime=now_iran)
    jdatetime.set_locale('fa_IR')
    date_str = j_date.strftime("%d %B %Y")
    time_str = now_iran.strftime("%H:%M")
    
    quote = random.choice(QUOTES)[1] # جمله فارسی

    # در چیدمان فارسی، برای جلوگیری از بهم ریختگی، ساختار را ساده‌تر و راست‌چین می‌کنیم
    msg = f"📅 **وضعیت زمانی شما | {date_str}**\n"
    msg += f"⌚️ ساعت: {time_str} (ایران)\n\n"
    
    msg += "╭ 🚧 **پرونده‌های اداری و مهاجرتی**\n│\n"
    for key in ["residence", "iran_entry", "passport"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        # محاسبه اختلاف زمان (از نظر ریاضی فرقی نمی‌کند مبدا کجا باشد، فاصله تا تاریخ ثابت است)
        delta = relativedelta(t_date, datetime.now())
        
        msg += f"│ {item['icon']} **{item['fa_label']}**\n"
        msg += f"│ 📅 تاریخ: {item['date']}\n"
        msg += f"│ ⏳ مانده: {format_duration(delta, 'fa')}\n│\n"
    msg += "╰\n\n"

    msg += "╭ 🎉 **مناسبت‌های پیش‌رو**\n│\n"
    for key in ["nowruz_05", "nowruz_06"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        delta = relativedelta(t_date, datetime.now())
        
        msg += f"│ {item['icon']} **{item['fa_label']}**\n"
        msg += f"│ 📅 تاریخ: {item['date']}\n"
        msg += f"│ ⏳ مانده: {format_duration(delta, 'fa')}\n│\n"
    msg += "╰\n\n"
    
    msg += f"💡 *\"{quote}\"*"
    return msg

# ==========================================
# بخش ۴: کنترل و دکمه‌ها
# ==========================================

def get_keyboard():
    """دکمه‌های تغییر زبان"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇩🇪 Deutsch (آلمان)", callback_data="view_de"),
            InlineKeyboardButton("🇮🇷 فارسی (ایران)", callback_data="view_fa")
        ]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # پیش‌فرض نسخه آلمانی را نشان می‌دهد
    await update.message.reply_text(
        get_german_view(), 
        parse_mode='Markdown', 
        reply_markup=get_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # حذف حالت لودینگ دکمه
    
    new_text = ""
    if query.data == "view_de":
        new_text = get_german_view()
    elif query.data == "view_fa":
        new_text = get_persian_view()
    
    # فقط اگر متن تغییر کرده باشد پیام را ویرایش می‌کند
    try:
        await query.edit_message_text(
            text=new_text, 
            parse_mode='Markdown', 
            reply_markup=get_keyboard()
        )
    except Exception:
        pass 

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    print("Bot started with Dual Timezone support...")
    application.run_polling()

if __name__ == "__main__":
    main()