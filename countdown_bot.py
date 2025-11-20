#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Reminder Bot – Single File – English Only
All features preserved: Mongo, Flask, WebApp, Rate-Limit, Date-Parser, Retry, Support, Delete, etc.
No extra folders or modules created.
"""

import os, logging, threading, json, re, time, certifi, ssl
from datetime import datetime, timedelta
from flask import Flask, render_template, request, abort
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters, Defaults
)
from telegram.constants import ParseMode
from pymongo import MongoClient
import jdatetime
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# ------------------ CONFIG ------------------
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MONGO_URI   = os.getenv("MONGO_URI")
WEBAPP_URL  = os.getenv("WEBAPP_URL_BASE")        # https://yourapp.onrender.com
ADMIN_ID    = int(os.getenv("ADMIN_ID", 0))

if not BOT_TOKEN or not MONGO_URI:
    exit("Missing BOT_TOKEN or MONGO_URI env vars")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ DB ------------------
ca = certifi.where()
client = MongoClient(
    MONGO_URI, tls=True, tlsCAFile=ca,
    serverSelectionTimeoutMS=5000, retryWrites=True
)
db = client["time_manager_db"]
users_coll = db["users"]
rate_coll  = db["rate_limit"]

# ------------------ FLASK ------------------
app_flask = Flask(__name__, template_folder="templates")

@app_flask.route("/")
def home(): return "Bot is Running (Single-File V2)"

@app_flask.route("/healthz")
def health():
    try:
        client.admin.command("ping")
        return "OK", 200
    except: return "DB ERROR", 500

@app_flask.route("/webapp/<user_id>")
def webapp(user_id):
    data = get_user_data(user_id)
    targets = data.get("targets", {})
    for item in targets.values():
        try:
            g = datetime.strptime(item["date"], "%d.%m.%Y")
            j = jdatetime.date.fromgregorian(date=g.date())
            item["shamsi_date"] = j.strftime("%Y.%m.%d")
        except: item["shamsi_date"] = ""
    return render_template("index.html", user_data=targets)

def run_server(): app_flask.run(host="0.0.0.0", port=10000)
threading.Thread(target=run_server, daemon=True).start()

# ------------------ DB HELPERS ------------------
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
def get_user_data(uid: str):
    data = users_coll.find_one({"_id": uid})
    if not data:
        users_coll.insert_one({"_id": uid, "targets": {}})
        return {"_id": uid, "targets": {}}
    return data

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
def update_db(uid: str, data: dict):
    users_coll.update_one({"_id": uid}, {"$set": data}, upsert=True)

# ------------------ RATE LIMIT ------------------
def check_rate(uid: str) -> bool:
    now = datetime.utcnow()
    rec = rate_coll.find_one({"_id": uid})
    if not rec:
        rate_coll.insert_one({"_id": uid, "count": 1, "reset": now + timedelta(seconds=60)})
        return True
    if now > rec["reset"]:
        rate_coll.update_one({"_id": uid}, {"$set": {"count": 1, "reset": now + timedelta(seconds=60)}})
        return True
    if rec["count"] >= 10: return False
    rate_coll.update_one({"_id": uid}, {"$inc": {"count": 1}})
    return True

# ------------------ DATE PARSER ------------------
def parse_date(ds: str):
    ds = str(ds).strip()[:20]
    ds = ds.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    ds = re.sub(r"[\/\s\-,]+", ".", ds)
    parts = [p for p in ds.split(".") if p]
    if len(parts) != 3: return None
    try:
        p1, p2, p3 = map(int, parts)
        y, m, d = 0, 0, 0
        if p1 > 1000: y, m, d = p1, p2, p3
        elif p3 > 1000: y, m, d = p3, p2, p1
        else: return None
        final = None
        if y > 1900: final = datetime(y, m, d)
        elif y < 1500:
            j = jdatetime.date(y, m, d).togregorian()
            final = datetime(j.year, j.month, j.day)
        if final: return final.strftime("%d.%m.%Y")
    except: return None
    return None

# ------------------ KEYBOARDS ------------------
def main_kb(uid: str):
    url = f"{WEBAPP_URL}/webapp/{uid}" if WEBAPP_URL else ""
    btn_app = KeyboardButton("📱 Open App", web_app=WebAppInfo(url=url)) if url else KeyboardButton("⚠️ Config Error")
    return ReplyKeyboardMarkup([
        [btn_app],
        [KeyboardButton("➕ Add Event"), KeyboardButton("🗑 Delete Event")],
        [KeyboardButton("📞 Support")]
    ], resize_keyboard=True, is_persistent=True)

# ------------------ STATES ------------------
GET_TITLE, GET_DATE = range(2)
GET_SUPPORT = 10

# ------------------ HANDLERS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not check_rate(uid): return
    get_user_data(uid)
    await update.message.reply_text(
        "👋 **Welcome to Event Reminder Bot\\!**\n\n"
        "I help you track your deadlines.\n"
        "• Add Event: Supports Gregorian & Persian dates.\n"
        "• Mini App: Visual dashboard.\n\n"
        "👇 *Select an option below:*",
        reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Use the buttons below to navigate:\n"
        "Open app – Launch mini-app\n"
        "Add event – Create new event\n"
        "Delete event – Remove an event\n"
        "Support – Get help",
        reply_markup=main_kb(str(update.effective_user.id))
    )

# ---- ADD FLOW ----
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not check_rate(uid): return
    await update.message.reply_text(
        "📝 **Enter Event Name:**",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "❌ Cancel": return await cancel(update, context)
    if len(txt) > 50:
        await update.message.reply_text("⚠️ Name too long. Try again.")
        return GET_TITLE
    context.user_data["title"] = txt
    await update.message.reply_text(
        "📅 **Enter Date:**\n(e.g. `2026.12.30` or `1405.10.20`)",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    uid = str(update.effective_user.id)
    if txt == "❌ Cancel": return await cancel(update, context)
    dt = parse_date(txt)
    if dt:
        import uuid
        evt_id = f"evt_{uuid.uuid4().hex[:8]}"
        users_coll.update_one(
            {"_id": uid},
            {"$set": {f"targets.{evt_id}": {"title": context.user_data["title"], "date": dt, "type": "personal"}}},
            upsert=True
        )
        await update.message.reply_text(
            "✅ **Saved! Check the App.**",
            reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **Invalid Date!** Try again.", parse_mode=ParseMode.MARKDOWN)
        return GET_DATE

# ---- SUPPORT FLOW ----
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not check_rate(uid): return
    await update.message.reply_text(
        "💌 **Support**\nPlease write your message for the Admin:",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_SUPPORT

async def support_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    user = update.effective_user
    uid = str(user.id)
    if txt == "❌ Cancel": return await cancel(update, context)
    await update.message.reply_text(
        "✅ **Sent to Admin!**\nThank you for your feedback.",
        reply_markup=main_kb(uid), parse_mode=ParseMode.MARKDOWN
    )
    if ADMIN_ID:
        msg = f"📩 **New Message**\nFrom: {user.full_name} (`{user.id}`)\n\n{txt[:1000]}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
        except: pass
    return ConversationHandler.END

# ---- DELETE FLOW ----
async def delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not check_rate(uid): return
    data = get_user_data(uid)
    targets = data.get("targets", {})
    if not targets:
        await update.message.reply_text("📭 **List is empty.**", parse_mode=ParseMode.MARKDOWN)
        return
    kb = [
        [InlineKeyboardButton(f"❌ {v['title']} ({v['date']})", callback_data=f"del_{k}")]
        for k, v in targets.items()
    ]
    await update.message.reply_text(
        "🗑 **Tap to delete:**", reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN
    )

async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    key = query.data.replace("del_", "")
    users_coll.update_one({"_id": uid}, {"$unset": {f"targets.{key}": ""}})
    await query.answer("Deleted!")
    await query.delete_message()

# ---- CANCEL ----
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Action Canceled.",
        reply_markup=main_kb(str(update.effective_user.id))
    )
    return ConversationHandler.END

# ---- UNKNOWN / MEDIA ----
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please use the buttons below.",
        reply_markup=main_kb(str(update.effective_user.id))
    )

# ---- ERROR ----
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update %s caused error %s", update, context.error)

# ---- MAIN ----
def main():
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)
    app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()

    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Add Event$"), add_start)],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            GET_DATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)]
        },
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )
    conv_support = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📞 Support$"), support_start)],
        states={GET_SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive)]},
        fallbacks=[MessageHandler(filters.ALL, cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv_add)
    app.add_handler(conv_support)
    app.add_handler(MessageHandler(filters.Regex("^🗑 Delete Event$"), delete_trigger))
    app.add_handler(CallbackQueryHandler(delete_cb, pattern="^del_"))
    app.add_handler(MessageHandler(filters.ALL, unknown))
    app.add_error_handler(error_handler)

    logger.info("Bot started (Single-File V2)")
    app.run_polling()

if __name__ == "__main__":
    main()