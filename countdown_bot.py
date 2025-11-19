import logging
import threading
import json
import os
import re
from datetime import datetime
from flask import Flask, render_template
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from pymongo import MongoClient
import certifi
import jdatetime
import ssl

app = Flask(__name__, template_folder='templates')

# --- CONFIGURATION ---
BOT_TOKEN = "TOKEN_VAGHEI_BOT_KHOD_RA_INJA_VARED_KONID"
MONGO_URI = "mongodb+srv://soltanshahhamidreza_db_user:oImlEg2Md081ASoY@cluster0.qcuz3fw.mongodb.net/?appName=Cluster0"
WEBAPP_URL_BASE = "https://my-bot-new.onrender.com"
ADMIN_ID = 1081294386

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE CONNECTION ---
users_collection = None
try:
    ca = certifi.where()
    client = MongoClient(MONGO_URI, tls=True, tlsCAFile=ca, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['time_manager_db']
    users_collection = db['users']
    logger.info("✅ MONGODB CONNECTED")
except Exception as e:
    logger.error(f"❌ DB ERROR: {e}")

# --- FLASK ---
@app.route('/')
def home(): return "Bot Running"

@app.route('/webapp/<user_id>')
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get('targets', {})
    for key, item in targets.items():
        try:
            g_date = datetime.strptime(item['date'], "%d.%m.%Y")
            j_date = jdatetime.date.fromgregorian(date=g_date.date())
            item['shamsi_date'] = j_date.strftime("%Y.%m.%d")
        except: item['shamsi_date'] = ""
    return render_template('index.html', user_data=targets)

def run_server(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# --- DATA HELPERS ---
def get_user_data(uid):
    if users_collection is None: return {"_id": str(uid), "targets": {}}
    try:
        data = users_collection.find_one({"_id": str(uid)})
        if not data:
            users_collection.insert_one({"_id": str(uid), "targets": {}})
            return {"_id": str(uid), "targets": {}}
        return data
    except: return {"_id": str(uid), "targets": {}}

def update_db(uid, data):
    if users_collection is None: return False
    try:
        users_collection.update_one({"_id": str(uid)}, {"$set": data}, upsert=True)
        return True
    except: return False

def parse_smart_date(date_str):
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_str = date_str.translate(trans)
    date_str = re.sub(r'[/\-\s,]+', '.', date_str)
    parts = [p for p in date_str.split('.') if p]
    if len(parts) != 3: return None
    try:
        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
        y, m, d = 0, 0, 0
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None
        if y > 1900: final = datetime(y, m, d)
        elif y < 1500: 
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
        if final: return final.strftime("%d.%m.%Y")
    except: return None
    return None

# --- KEYBOARDS ---
def main_kb(uid):
    url = f"{WEBAPP_URL_BASE}/webapp/{uid}"
    return ReplyKeyboardMarkup([
        [KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url))],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# --- HANDLERS ---
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user_data(uid)
    await update.message.reply_text("👋 **Welcome!**", reply_markup=main_kb(uid), parse_mode='Markdown')

# --- MINI APP DATA HANDLER (پل ارتباطی مینی اپ و ربات) ---
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    if data == 'add':
        await add_start(update, context)
    elif data == 'delete':
        await delete_trigger(update, context)

async def unknown_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("❓ **Use buttons:**", reply_markup=main_kb(uid), parse_mode='Markdown')

# --- ADD ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 **Event Name:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return 1

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    context.user_data['title'] = update.message.text
    await update.message.reply_text("📅 **Enter Date:**", parse_mode='Markdown')
    return 2

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    uid = update.effective_user.id
    formatted = parse_smart_date(update.message.text)
    if formatted:
        data = get_user_data(uid)
        import uuid
        new_id = f"evt_{uuid.uuid4().hex[:8]}"
        data['targets'][new_id] = {"title": context.user_data['title'], "date": formatted, "type": "personal"}
        
        if users_collection:
             users_collection.update_one({"_id": str(uid)}, {"$set": {f"targets.{new_id}": data['targets'][new_id]}}, upsert=True)
             await update.message.reply_text("✅ **Saved!**", reply_markup=main_kb(uid), parse_mode='Markdown')
        else: await update.message.reply_text("⛔ DB Error", reply_markup=main_kb(uid))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid!** Try again.", parse_mode='Markdown')
        return 2

# --- DELETE (با تاییدیه) ---
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_user_data(uid)
    targets = data.get('targets', {})
    if not targets: return await update.message.reply_text("📭 Empty.")
    kb = []
    for k, v in targets.items():
        # مرحله اول: انتخاب آیتم برای حذف (پیشوند pre_del)
        kb.append([InlineKeyboardButton(f"❌ {v['title']}", callback_data=f"pre_del_{k}")])
    await update.message.reply_text("🗑 **Select to delete:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = query.data
    
    # مرحله دوم: نمایش تاییدیه
    if data.startswith("pre_del_"):
        key = data.replace("pre_del_", "")
        # دکمه‌های تایید و لغو
        confirm_kb = [
            [InlineKeyboardButton("✅ Yes, Delete", callback_data=f"del_{key}")],
            [InlineKeyboardButton("❌ No, Cancel", callback_data="cancel_del")]
        ]
        await query.edit_message_text("❓ **Are you sure?**", reply_markup=InlineKeyboardMarkup(confirm_kb), parse_mode='Markdown')

    # مرحله سوم: انجام حذف واقعی
    elif data.startswith("del_"):
        key = data.replace("del_", "")
        if users_collection:
            users_collection.update_one({"_id": str(uid)}, {"$unset": {f"targets.{key}": ""}})
            await query.answer("Deleted!")
            await query.edit_message_text("✅ **Item Deleted.**", parse_mode='Markdown')
        else: await query.answer("Error")
        
    # لغو حذف
    elif data == "cancel_del":
        await query.answer("Cancelled")
        await query.delete_message()

# --- SUPPORT ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💌 **Msg to Admin:**", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True), parse_mode='Markdown')
    return GET_SUPPORT

async def support_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancel": return await cancel(update, context)
    user = update.effective_user
    if ADMIN_ID:
        try:
            txt = f"📩 **Support**\nFrom: `{user.id}`\n\n{update.message.text}"
            await context.bot.send_message(chat_id=ADMIN_ID, text=txt, parse_mode='Markdown')
            await update.message.reply_text("✅ Sent!", reply_markup=main_kb(user.id))
        except: pass
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Canceled.", reply_markup=main_kb(update.effective_user.id))
    return ConversationHandler.END

def main():
    keep_alive()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add Handler for Mini App Data
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(➕|Add)"), add_start)],
        states={1: [MessageHandler(filters.TEXT, receive_title)], 2: [MessageHandler(filters.TEXT, receive_date)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    conv_sup = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📞|Support)"), support_start)],
        states={GET_SUPPORT: [MessageHandler(filters.TEXT, support_rec)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )

    app.add_handler(conv_add)
    app.add_handler(conv_sup)
    app.add_handler(MessageHandler(filters.Regex("^(🗑|Delete)"), delete_trigger))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(delete_cb))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_msg))
    
    print("Bot Running (Confirm Delete + MiniApp Buttons)...")
    app.run_polling()

if __name__ == "__main__":
    main()