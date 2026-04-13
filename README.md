# TimeManager Pro

TimeManager Pro is a Telegram Mini App for managing personal events and reminders with both Gregorian and Jalali dates.

## Features

- Create, edit, delete personal events
- Gregorian and Jalali date support
- Repeating reminders: daily, weekly, monthly, yearly
- Pin important events
- Add notes to events
- Telegram bot reminder delivery
- Mobile-first Telegram Mini App UI
- Light/Dark mode support

## Tech Stack

- Python 3.12+
- FastAPI
- Gunicorn + Uvicorn
- MongoDB
- python-telegram-bot / telegram Bot API
- Jinja2
- Vanilla JS frontend
- CSS custom properties theme system

## Project Structure

```text
app/
  main.py          # FastAPI app entrypoint
  config.py        # environment-based settings
  db.py            # Mongo connection and collections
  deps.py          # shared FastAPI dependencies
  routes/          # route modules
  schemas/         # request/response models
  services/        # business logic
  utils/           # utilities

worker/
  reminder_worker.py   # reminder processing worker
```

## Requirements

- Python 3.12+
- MongoDB connection string
- Telegram Bot Token
- Public HTTPS deployment for Telegram Mini App usage

## Environment Variables

Copy `.env.example` to `.env` and fill values:

```bash
cp .env.example .env
```

Required variables:

- `BOT_TOKEN`
- `MONGO_URI`

Recommended variables:

- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `WEBAPP_BASE_URL`
- `AUTH_EXPIRE_SECS`
- `RATE_LIMIT_COUNT`
- `REMINDER_BATCH_SIZE`

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run in Development

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Run in Production

### Web process

```bash
gunicorn app.main:app \
  -w 1 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT:-8000} \
  --log-level info \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --access-logfile -
```

### Worker process

```bash
python -m worker.reminder_worker
```

## Notes

- The reminder worker must run as a separate process.
- Do not scale web workers above `1` until the worker has been fully separated from the app lifecycle.
- Telegram Mini App requests must always be validated server-side using raw `initData`.

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

## Basic Development Plan

1. Finalize modular backend structure
2. Split reminder worker from web process
3. Add Pydantic request/response schemas
4. Add tests for auth, dates, recurrence, and CRUD
5. Improve frontend localization and accessibility
6. Add deployment and recovery documentation

## Security Notes

- Never commit `.env`
- Never trust user identity from frontend without validating Telegram `initData`
- Never log bot token or raw secrets
- Run MongoDB backups regularly
- Restrict public operational endpoints where possible