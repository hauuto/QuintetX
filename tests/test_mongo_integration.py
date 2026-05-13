from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from app.core import config as config_module
from app.core.security import hash_password
from app.db import client as db_client
from app.db.init_db import GROUPS_COLLECTION, MATCHES_COLLECTION, USERS_COLLECTION, initialize_local_database

pytestmark = [pytest.mark.asyncio, pytest.mark.mongo]


@pytest.fixture
async def real_mongo_db():
    uri = os.environ.get("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI not set; start docker-compose.test.yml mongo-test")

    settings = config_module.settings
    original_uri = settings.MONGODB_URI
    original_db = settings.DATABASE_NAME
    original_seed = settings.AUTO_SEED_ON_STARTUP
    original_client = db_client._mongo_client
    original_database = db_client._database

    settings.MONGODB_URI = uri
    settings.DATABASE_NAME = "quintetx_real_test"
    settings.AUTO_SEED_ON_STARTUP = False
    db_client._mongo_client = None
    db_client._database = None

    direct_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
    await direct_client.drop_database(settings.DATABASE_NAME)
    direct_client.close()

    database = await db_client.connect_db()
    await initialize_local_database()
    yield database

    await database.client.drop_database(settings.DATABASE_NAME)
    await db_client.close_db()
    settings.MONGODB_URI = original_uri
    settings.DATABASE_NAME = original_db
    settings.AUTO_SEED_ON_STARTUP = original_seed
    db_client._mongo_client = original_client
    db_client._database = original_database


async def test_real_mongo_initializes_collections_validators_and_indexes(real_mongo_db):
    names = set(await real_mongo_db.list_collection_names())
    assert {USERS_COLLECTION, GROUPS_COLLECTION, MATCHES_COLLECTION, "notifications"}.issubset(names)

    user_indexes = await real_mongo_db[USERS_COLLECTION].index_information()
    group_indexes = await real_mongo_db[GROUPS_COLLECTION].index_information()
    match_indexes = await real_mongo_db[MATCHES_COLLECTION].index_information()
    assert "uq_users_mssv" in user_indexes
    assert "uq_groups_group_code" in group_indexes
    assert "idx_matches_room_name" in match_indexes
    assert "uq_active_team_x" in match_indexes


async def test_real_mongo_unique_mssv_and_duplicate_room_names(real_mongo_db):
    now = datetime.now(timezone.utc)
    user = {
        "_id": "U27000001",
        "mssv": "27000001",
        "full_name": "Real Mongo User",
        "class_name": "D21",
        "password_hash": hash_password("Pass1234"),
        "role": "student",
        "group_id": None,
        "is_active": True,
        "created_at": now,
    }
    await real_mongo_db[USERS_COLLECTION].insert_one(user)
    with pytest.raises(DuplicateKeyError):
        await real_mongo_db[USERS_COLLECTION].insert_one({**user, "_id": "U27000002"})

    base_match = {
        "room_name": "Duplicate Room",
        "status": "finished",
        "rev": 0,
        "updated_at": now,
        "board": [[0 for _ in range(40)] for _ in range(40)],
        "teams": {
            "X": {"team_id": "TREALX1", "api_key": "x" * 32, "is_connected": False, "last_heartbeat": None},
            "O": {"team_id": "TREALO1", "api_key": "o" * 32, "is_connected": False, "last_heartbeat": None},
        },
        "current_turn": "X",
        "winner": None,
        "history": [],
        "events": [],
        "start_time": now,
        "started_at": None,
        "finished_at": now,
        "turn_deadline_at": None,
        "finish_reason": "draw",
        "created_at": now,
    }
    await real_mongo_db[MATCHES_COLLECTION].insert_one({**base_match, "_id": "MREAL0001"})
    await real_mongo_db[MATCHES_COLLECTION].insert_one({**base_match, "_id": "MREAL0002"})
    assert await real_mongo_db[MATCHES_COLLECTION].count_documents({"room_name": "Duplicate Room"}) == 2
