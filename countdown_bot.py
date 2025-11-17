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
# بخش ۱: سرور
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive (Date Conversion Mode)!"

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

def get_user_targets(user_id):
    user_id = str(user_id)
    if user_id not in all_users_data:
        all_users_data[user_id] = copy.deepcopy(DEFAULT_TARGETS)
        save_data()
    return all_users_data[user_id]

def update_user_targets(user_id, new_targets):
    user_id = str(user_id)
    all_users_data[user_id] = new_targets
    save_data()

load_data()

# ==========================================
# بخش ۴: مترجم و مبدل تاریخ
# ==========================================

def translate_text(text):
    try:
        de_text = GoogleTranslator(source='auto', target='de').translate(text)
        fa_text = GoogleTranslator(source='auto', target='fa').translate(text)
        return de_text, fa_text
    except Exception:
        return text, text

def gregorian_to_shamsi(date_str):
    """تبدیل تاریخ میلادی (رشته) به شمسی (رشته)"""
    try:
        # تبدیل رشته به آبجکت تاریخ
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        # تبدیل به شمسی
        j_date = jdatetime.date.fromgregorian(date=dt.date())
        # تنظیم زبان فارسی برای نام ماه‌ها
        jdatetime.set_locale('fa_IR')
        return j_date.strftime("%d %B %Y")
    except Exception:
        return date_str

# ==========================================
# بخش ۵: توابع نمایش
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

def get_german_view(user_id):
    targets = get_user_targets(user_id)
    now = datetime.now(TZ_GERMANY)
    date_str = f"{now.day}. {DE_MONTHS[now.month]} {now.year}"
    time_str = now.strftime("%H:%M")
    quote = random.choice(QUOTES)[0]

    msg = f"📅 **Aktueller Status | {date_str}**\n"
    msg += f"⌚️ Uhrzeit: {time_str} (Deutschland)\n\n"
    
    if not targets:
        msg += "📭 Deine Liste ist leer.\nNutze '➕ Event hinzufügen'.\n\n"
    else:
        msg += "╭ 📌 **Persönliche Termine**\n│\n"
        for key, item in targets.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y").replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None)
            delta = relativedelta(t_date, now_naive)
            
            # نمایش به آلمانی (تاریخ میلادی)
            msg += f"│ {item['icon']} **{item['de_label']}**\n│ └ 📅 {item['date']} | ⏳ {format_duration(delta, 'de')}\n│\n"
        msg += "╰\n\n"

    msg += f"💡 *\"{quote}\"*"
    return msg

def get_persian_view(user_id):
    targets = get_user_targets(user_id)
    now_iran = datetime.now(TZ_IRAN)
    
    # تاریخ امروز به شمسی
    j_now = jdatetime.datetime.fromgregorian(datetime=now_iran)
    jdatetime.set_locale('fa_IR')
    date_str = j_now.strftime("%d %B %Y")
    time_str = now_iran.strftime("%H:%M")
    
    quote = random.choice(QUOTES)[1]

    msg = f"\u200f📅 **وضعیت زمانی شما | {date_str}**\n"
    msg += f"\u200f⌚️ ساعت: {time_str} (ایران)\n\n"
    
    if not targets:
        msg += "\u200f📭 لیست شما خالی است.\n\u200fبرای شروع، دکمه '➕ افزودن رویداد' را بزنید.\n\n"
    else:
        msg += "\u200f📌 **برنامه‌های شخصی شما**\n"
        msg += "➖➖➖➖➖➖➖➖➖➖\n"
        for key, item in targets.items():
            t_date = datetime.strptime(item["date"], "%d.%m.%Y")
            delta = relativedelta(t_date, datetime.now())
            
            # تبدیل تاریخ رویداد به شمسی برای نمایش
            shamsi_date = gregorian_to_shamsi(item['date'])
            
            # نمایش به فارسی (تاریخ شمسی)
            msg += f"\u200f{item['icon']} **{item['fa_label']}**\n"
            msg += f"\u200f   📅 {shamsi_date} | ⏳ {format_duration(delta, 'fa')}\n\n"

    msg += f"\u200f💡 *\"{quote}\"*"
    return msg

