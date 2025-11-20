import logging
import threading
import os
import uuid
from datetime import datetime
import jdatetime
import certifi
from flask import Flask, render_template
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# --- CONFIGURATION ---
app = Flask(__name__, template_folder='templates')

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

# ⚠️ ADMIN CONFIGURATION (For Anonymous Support)
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID")) # Ensure this is set in your environment variables
except:
    ADMIN_ID = None
    print("⚠️ WARNING: ADMIN_ID is not set. Support messages will fail.")

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
client = None
users_collection = None

def connect_db():
    global client, users_collection
    if not MONGO_URI: return None
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
    # Auto-redirect to the correct user page
    return """
    <html><head><script src="https://telegram.org/js/telegram-web-app.js"></script></head>
    <body style="background-color:#f4f6f8; font-family:sans-serif; text-align:center; padding-top:50px;">
        <p>Loading your Time Manager...</p>
        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                window.location.href = "/webapp/" + tg.initDataUnsafe.user.id;
            } else { document.body.innerHTML = "<p>Please open this inside Telegram.</p>"; }
        </script>
    </body></html>
    """

@app.route('/webapp/<user_id>')
def webapp(user_id):
    coll = connect_db()
    if coll is None: return "Database Error", 500
    try:
        raw_data = coll.find_one({"_id": str(user_id)})
        targets = raw_data.get('targets', {}) if raw_data else {}
        
        # Date Processing
        for key, item in targets.items():
            try:
                g_date = datetime.strptime(item['date'], "%d.%m.%Y")
                j_date = jdatetime.date.fromgregorian(date=g_date.date())
                item['shamsi_date'] = j_date.strftime("%Y/%m/%d")
            except: item['shamsi_date'] = ""
            
        return render_template('index.html', user_data=targets)
    except: return "Application Error", 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# --- HELPERS ---
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

# --- STATES ---
GET_TITLE, GET_DATE = range(2)
SUPPORT_MSG = range(1)

# --- START HANDLER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_first_name = update.effective_user.first_name
    get_user_data(uid)
    
    # NEW GREETING MESSAGE
    welcome_text = (
        f"👋 **Hello, {user_first_name}!**\n\n"
        "I am your intelligent Time Manager Bot. I help you track important dates, birthdays, and deadlines.\n\n"
        "🚀 **How to use me:**\n"
        "1️⃣ **Open App:** Click the button below to see your visual timeline.\n"
        "2️⃣ **Add Event:** Use the menu to add a new countdown.\n"
        "3️⃣ **Colors:** \n"
        "   🔴 **Urgent:** Less than 6 months\n"
        "   🟡 **Upcoming:** 6 to 12 months\n"
        "   🟢 **Future:** More than 1 year\n\n"
        "👇 **Select an option below to start:**"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_kb(uid), parse_mode='Markdown')

async def post_init(application: Application):
    if WEBAPP_URL_BASE:
        try:
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="📱 Open App", web_app=WebAppInfo(url=WEBAPP_URL_BASE))
            )
        except: pass

