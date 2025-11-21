import logging
import threading
import os
import uuid
from datetime import datetime
import jdatetime
import certifi
# Added 'request' and 'jsonify' for the API
from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# --- CONFIGURATION ---
app = Flask(__name__, template_folder='templates')

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
WEBAPP_URL_BASE = os.getenv("WEBAPP_URL_BASE")

try: ADMIN_ID = int(os.getenv("ADMIN_ID"))
except: ADMIN_ID = None

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
client = None
def get_collection():
    global client
    if not MONGO_URI: return None
    try:
        if client is None:
            ca = certifi.where()
            client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
        return client['time_manager_db']['users']
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

# --- DATE PARSER ---
def parse_date(text):
    if not text: return None
    text = text.replace('/', '.').replace('-', '.')
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    text = text.translate(trans)
    parts = [p for p in text.split('.') if p.isdigit()]
    if len(parts) != 3: return None
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None
        if y < 1500: 
            g = jdatetime.date(y, m, d).togregorian()
            return datetime(g.year, g.month, g.day).strftime("%d.%m.%Y")
        return datetime(y, m, d).strftime("%d.%m.%Y")
    except: return None

# --- FLASK ROUTES ---
@app.route('/')
def home():
    return """
    <html><head><script src="https://telegram.org/js/telegram-web-app.js"></script></head>
    <body style="background:#f4f6f8;font-family:sans-serif;text-align:center;padding-top:50px;">
        <script>
            const tg = window.Telegram.WebApp; tg.ready();
            if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                window.location.href = "/webapp/" + tg.initDataUnsafe.user.id;
            } else { document.write("Please open in Telegram"); }
        </script>
    </body></html>
    """

@app.route('/webapp/<user_id>')
def webapp(user_id):
    coll = get_collection()
    if coll is None: return "DB Error", 500
    try:
        user_doc = coll.find_one({"_id": str(user_id)})
        targets = user_doc.get('targets', {}) if user_doc else {}
        for key, item in targets.items():
            try:
                g_date = datetime.strptime(item['date'], "%d.%m.%Y")
                j_date = jdatetime.date.fromgregorian(date=g_date.date())
                item['shamsi_date'] = j_date.strftime("%Y/%m/%d")
            except: item['shamsi_date'] = ""
        return render_template('index.html', user_data=targets, user_id=str(user_id))
    except: return "Error", 500

# --- API ROUTES (FIXED) ---
@app.route('/api/add/<user_id>', methods=['POST'])
def add_event_api(user_id):
    try:
        data = request.json
        title = data.get('title')
        date_str = data.get('date')
        formatted = parse_date(date_str)
        
        if not formatted: return jsonify({"success": False, "error": "Invalid Date"}), 400
        
        coll = get_collection()
        
        # FIX WAS APPLIED HERE: Explicit check 'is not None'
        if coll is not None:
            evt_id = f"evt_{uuid.uuid4().hex[:6]}"
            new_item = {"title": title, "date": formatted}
            coll.update_one({"_id": str(user_id)}, {"$set": {f"targets.{evt_id}": new_item}}, upsert=True)
            return jsonify({"success": True})
            
        return jsonify({"success": False, "error": "DB Connection Failed"}), 500
    except Exception as e:
        logger.error(f"API Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/delete/<user_id>', methods=['POST'])
def delete_event_api(user_id):
    try:
        data = request.json
        key = data.get('key')
        coll = get_collection()
        
        # FIX WAS APPLIED HERE: Explicit check 'is not None'
        if coll is not None:
            coll.update_one({"_id": str(user_id)}, {"$unset": {f"targets.{key}": ""}})
            return jsonify({"success": True})
            
        return jsonify({"success": False, "error": "DB Connection Failed"}), 500
    except Exception as e:
        logger.error(f"API Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# --- BOT HELPERS ---
def main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}" if WEBAPP_URL_BASE else "https://telegram.org"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Contact Support")]
    ], resize_keyboard=True)

