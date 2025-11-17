import logging
import threading
import jdatetime  # کتابخانه برای تاریخ شمسی
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# بخش ۱: سیستم زنده نگه داشتن (Flask)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# ==========================================
# بخش ۲: تنظیمات ربات
# ==========================================

# توکن خود را اینجا قرار دهید
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تنظیم زبان تاریخ شمسی به فارسی
jdatetime.set_locale('fa_IR')

TARGET_DATES = {
    "iran_entry": ("18.12.2026", "تاریخ ممکن ورود به ایران"),
    "nowruz_1405": ("21.03.2026", "تاریخ عید نوروز ۱۴۰۵"),
    "nowruz_1406": ("21.03.2027", "تاریخ عید نوروز ۱۴۰۶"),
    "residence_end": ("22.09.2026", "تاریخ پایان کارت اقامت"),
    "passport_end": ("11.01.2028", "تاریخ پایان اعتبار پاسپورت"),
}

# دیکشنری برای ترجمه نام ماه‌های میلادی به فارسی
GREGORIAN_MONTHS = {
    1: "ژانویه", 2: "فوریه", 3: "مارس", 4: "آوریل", 5: "مه", 6: "ژوئن",
    7: "ژوئیه", 8: "اوت", 9: "سپتامبر", 10: "اکتبر", 11: "نوامبر", 12: "دسامبر"
}

def get_current_date_info():
    """این تابع متن تاریخ و ساعت فعلی را دقیقاً به فرمت شما می‌سازد"""
    now = datetime.now()
    j_now = jdatetime.datetime.now()

    # ساخت تاریخ میلادی با ماه فارسی (مثل: 17 نوامبر 2025)
    g_month_name = GREGORIAN_MONTHS[now.month]
    g_date_str = f"{now.day} {g_month_name} {now.year}"

    # ساخت تاریخ شمسی (مثل: 26 آبان 1404)
    # %B نام ماه شمسی را کامل می‌نویسد
    j_date_str = j_now.strftime("%d %B %Y")

    # ساعت و دقیقه
    time_str = now.strftime("%H:%M")

    return f"امروز {g_date_str} و همچنین {j_date_str} می‌باشد . ساعت {time_str} دقیقه"

def get_remaining_time(target_date_str):
    """محاسبه زمان باقیمانده"""
    try:
        target_date = datetime.strptime(target_date_str, "%d.%m.%Y")
        now = datetime.now()

        if now > target_date:
            return f"تاریخ {target_date_str} قبلاً گذشته است.", False

        delta = relativedelta(target_date, now)
        parts = []
        if delta.years > 0: parts.append(f"{delta.years} سال")
        if delta.months > 0: parts.append(f"{delta.months} ماه")
        if delta.days > 0: parts.append(f"{delta.days} روز")
        if delta.hours > 0: parts.append(f"{delta.hours} ساعت")
        if delta.minutes > 0: parts.append(f"{delta.minutes} دقیقه")
        
        if not parts and delta.seconds > 0: parts.append(f"{delta.seconds} ثانیه")
        elif not parts: return "همین الان!", True

        return " و ".join(parts), True
    except Exception as e:
        logger.error(f"Error: {e}")
        return "خطا در محاسبه.", False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []
    for key, (date_str, label) in TARGET_DATES.items():
        button = InlineKeyboardButton(label, callback_data=key)
        keyboard.append([button])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # اینجا هم می‌تونی ساعت رو نشون بدی (اختیاری)
    await update.message.reply_text(
        "سلام! 🗓\nبرای مشاهده زمان باقیمانده انتخاب کنید:",
        reply_markup=reply_markup
    )

async def button_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    selected_key = query.data

    if selected_key in TARGET_DATES:
        date_str, label = TARGET_DATES[selected_key]
        remaining_time_str, success = get_remaining_time(date_str)
        
        # دریافت متن تاریخ و ساعت جاری
        current_info = get_current_date_info()

        response_text = f"**⏳ زمان باقیمانده تا:**\n{label}\n"
        response_text += f"**تاریخ مقصد:** {date_str}\n"
        response_text += "-----------------------------------\n"
        response_text += f"**{remaining_time_str}**\n\n"
        response_text += "📆 **اطلاعات امروز:**\n"
        response_text += f"{current_info}"

        try:
            await query.edit_message_text(text=response_text, parse_mode='Markdown')
        except Exception:
            pass
    else:
        await query.edit_message_text(text="خطا: گزینه یافت نشد.")

def main() -> None:
    keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click_handler))
    application.run_polling()

if __name__ == "__main__":
    main()
