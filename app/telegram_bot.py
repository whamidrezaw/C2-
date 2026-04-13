from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import get_settings


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    webapp_url = f"{settings.app_base_url}/webapp"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("باز کردن برنامه", web_app=WebAppInfo(url=webapp_url))]]
    )

    text = (
        "سلام.\n"
        "برای مدیریت رویدادها روی دکمه زیر بزن."
    )

    if update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "/start - باز کردن برنامه\n"
            "/ping - تست زنده بودن ربات"
        )


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("ربات فعال است.")


def build_telegram_application() -> Application:
    settings = get_settings()

    application = (
        Application.builder()
        .token(settings.bot_token)
        .updater(None)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))

    return application