# --- BOT HANDLERS ---
GET_TITLE, GET_DATE = range(2)
SUPPORT_MSG = range(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    coll = get_collection()
    if coll is not None: 
        coll.update_one({"_id": uid}, {"$setOnInsert": {"targets": {}}}, upsert=True)
    await update.message.reply_text(
        f"👋 **Hello {update.effective_user.first_name}!**\n\nSelect an option:",
        reply_markup=main_kb(uid), parse_mode='Markdown'
    )

async def post_init(application: Application):
    if WEBAPP_URL_BASE:
        try: await application.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="📱 Open App", web_app=WebAppInfo(url=WEBAPP_URL_BASE)))
        except: pass

# --- LEGACY WEB APP BRIDGE (Optional, but kept for safety) ---
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    if data == "add":
        await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
        return GET_TITLE
    elif data == "delete":
        await delete_menu_logic(update, context)
        return ConversationHandler.END

# --- ADD CONVERSATION (Bot Mode) ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Enter Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text in ["❌ Cancel", "📱 Open App", "➕ Add Event", "🗑 Delete Event"]:
        await update.message.reply_text("❌ Cancelled.", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END
    context.user_data['title'] = text
    await update.message.reply_text("📅 **Enter Date (Year.Month.Day):**", parse_mode='Markdown')
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    formatted = parse_date(text)
    uid = str(update.effective_user.id)
    if formatted:
        coll = get_collection()
        if coll is not None:
            evt_id = f"evt_{uuid.uuid4().hex[:6]}"
            new_item = {"title": context.user_data['title'], "date": formatted}
            coll.update_one({"_id": uid}, {"$set": {f"targets.{evt_id}": new_item}}, upsert=True)
            await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else:
            await update.message.reply_text("⛔ DB Error", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date.** Try again:", parse_mode='Markdown')
        return GET_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

# --- DELETE LOGIC (Bot Mode) ---
async def delete_menu_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_menu_logic(update, context)

async def delete_menu_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    coll = get_collection()
    if coll is not None:
        user_doc = coll.find_one({"_id": uid})
        targets = user_doc.get('targets', {}) if user_doc else {}
    else: targets = {}
    if not targets:
        await update.message.reply_text("📭 **List is empty.**", reply_markup=main_kb(uid), parse_mode='Markdown')
        return
    kb = []
    for k, v in targets.items():
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"ask_{k}")])
    await update.message.reply_text("🗑 **Tap to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = str(update.effective_user.id)
    if data.startswith("ask_"):
        key = data.replace("ask_", "")
        kb = [[InlineKeyboardButton("✅ Yes", callback_data=f"cnf_{key}")], [InlineKeyboardButton("🔙 No", callback_data="no")]]
        await query.edit_message_text("⚠️ **Confirm deletion?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    elif data.startswith("cnf_"):
        key = data.replace("cnf_", "")
        coll = get_collection()
        if coll is not None:
            coll.update_one({"_id": uid}, {"$unset": {f"targets.{key}": ""}})
            await query.edit_message_text("✅ **Deleted.**")
    elif data == "no":
        await query.delete_message()

# --- SUPPORT ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📬 **Type your message:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return SUPPORT_MSG

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Cancel": return await cancel(update, context)
    if ADMIN_ID:
        await context.bot.send_message(ADMIN_ID, f"📩 **Support:**\nID: `{update.effective_user.id}`\n\n{msg}\n\nReply: `/reply {update.effective_user.id} msg`", parse_mode='Markdown')
        await update.message.reply_text("✅ Sent!", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid, txt = context.args[0], " ".join(context.args[1:])
        await context.bot.send_message(uid, f"📨 **Support Reply:**\n{txt}", parse_mode='Markdown')
        await update.message.reply_text("✅ Sent.")
    except: pass

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(➕|Add)"), add_start),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data)
        ],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT, receive_title)],
            GET_DATE: [MessageHandler(filters.TEXT, receive_date)]
        },
        fallbacks=[MessageHandler(filters.ALL, receive_title)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Contact)"), support_start)],
        states={SUPPORT_MSG: [MessageHandler(filters.TEXT, support_receive)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    ))
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_menu_manual))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", admin_reply))
    app.add_handler(CallbackQueryHandler(delete_callback))
    print("✅ Bot Running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()