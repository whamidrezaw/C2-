import logging
import threading
import random
import jdatetime
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# بخش ۱: تنظیمات سرور (ضد خواب)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! Dashboard Updated."

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# ==========================================
# بخش ۲: تنظیمات ربات و داده‌ها
# ==========================================
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تنظیم زبان تاریخ شمسی
jdatetime.set_locale('fa_IR')

# جملات انگیزشی (آلمانی و فارسی)
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

# نام ماه‌های آلمانی
DE_MONTHS = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni",
    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"
}

# تاریخ‌های هدف
TARGETS = {
    "residence": {"date": "22.09.2026", "de_label": "Ablauf Aufenthaltstitel", "fa_label": "پایان کارت اقامت", "icon": "🔴"},
    "iran_entry": {"date": "18.12.2026", "de_label": "Geplante Einreise (Iran)", "fa_label": "ورود احتمالی به ایران", "icon": "🟡"},
    "passport": {"date": "11.01.2028", "de_label": "Ablauf Reisepass", "fa_label": "پایان اعتبار پاسپورت", "icon": "🟢"},
    "nowruz_05": {"date": "21.03.2026", "de_label": "Nouruz-Fest 1405", "fa_label": "عید نوروز ۱۴۰۵", "icon": "🔹"},
    "nowruz_06": {"date": "21.03.2027", "de_label": "Nouruz-Fest 1406", "fa_label": "عید نوروز ۱۴۰۶", "icon": "🔹"},
}

# ==========================================
# بخش ۳: توابع محاسباتی و گرافیکی
# ==========================================

def format_duration(delta, lang="de"):
    """تبدیل فاصله زمانی به متن کامل و دقیق"""
    parts = []
    
    if lang == "de":
        if delta.years > 0: parts.append(f"{delta.years} Jahr{'e' if delta.years > 1 else ''}")
        if delta.months > 0: parts.append(f"{delta.months} Monat{'e' if delta.months > 1 else ''}")
        if delta.days > 0: parts.append(f"{delta.days} Tag{'e' if delta.days > 1 else ''}")
        # اگر بخواهید ساعت دقیق هم باشد:
        # if delta.hours > 0: parts.append(f"{delta.hours} Std.")
        return ", ".join(parts) if parts else "Heute!"
    else: # fa
        if delta.years > 0: parts.append(f"{delta.years} سال")
        if delta.months > 0: parts.append(f"{delta.months} ماه")
        if delta.days > 0: parts.append(f"{delta.days} روز")
        return " و ".join(parts) if parts else "همین امروز!"

def generate_dashboard():
    now = datetime.now()
    j_now = jdatetime.datetime.now()
    
    # انتخاب یک جمله تصادفی
    quote_de, quote_fa = random.choice(QUOTES)

    # --- ساخت بخش آلمانی ---
    de_date_str = f"{now.day}. {DE_MONTHS[now.month]} {now.year}"
    de_time_str = now.strftime("%H:%M")
    
    msg = f"📅 **Aktueller Status | {de_date_str}**\n"
    msg += f"⌚️ Uhrzeit: {de_time_str}\n\n"
    
    msg += "╭ 🚧 **Behörden & Aufenthalt**\n│\n"
    
    # آیتم‌های اداری (آلمانی)
    for key in ["residence", "iran_entry", "passport"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        delta = relativedelta(t_date, now)
        duration = format_duration(delta, "de")
        
        msg += f"│ {item['icon']} **{item['de_label']}**\n"
        msg += f"│ └ 📅 Frist: {item['date']}\n"
        msg += f"│ └ ⏳ Restzeit: {duration}\n│\n"
    
    msg += "╰\n\n╭ 🎉 **Kommende Ereignisse**\n│\n"
    
    # آیتم‌های مناسبتی (آلمانی)
    for key in ["nowruz_05", "nowruz_06"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        delta = relativedelta(t_date, now)
        duration = format_duration(delta, "de")
        
        msg += f"│ {item['icon']} **{item['de_label']}**\n"
        msg += f"│ └ 📅 Datum: {item['date']}\n"
        msg += f"│ └ ⏳ Restzeit: {duration}\n│\n"
        
    msg += "╰\n\n"
    msg += f"💡 *\"{quote_de}\"*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # --- ساخت بخش فارسی ---
    fa_date_str = j_now.strftime("%d %B %Y")
    
    msg += f"📅 **وضعیت زمانی شما | {fa_date_str}**\n"
    msg += f"⌚️ ساعت: {de_time_str}\n\n"
    
    msg += "╭ 🚧 **پرونده‌های اداری و مهاجرتی**\n│\n"
    
    # آیتم‌های اداری (فارسی)
    for key in ["residence", "iran_entry", "passport"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        delta = relativedelta(t_date, now)
        duration = format_duration(delta, "fa")
        
        msg += f"│ {item['icon']} **{item['fa_label']}**\n"
        msg += f"│ └ 📅 تاریخ: {item['date']}\n"
        msg += f"│ └ ⏳ باقیمانده: {duration}\n│\n"

    msg += "╰\n\n╭ 🎉 **مناسبت‌های پیش‌رو**\n│\n"

    # آیتم‌های مناسبتی (فارسی)
    for key in ["nowruz_05", "nowruz_06"]:
        item = TARGETS[key]
        t_date = datetime.strptime(item["date"], "%d.%m.%Y")
        delta = relativedelta(t_date, now)
        duration = format_duration(delta, "fa")
        
        msg += f"│ {item['icon']} **{item['fa_label']}**\n"
        msg += f"│ └ 📅 تاریخ: {item['date']}\n"
        msg += f"│ └ ⏳ باقیمانده: {duration}\n│\n"

    msg += "╰\n\n"
    msg += f"💡 *\"{quote_fa}\"*"
    
    return msg

# ==========================================
# بخش ۴: هندلرها
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش داشبورد اصلی"""
    dashboard_text = generate_dashboard()
    
    # دکمه رفرش برای به‌روزرسانی زمان
    keyboard = [[InlineKeyboardButton("🔄 بروزرسانی وضعیت | Aktualisieren", callback_data="refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(dashboard_text, parse_mode='Markdown', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Updating... | در حال بروزرسانی")
    
    if query.data == "refresh":
        new_text = generate_dashboard()
        try:
            await query.edit_message_text(text=new_text, parse_mode='Markdown', reply_markup=query.message.reply_markup)
        except Exception:
            pass # اگر متن تغییر نکرده باشد ارور نمیدهد

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running with Dashboard...")
    application.run_polling()

if __name__ == "__main__":
    main()