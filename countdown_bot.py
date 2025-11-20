import logging
import threading
import os
import uuid
from datetime import datetime
import jdatetime
import certifi
from flask import Flask, render_template, request
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# --- CONFIGURATION ---
app = Flask(__name__, template_folder='templates')

# Load Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")
# CHANGE THIS TO YOUR USERNAME (No @ symbol)
SUPPORT_USERNAME = "YourUsernameHere" 

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
client = None
users_collection = None

def connect_db():
    """Establishes or refreshes DB connection safely."""
    global client, users_collection
    if not MONGO_URI:
        logger.error("❌ MONGO_URI is missing!")
        return None
    try:
        if client is None:
            ca = certifi.where()
            client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db = client['time_manager_db']
            users_collection = db['users']
            logger.info("✅ MONGODB CONNECTED")
        return users_collection
    except Exception as e:
        logger.error(f"❌ DB CONNECTION FAILED: {e}")
        return None

# --- FLASK SERVER ---
@app.route('/')
def home():
    # FIX: This script automatically detects the User ID from Telegram
    # and redirects them to the correct /webapp/<id> page.
    return """
    <html>
    <head>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
    </head>
    <body style="background-color:#f4f6f8; font-family:sans-serif; text-align:center; padding-top:50px;">
        <p>Loading your data...</p>
        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                window.location.href = "/webapp/" + tg.initDataUnsafe.user.id;
            } else {
                document.body.innerHTML = "<p>Please open this from inside Telegram.</p>";
            }
        </script>
    </body>
    </html>
    """

@app.route('/webapp/<user_id>')
def webapp(user_id):
    coll = connect_db()
    if coll is None: return "Database Error", 500

    try:
        raw_data = coll.find_one({"_id": str(user_id)})
        targets = raw_data.get('targets', {}) if raw_data else {}
        
        # Pre-process for frontend
        for key, item in targets.items():
            try:
                g_date = datetime.strptime(item['date'], "%d.%m.%Y")
                j_date = jdatetime.date.fromgregorian(date=g_date.date())
                item['shamsi_date'] = j_date.strftime("%Y/%m/%d")
            except Exception: 
                item['shamsi_date'] = ""
                
        return render_template('index.html', user_data=targets)
    except Exception as e:
        logger.error(f"Webapp Error: {e}")
        return "Application Error", 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# --- DATA HELPERS ---
def get_user_data(uid):
    coll = connect_db()
    if coll is None: return {"_id": str(uid), "targets": {}}
    try:
        data = coll.find_one({"_id": str(uid)})
        if not data:
            coll.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except: return {"_id": str(uid), "targets": {}}

# --- DATE PARSER ---
def parse_smart_date(date_str):
    if not date_str: return None
    date_str = date_str.replace('/', '.').replace('-', '.')
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    parts = [p for p in date_str.split('.') if p.isdigit()]
    if len(parts) != 3: return None
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None
        final = None
        if y > 1900: final = datetime(y, m, d)
        elif y < 1500: 
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
        return final.strftime("%d.%m.%Y") if final else None
    except: return None

# --- KEYBOARDS ---
def main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}" if WEBAPP_URL_BASE else "https://telegram.org"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Contact Support")] 
    ], resize_keyboard=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    
    welcome_text = (
        "🌟 **Welcome to Time Manager Bot!** 🌟\n\n"
        "I am your smart assistant to track important events, birthdays, and deadlines.\n\n"
        "✨ **What can I do?**\n"
        "🔹 **Countdowns:** See exactly how many days are left.\n"
        "🔹 **Date Conversion:** I understand both Gregorian and Shamsi dates.\n"
        "🔹 **Visuals:** A beautiful Mini App to view your list.\n"
        "🔹 **Smart Alerts:** Colors change as the date gets closer!\n\n"
        "👇 **Select an option below to start:**"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_kb(uid), parse_mode='Markdown')

async def post_init(application: Application):
    if WEBAPP_URL_BASE:
        try:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="📱 Open App", web_app=WebAppInfo(url=WEBAPP_URL_BASE))
            )
        except Exception as e: logger.error(f"Menu Button Error: {e}")

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"📬 **Need Help?**\n\nClick below to message support directly."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Open Chat", url=f"https://t.me/{SUPPORT_USERNAME}")]])
    await update.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')

# --- WEBAPP DATA BRIDGE ---
async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    if data == "add":
        await add_start(update, context)
        return GET_TITLE 
    elif data == "delete":
        await delete_menu(update, context)

# --- ADD EVENT FLOW ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    context.user_data['title'] = update.message.text
    await update.message.reply_text("📅 **Enter Date (e.g., 1403.10.01 or 2025.01.01):**", parse_mode='Markdown')
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    uid = update.effective_user.id
    formatted = parse_smart_date(update.message.text)
    
    if formatted:
        coll = connect_db()
        if coll:
            new_id = f"evt_{uuid.uuid4().hex[:8]}"
            new_item = {"title": context.user_data['title'], "date": formatted}
            coll.update_one({"_id": str(uid)}, {"$set": {f"targets.{new_id}": new_item}}, upsert=True)
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ DB Error", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again:", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE FLOW (WITH CONFIRMATION) ---
async def delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Your list is empty.")
    
    kb = []
    for k, v in targets.items():
        # Stage 1: Select item to delete
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"ask_{k}")])
    await update.message.reply_text("🗑 **Select an event to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = update.effective_user.id
    
    if data.startswith("ask_"):
        # Stage 2: Ask for confirmation
        key = data.replace("ask_", "")
        # Store key temporarily? No need, pass it in button
        kb = [
            [InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_{key}")],
            [InlineKeyboardButton("❌ No, Keep it", callback_data="cancel_del")]
        ]
        await query.edit_message_text("⚠️ **Are you sure you want to delete this event?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith("confirm_"):
        # Stage 3: Actually Delete
        key = data.replace("confirm_", "")
        coll = connect_db()
        if coll:
            coll.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
            await query.answer("Deleted Successfully")
            await query.edit_message_text("🗑 Event has been deleted.")
        else:
            await query.answer("Database Error")

    elif data == "cancel_del":
        await query.answer("Cancelled")
        await query.delete_message()

# --- INPUT GUARD (IGNORE RANDOM MESSAGES) ---
async def ignore_wrong_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This runs if the user sends text/photo that isn't a command or part of a flow
    await update.message.reply_text(
        "⛔ **I didn't understand that.**\n\nPlease use the buttons below to control the bot.",
        reply_markup=main_kb(update.effective_user.id),
        parse_mode='Markdown'
    )

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    if not BOT_TOKEN: return print("❌ BOT_TOKEN missing")

    app_bot = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(➕|Add)"), add_start),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data) 
        ],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)]
        },
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    
    app_bot.add_handler(conv)
    app_bot.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_menu))
    app_bot.add_handler(MessageHandler(filters.Regex("^(📞|Contact)"), support_handler))
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(delete_callback))
    
    # CATCH-ALL HANDLER: Must be LAST. Ignores random text/media
    app_bot.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, ignore_wrong_input))
    
    print("✅ Bot Updated & Running...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()