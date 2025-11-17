
import logging
import threading
import os
from flask import Flask
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# بخش ۱: سیستم زنده نگه داشتن ربات (Flask)
# این بخش باعث می‌شود Render فکر کند ما یک وب‌سایت هستیم
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    # پورت 10000 پورتی است که معمولاً Render باز می‌کند
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    """این تابع سرور وب را در یک رشته جداگانه اجرا می‌کند"""
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

# ==========================================
# بخش ۲: تنظیمات و منطق ربات تلگرام
# ==========================================

# توکن خود را دقیقاً اینجا قرار بده
BOT_TOKEN = "8562902859:AAEIBDk6cYEf6efIGJi8GSNTMaCQMuxlGLU"

# تنظیمات لاگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تاریخ‌های مد نظر شما
TARGET_DATES = {
    "iran_entry": ("18.12.2026", "تاریخ ممکن ورود به ایران"),
    "nowruz_1405": ("21.03.2026", "تاریخ عید نوروز ۱۴۰۵"),
    "nowruz_1406": ("21.03.2027", "تاریخ عید نوروز ۱۴۰۶"),
    "residence_end": ("22.09.2026", "تاریخ پایان کارت اقامت"),
    "passport_end": ("11.01.2028", "تاریخ پایان اعتبار پاسپورت"),
}

def get_remaining_time(target_date_str):
    """محاسبه دقیق زمان باقیمانده"""
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
        
        if not parts and delta.seconds > 0:
            parts.append(f"{delta.seconds} ثانیه")
        elif not parts:
            return "همین الان!", True

        return " و ".join(parts), True

    except Exception as e:
        logger.error(f"Error in calculation: {e}")
        return "خطا در محاسبه تاریخ.", False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش منوی دکمه‌ای"""
    keyboard = []
    for key, (date_str, label) in TARGET_DATES.items():
        button = InlineKeyboardButton(label, callback_data=key)
        keyboard.append([button])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "سلام! 🗓\nبرای مشاهده زمان باقیمانده، لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def button_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ به کلیک دکمه"""
    query = update.callback_query
    await query.answer()

    selected_key = query.data

    if selected_key in TARGET_DATES:
        date_str, label = TARGET_DATES[selected_key]
        remaining_time_str, success = get_remaining_time(date_str)
        
        response_text = f"**⏳ زمان باقیمانده تا:**\n{label}\n\n"
        response_text += f"**تاریخ مقصد:** {date_str}\n"
        response_text += "-----------------------------------\n"
        response_text += f"**{remaining_time_str}**"

        # استفاده از try-except برای جلوگیری از خطای "پیام تغییر نکرده است"
        try:
            await query.edit_message_text(text=response_text, parse_mode='Markdown')
        except Exception:
            pass 
    else:
        await query.edit_message_text(text="خطا: گزینه یافت نشد.")

def main() -> None:
    """اجرای اصلی"""
    # ۱. ابتدا سرور وب را روشن می‌کنیم (برای دور زدن محدودیت Render)
    keep_alive()
    
    # ۲. سپس ربات تلگرام را اجرا می‌کنیم
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click_handler))

    print("ربات و سرور وب در حال اجرا هستند...")
    application.run_polling()

if __name__ == "__main__":
    main()