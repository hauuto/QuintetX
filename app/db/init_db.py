from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.security import hash_password
from app.db.client import get_database
from app.db.validators import (
    GROUPS_SCHEMA_VALIDATOR,
    MATCHES_SCHEMA_VALIDATOR,
    NOTIFICATIONS_SCHEMA_VALIDATOR,
    USERS_SCHEMA_VALIDATOR,
)

USERS_COLLECTION = "users"
GROUPS_COLLECTION = "groups"
MATCHES_COLLECTION = "matches"
NOTIFICATIONS_COLLECTION = "notifications"

SEED_ROOM_NAME = "Test"
SEED_USER_MSSV_LIST = ["23012345", "23012346", "23012347"]
SEED_GROUP_CODE_LIST = ["GRP-A3F9", "GRP-B7K2"]

GROUP_ONE_ID = "T0001padjsl92"
GROUP_TWO_ID = "T0002p24jslp2"

SEED_USERS = [
    {
        "_id": "U23012345",
        "mssv": "23012345",
        "full_name": "Nguyen Van A",
        "class_name": "D21CQCN01-N",
        "password_hash": hash_password("SeedPass123"),
        "role": "student",
        "group_id": GROUP_ONE_ID,
        "is_active": True,
    },
    {
        "_id": "U23012346",
        "mssv": "23012346",
        "full_name": "Tran Thi B",
        "class_name": "D21CQCN01-N",
        "password_hash": hash_password("SeedPass123"),
        "role": "student",
        "group_id": GROUP_ONE_ID,
        "is_active": True,
    },
    {
        "_id": "U23012347",
        "mssv": "23012347",
        "full_name": "Le Van C",
        "class_name": "D21CQCN02-N",
        "password_hash": hash_password("SeedPass123"),
        "role": "student",
        "group_id": GROUP_TWO_ID,
        "is_active": True,
    },
]

SEED_GROUPS = [
    {
        "_id": GROUP_ONE_ID,
        "group_code": "GRP-A3F9",
        "name": "Team Alpha",
        "description": "Seed team with 2 members",
        "avatar_url": None,
        "is_public": True,
        "leader_id": "U23012345",
        "members": [
            {
                "user_id": "U23012345",
                "mssv": "23012345",
                "full_name": "Nguyen Van A",
            },
            {
                "user_id": "U23012346",
                "mssv": "23012346",
                "full_name": "Tran Thi B",
            },
        ],
        "pending_requests": [],
        "match_history": [],
        "stats": {"total": 0, "wins": 0, "losses": 0, "draws": 0},
    },
    {
        "_id": GROUP_TWO_ID,
        "group_code": "GRP-B7K2",
        "name": "Team Beta",
        "description": "Seed team with 1 member",
        "avatar_url": None,
        "is_public": True,
        "leader_id": "U23012347",
        "members": [
            {
                "user_id": "U23012347",
                "mssv": "23012347",
                "full_name": "Le Van C",
            }
        ],
        "pending_requests": [],
        "match_history": [],
        "stats": {"total": 0, "wins": 0, "losses": 0, "draws": 0},
    },
]


async def initialize_local_database() -> None:
    database = get_database()

    await _ensure_collections(database)
    await _apply_collection_validators(database)
    await _ensure_indexes(database)

    if not settings.AUTO_SEED_ON_STARTUP:
        return

    env_name = (settings.APP_ENV or "dev").strip().lower()
    if env_name == "prod":
        await _seed_initial_admin(database)
        return

    await _seed_local_data(database)
    await _seed_initial_admin(database)


async def _ensure_collections(database: Any) -> None:
    existing_collections = set(await database.list_collection_names())

    if USERS_COLLECTION not in existing_collections:
        await database.create_collection(USERS_COLLECTION, validator=USERS_SCHEMA_VALIDATOR)
    if GROUPS_COLLECTION not in existing_collections:
        await database.create_collection(GROUPS_COLLECTION, validator=GROUPS_SCHEMA_VALIDATOR)
    if MATCHES_COLLECTION not in existing_collections:
        await database.create_collection(MATCHES_COLLECTION, validator=MATCHES_SCHEMA_VALIDATOR)
    if NOTIFICATIONS_COLLECTION not in existing_collections:
        await database.create_collection(
            NOTIFICATIONS_COLLECTION,
            validator=NOTIFICATIONS_SCHEMA_VALIDATOR,
        )