def get_main_menu_keyboard():
    keyboard = [
        ["🇩🇪 Deutsch (آلمان)", "🇮🇷 فارسی (ایران)"],
        ["➕ افزودن رویداد", "🗑 حذف رویداد"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==========================================
# بخش ۶: هندلرهای افزودن و حذف
# ==========================================

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 **عنوان رویداد** را بنویسید (فارسی یا آلمانی):\n\n(انصراف: دکمه انصراف)", 
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True)
    )
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "❌ انصراف":
        await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
    
    await update.message.reply_text("🔄 در حال ترجمه...")
    de_title, fa_title = translate_text(text)
    
    context.user_data['de_title'] = de_title
    context.user_data['fa_title'] = fa_title
    
    await update.message.reply_text(
        f"🇩🇪: **{de_title}**\n🇮🇷: **{fa_title}**\n\n"
        "📅 حالا **تاریخ میلادی** را وارد کنید (`DD.MM.YYYY`):\nمثال: `12.01.2026`", 
        parse_mode='Markdown'
    )
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "❌ انصراف":
        await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    try:
        # اعتبارسنجی تاریخ میلادی
        datetime.strptime(text, "%d.%m.%Y")
        
        user_id = update.effective_user.id
        user_targets = get_user_targets(user_id)
        
        new_id = f"custom_{int(datetime.now().timestamp())}"
        user_targets[new_id] = {
            "date": text, # همیشه میلادی ذخیره می‌شود
            "de_label": context.user_data['de_title'],
            "fa_label": context.user_data['fa_title'],
            "icon": "📌", 
            "type": "personal"
        }
        
        update_user_targets(user_id, user_targets)
        
        await update.message.reply_text(
            f"✅ رویداد اضافه شد!", 
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ فرمت تاریخ اشتباه است. لطفاً میلادی وارد کنید:\n`DD.MM.YYYY`", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ لغو شد.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def delete_menu_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    targets = get_user_targets(user_id)
    
    if not targets:
        await update.message.reply_text("📭 لیست خالی است.")
        return

    keyboard = []
    for key, item in targets.items():
        btn_text = f"🗑 {item['fa_label']} ({item['date']})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بستن", callback_data="close_delete")])
    
    await update.message.reply_text("🗑 **کدام مورد حذف شود؟**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def delete_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    user_targets = get_user_targets(user_id)
    
    if data.startswith("del_"):
        key_to_delete = data.replace("del_", "")
        if key_to_delete in user_targets:
            deleted_item = user_targets.pop(key_to_delete)
            update_user_targets(user_id, user_targets)
            await query.answer(f"حذف شد: {deleted_item['fa_label']}")
            
            # Refresh list
            keyboard = []
            for key, item in user_targets.items():
                btn_text = f"🗑 {item['fa_label']} ({item['date']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{key}")])
            keyboard.append([InlineKeyboardButton("🔙 بستن", callback_data="close_delete")])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.answer("یافت نشد.")
            
    elif data == "close_delete":
        await query.answer()
        await query.edit_message_text("✅ منوی حذف بسته شد.")

# ==========================================
# بخش ۸: هندلرهای اصلی
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    get_user_targets(user_id)
    
    await update.message.reply_text(
        "سلام! 👋\nبه ربات هوشمند مدیریت زمان خوش آمدید.\n\n"
        "📅 **هوشمند:** تاریخ را به میلادی وارد کنید، من در بخش فارسی آن را به شمسی تبدیل می‌کنم.",
        reply_markup=get_main_menu_keyboard()
    )

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.effective_user.id
    
    if "Deutsch" in text:
        await update.message.reply_text(get_german_view(user_id), parse_mode='Markdown')
    elif "فارسی" in text:
        await update.message.reply_text(get_persian_view(user_id), parse_mode='Markdown')

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
    
    print("Bot started with Date Conversion...")
    application.run_polling()

if __name__ == "__main__":
    main()