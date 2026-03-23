from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

_mongo_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


def _build_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )


async def connect_db() -> AsyncIOMotorDatabase:
    global _mongo_client, _database

    if _mongo_client is not None and _database is not None:
        return _database

    _mongo_client = _build_client()
    _database = _mongo_client[settings.DATABASE_NAME]

    # Explicit ping ensures startup fails immediately if MongoDB is unavailable.
    await _mongo_client.admin.command("ping")

    return _database


def get_database() -> AsyncIOMotorDatabase:
    if _database is None:
        raise RuntimeError("Database client is not connected")
    return _database


async def close_db() -> None:
    global _mongo_client, _database

    if _mongo_client is not None:
        _mongo_client.close()

    _mongo_client = None
    _database = None
