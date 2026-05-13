from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core import config as config_module
from app.core.security import hash_password
from app.db import client as db_client
from app.db import init_db as init_db_module
from app.db.init_db import (
    GROUPS_COLLECTION,
    MATCHES_COLLECTION,
    NOTIFICATIONS_COLLECTION,
    USERS_COLLECTION,
)
from main import app


@pytest.fixture(autouse=True)
async def test_database():
    settings = config_module.settings
    original_database_name = settings.DATABASE_NAME
    original_seed = settings.AUTO_SEED_ON_STARTUP
    original_client = db_client._mongo_client
    original_database = db_client._database

    settings.DATABASE_NAME = "quintetx_test"
    settings.AUTO_SEED_ON_STARTUP = False
    mock_client = AsyncMongoMockClient()
    database = mock_client[settings.DATABASE_NAME]
    db_client._mongo_client = mock_client
    db_client._database = database

    for collection_name in (USERS_COLLECTION, GROUPS_COLLECTION, MATCHES_COLLECTION, NOTIFICATIONS_COLLECTION):
        await database.create_collection(collection_name)
    await init_db_module._ensure_indexes(database)
    yield database

    await mock_client.drop_database(settings.DATABASE_NAME)
    db_client._mongo_client = original_client
    db_client._database = original_database
    settings.DATABASE_NAME = original_database_name
    settings.AUTO_SEED_ON_STARTUP = original_seed


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def db(test_database):
    return test_database


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def agent_headers(team_id: str, api_key: str) -> dict[str, str]:
    return {"X-Team-ID": team_id, "X-API-Key": api_key}


async def create_student(
    db: Any,
    *,
    mssv: str,
    password: str = "Pass1234",
    full_name: str | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    user = {
        "_id": f"U{mssv}",
        "mssv": mssv,
        "full_name": full_name or f"Student {mssv}",
        "class_name": "D21CQCN01-N",
        "password_hash": hash_password(password),
        "role": "student",
        "group_id": group_id,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    await db[USERS_COLLECTION].insert_one(user)
    return user


async def create_admin(db: Any, *, username: str = "admin", password: str = "admin") -> dict[str, Any]:
    user = {
        "_id": "A0001",
        "mssv": "00000000",
        "full_name": "System Admin",
        "class_name": "ADMIN",
        "username": username,
        "email": "admin@quintetx.local",
        "password_hash": hash_password(password),
        "role": "admin",
        "group_id": None,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    await db[USERS_COLLECTION].insert_one(user)
    return user


async def create_group(
    db: Any,
    *,
    group_id: str,
    leader: dict[str, Any],
    name: str = "Test Team",
    is_public: bool = True,
    members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    member_docs = members
    if member_docs is None:
        member_docs = [
            {
                "user_id": leader["_id"],
                "mssv": leader["mssv"],
                "full_name": leader["full_name"],
                "joined_at": now,
            }
        ]
    group = {
        "_id": group_id,
        "group_code": f"GRP-{group_id[-4:].upper()}",
        "name": name,
        "description": "Test group",
        "avatar_url": None,
        "is_public": is_public,
        "leader_id": leader["_id"],
        "members": member_docs,
        "pending_requests": [],
        "match_history": [],
        "stats": {"total": 0, "wins": 0, "losses": 0, "draws": 0},
        "created_at": now,
    }
    await db[GROUPS_COLLECTION].insert_one(group)
    await db[USERS_COLLECTION].update_one({"_id": leader["_id"]}, {"$set": {"group_id": group_id}})
    return group


async def login_student(client: AsyncClient, mssv: str, password: str = "Pass1234") -> str:
    response = await client.post("/api/v1/auth/login/student", json={"mssv": mssv, "password": password})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    return payload["data"]["access_token"]


async def login_admin(client: AsyncClient, username: str = "admin", password: str = "admin") -> str:
    response = await client.post(
        "/api/v1/auth/login/admin",
        json={"username_or_email": username, "password": password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    return payload["data"]["access_token"]


async def create_match_via_api(
    client: AsyncClient,
    admin_token: str,
    *,
    x_team_id: str,
    o_team_id: str,
    room_name: str = "Test Match",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={
            "x_team_id": x_team_id,
            "o_team_id": o_team_id,
            "start_time": "2030-01-01T00:00:00Z",
            "room_name": room_name,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    return payload["data"]["match"]


@pytest.fixture
async def admin_token(client, db):
    await create_admin(db)
    return await login_admin(client)


@pytest.fixture
async def two_group_match(client, db, admin_token):
    leader_x = await create_student(db, mssv="24000001")
    leader_o = await create_student(db, mssv="24000002")
    group_x = await create_group(db, group_id="T1001TEAMX", leader=leader_x, name="Team X")
    group_o = await create_group(db, group_id="T1002TEAMO", leader=leader_o, name="Team O")
    match = await create_match_via_api(
        client,
        admin_token,
        x_team_id=group_x["_id"],
        o_team_id=group_o["_id"],
    )
    return {"match": match, "group_x": group_x, "group_o": group_o}