async def _apply_collection_validators(database: Any) -> None:
    await database.command(
        "collMod",
        USERS_COLLECTION,
        validator=USERS_SCHEMA_VALIDATOR,
        validationLevel="moderate",
    )
    await database.command(
        "collMod",
        GROUPS_COLLECTION,
        validator=GROUPS_SCHEMA_VALIDATOR,
        validationLevel="moderate",
    )
    await database.command(
        "collMod",
        MATCHES_COLLECTION,
        validator=MATCHES_SCHEMA_VALIDATOR,
        validationLevel="moderate",
    )
    await database.command(
        "collMod",
        NOTIFICATIONS_COLLECTION,
        validator=NOTIFICATIONS_SCHEMA_VALIDATOR,
        validationLevel="moderate",
    )


async def _ensure_indexes(database: Any) -> None:
    await database[USERS_COLLECTION].create_index(
        [("mssv", 1)],
        name="uq_users_mssv",
        unique=True,
    )

    await database[GROUPS_COLLECTION].create_index(
        [("group_code", 1)],
        name="uq_groups_group_code",
        unique=True,
    )

    # room_name is NOT unique (duplicate room names are allowed).
    # Best-effort drop of legacy unique index if it exists.
    try:
        await database[MATCHES_COLLECTION].drop_index("uq_matches_room_name")
    except Exception:
        pass

    await database[MATCHES_COLLECTION].create_index(
        [("room_name", 1)],
        name="idx_matches_room_name",
    )

    await database[MATCHES_COLLECTION].create_index(
        [("teams.X.team_id", 1)],
        name="uq_active_team_x",
        unique=True,
        partialFilterExpression={"status": {"$in": ["waiting", "playing"]}},
    )

    await database[MATCHES_COLLECTION].create_index(
        [("teams.O.team_id", 1)],
        name="uq_active_team_o",
        unique=True,
        partialFilterExpression={"status": {"$in": ["waiting", "playing"]}},
    )

    await database[NOTIFICATIONS_COLLECTION].create_index(
        [("user_id", 1), ("is_read", 1), ("created_at", -1)],
        name="idx_notifications_user_read_created",
    )

    await database[NOTIFICATIONS_COLLECTION].create_index(
        [("status", 1), ("type", 1)],
        name="idx_notifications_status_type",
    )


async def _seed_local_data(database: Any) -> None:
    now = datetime.now(timezone.utc)

    # Keep timestamps explicit UTC for reproducibility.
    for user in SEED_USERS:
        await database[USERS_COLLECTION].update_one(
            {"mssv": user["mssv"]},
            {"$setOnInsert": {**user, "created_at": now}},
            upsert=True,
        )

    for group in SEED_GROUPS:
        group_doc = {
            **group,
            "members": [
                {**member, "joined_at": now} for member in group["members"]
            ],
            "created_at": now,
        }
        await database[GROUPS_COLLECTION].update_one(
            {"group_code": group["group_code"]},
            {"$setOnInsert": group_doc},
            upsert=True,
        )

    # Explicitly keep local seed with zero matches.
    await database[MATCHES_COLLECTION].delete_many({"room_name": SEED_ROOM_NAME})


async def _seed_initial_admin(database: Any) -> None:
    now = datetime.now(timezone.utc)
    admin_doc = {
        "_id": "A0001",
        "mssv": settings.INITIAL_ADMIN_MSSV,
        "full_name": settings.INITIAL_ADMIN_FULL_NAME,
        "class_name": "ADMIN",
        "username": settings.INITIAL_ADMIN_USERNAME,
        "email": settings.INITIAL_ADMIN_EMAIL,
        "password_hash": hash_password(settings.INITIAL_ADMIN_PASSWORD),
        "role": "admin",
        "group_id": None,
        "is_active": True,
        "created_at": now,
    }

    await database[USERS_COLLECTION].update_one(
        {"_id": admin_doc["_id"]},
        {"$setOnInsert": admin_doc},
        upsert=True,
    )
