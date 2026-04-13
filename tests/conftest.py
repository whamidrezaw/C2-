from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient


os.environ["APP_ENV"] = "development"
os.environ["APP_DEBUG"] = "true"
os.environ["BOT_TOKEN"] = os.environ.get("BOT_TOKEN", "test_bot_token")
os.environ["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
os.environ["MONGO_DB_NAME"] = "time_manager_pro_test"  # همیشه override
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["TELEGRAM_INITDATA_MAX_AGE"] = "900"
os.environ["TELEGRAM_INITDATA_FUTURE_SKEW"] = "60"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client