# --- WEB APP ROUTER (THE FIX) ---
async def webapp_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This function receives signals from the Mini App.
    If 'add' -> It enters the conversation.
    If 'delete' -> It triggers the delete menu immediately.
    """
    data = update.effective_message.web_app_data.data
    
    if data == "add":
        # Transition to the Add Conversation
        await update.message.reply_text("📝 **Enter the name of your event:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
        return GET_TITLE
    
    elif data == "delete":
        # Trigger delete logic and END conversation state
        await delete_menu_logic(update, context)
        return ConversationHandler.END

# --- ADD CONVERSATION ---
async def add_start_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter the name of your event:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    context.user_data['title'] = text
    await update.message.reply_text("📅 **Enter the Date:**\n(e.g., `2025.01.01` or `1403.10.01`)", parse_mode='Markdown')
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    uid = update.effective_user.id
    formatted = parse_smart_date(text)
    
    if formatted:
        coll = connect_db()
        if coll:
            new_id = f"evt_{uuid.uuid4().hex[:8]}"
            new_item = {"title": context.user_data['title'], "date": formatted}
            coll.update_one({"_id": str(uid)}, {"$set": {f"targets.{new_id}": new_item}}, upsert=True)
            await update.message.reply_text("✅ **Event Saved Successfully!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ Database Error.", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date Format.**\nPlease try again (Year.Month.Day):", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE LOGIC ---
async def delete_trigger_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_menu_logic(update, context)

async def delete_menu_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    
    if not targets: 
        await update.message.reply_text("📭 **Your list is empty.**\nAdd an event first!", reply_markup=main_kb(uid), parse_mode='Markdown')
        return

    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"ask_{k}")])
    
    await update.message.reply_text("🗑 **Tap an event to delete it:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = update.effective_user.id
    
    if data.startswith("ask_"):
        key = data.replace("ask_", "")
        # Confirmation Buttons
        kb = [
            [InlineKeyboardButton("✅ Yes, Delete It", callback_data=f"confirm_{key}")],
            [InlineKeyboardButton("🔙 No, Cancel", callback_data="cancel_del")]
        ]
        await query.edit_message_text("⚠️ **Are you sure you want to delete this?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith("confirm_"):
        key = data.replace("confirm_", "")
        coll = connect_db()
        if coll:
            coll.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
            await query.answer("Deleted successfully")
            await query.edit_message_text("🗑 **Event Deleted.**")
        else:
            await query.answer("Database Error")
    
    elif data == "cancel_del":
        await query.answer("Cancelled")
        await query.delete_message()

# --- ANONYMOUS SUPPORT ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📬 **Contact Support**\n\nPlease type your message below. It will be sent anonymously to the admin.",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return SUPPORT_MSG

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    
    user = update.effective_user
    if ADMIN_ID:
        admin_text = (
            f"📩 **New Support Message**\n"
            f"🆔 User ID: `{user.id}`\n"
            f"👤 Name: {user.first_name}\n\n"
            f"💬 Message:\n{msg}\n\n"
            f"👉 **To Reply:** `/reply {user.id} Your Message`"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode='Markdown')
            await update.message.reply_text("✅ **Message Sent!** The admin will reply soon.", reply_markup=main_kb(user.id), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Support Send Error: {e}")
            await update.message.reply_text("❌ Internal Error. Admin ID might be wrong.")
    else:
        await update.message.reply_text("❌ Support system is currently offline (Admin ID not configured).")
        
    return ConversationHandler.END

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return # Ignore non-admins
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ Usage: `/reply <user_id> <message>`", parse_mode='Markdown')
            return
            
        target_uid = args[0]
        reply_text = " ".join(args[1:])
        
        await context.bot.send_message(
            chat_id=target_uid,
            text=f"📨 **New Message from Support:**\n\n{reply_text}",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Reply sent to `{target_uid}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send: {e}")

# --- IGNORE OTHERS ---
async def ignore_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⛔ **I didn't understand that.**\n\nPlease use the menu buttons below.",
        reply_markup=main_kb(update.effective_user.id),
        parse_mode='Markdown'
    )

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    if not BOT_TOKEN: return print("❌ BOT_TOKEN missing")

    app_bot = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # 1. Add Event Conversation (Includes WebApp Bridge)
    add_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(➕|Add)"), add_start_manual),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_router)
        ],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)]
        },
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    
    # 2. Support Conversation
    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Contact)"), support_start)],
        states={SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )

    app_bot.add_handler(add_conv)
    app_bot.add_handler(support_conv)
    
    app_bot.add_handler(CommandHandler("reply", admin_reply))
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger_manual))
    app_bot.add_handler(CallbackQueryHandler(delete_callback))
    
    # Catch-All (Must be last)
    app_bot.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, ignore_unknown))
    
    print("✅ Bot Updated & Running...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()