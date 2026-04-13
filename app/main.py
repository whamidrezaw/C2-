from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update
from pymongo import ReturnDocument

from app.config import get_settings
from app.services.auth import get_authenticated_user_id
from app.telegram_bot import build_telegram_application

logger = logging.getLogger("tm_pro")
logging.basicConfig(level=logging.INFO)

settings = get_settings()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def clean_event(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "date_iso": doc.get("date_iso", ""),
        "date_jalali": doc.get("date_jalali", ""),
        "repeat": doc.get("repeat", "none"),
        "category": doc.get("category", "general"),
        "pinned": bool(doc.get("pinned", False)),
        "note": doc.get("note", ""),
        "notify_status": doc.get("notify_status", "pending"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo[settings.mongodb_db_name]
    events = db["events"]

    await events.create_index([("user_id", 1), ("pinned", -1), ("date_iso", 1)])
    await events.create_index([("user_id", 1), ("updated_at", -1)])

    telegram_app = build_telegram_application()
    await telegram_app.initialize()
    await telegram_app.start()

    await telegram_app.bot.set_webhook(
        url=f"{settings.app_base_url}/telegram/webhook",
        secret_token=settings.telegram_webhook_secret,
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )

    app.state.mongo = mongo
    app.state.db = db
    app.state.events = events
    app.state.telegram_app = telegram_app

    logger.info("Application started")

    try:
        yield
    finally:
        try:
            await telegram_app.bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Failed to delete webhook cleanly")
        await telegram_app.stop()
        await telegram_app.shutdown()
        mongo.close()
        logger.info("Application stopped")


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "tm_pro is running"


@app.get("/webapp", response_class=HTMLResponse)
async def webapp(request: Request):
    return templates.TemplateResponse("webapp.html", {"request": request})


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="INVALID_WEBHOOK_SECRET")

    data = await request.json()
    telegram_app = request.app.state.telegram_app
    await telegram_app.update_queue.put(
        Update.de_json(data=data, bot=telegram_app.bot)
    )
    return JSONResponse({"ok": True})


async def get_events_collection(request: Request):
    return request.app.state.events


async def parse_json(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="INVALID_JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="INVALID_PAYLOAD")

    return data


def require_event_id(payload: dict[str, Any]) -> str:
    event_id = str(payload.get("event_id", "")).strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="MISSING_EVENT_ID")
    return event_id


def validate_basic_event_fields(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    date_iso = str(payload.get("date", "")).strip()
    repeat = str(payload.get("repeat", "none")).strip() or "none"
    category = str(payload.get("category", "general")).strip() or "general"
    pinned = normalize_bool(payload.get("pinned", False))
    note = str(payload.get("note", "")).strip()

    if not title:
        raise HTTPException(status_code=400, detail="TITLE_REQUIRED")
    if len(title) > 200:
        raise HTTPException(status_code=400, detail="TITLE_TOO_LONG")
    if not date_iso:
        raise HTTPException(status_code=400, detail="DATE_REQUIRED")
    if len(note) > 2000:
        raise HTTPException(status_code=400, detail="NOTE_TOO_LONG")

    return {
        "title": title,
        "date_iso": date_iso,
        "date_jalali": str(payload.get("date_jalali", "")).strip(),
        "repeat": repeat,
        "category": category,
        "pinned": pinned,
        "note": note,
    }


@app.post("/api/list")
async def api_list(request: Request):
    user_id = await get_authenticated_user_id(request)
    events = await get_events_collection(request)

    docs = await events.find({"user_id": user_id}).sort(
        [("pinned", -1), ("date_iso", 1), ("_id", -1)]
    ).to_list(length=1000)

    return {
        "success": True,
        "targets": [clean_event(doc) for doc in docs],
    }


@app.post("/api/add")
async def api_add(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await parse_json(request)
    data = validate_basic_event_fields(payload)
    events = await get_events_collection(request)

    doc = {
        "user_id": user_id,
        "title": data["title"],
        "date_iso": data["date_iso"],
        "date_jalali": data["date_jalali"],
        "repeat": data["repeat"],
        "category": data["category"],
        "pinned": data["pinned"],
        "note": data["note"],
        "notify_status": "pending",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    result = await events.insert_one(doc)
    created = await events.find_one({"_id": result.inserted_id, "user_id": user_id})

    return {
        "success": True,
        "target": clean_event(created),
    }


@app.post("/api/edit")
async def api_edit(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await parse_json(request)
    event_id = require_event_id(payload)
    data = validate_basic_event_fields(payload)
    events = await get_events_collection(request)

    from bson import ObjectId

    updated = await events.find_one_and_update(
        {"_id": ObjectId(event_id), "user_id": user_id},
        {
            "$set": {
                "title": data["title"],
                "date_iso": data["date_iso"],
                "date_jalali": data["date_jalali"],
                "repeat": data["repeat"],
                "category": data["category"],
                "pinned": data["pinned"],
                "note": data["note"],
                "updated_at": utc_now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")

    return {
        "success": True,
        "target": clean_event(updated),
    }


@app.post("/api/delete")
async def api_delete(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await parse_json(request)
    event_id = require_event_id(payload)
    events = await get_events_collection(request)

    from bson import ObjectId

    result = await events.delete_one({"_id": ObjectId(event_id), "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")

    return {"success": True}


@app.post("/api/note")
async def api_note(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await parse_json(request)
    event_id = require_event_id(payload)
    note = str(payload.get("note", "")).strip()
    if len(note) > 2000:
        raise HTTPException(status_code=400, detail="NOTE_TOO_LONG")

    events = await get_events_collection(request)
    from bson import ObjectId

    updated = await events.find_one_and_update(
        {"_id": ObjectId(event_id), "user_id": user_id},
        {"$set": {"note": note, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")

    return {
        "success": True,
        "target": clean_event(updated),
    }


@app.post("/api/pin")
async def api_pin(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await parse_json(request)
    event_id = require_event_id(payload)
    pinned = normalize_bool(payload.get("pinned", False))

    events = await get_events_collection(request)
    from bson import ObjectId

    updated = await events.find_one_and_update(
        {"_id": ObjectId(event_id), "user_id": user_id},
        {"$set": {"pinned": pinned, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")

    return {
        "success": True,
        "target": clean_event(updated),
    }
