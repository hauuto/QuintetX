from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.client import get_database

USERS_COLLECTION = "users"
GROUPS_COLLECTION = "groups"
MATCHES_COLLECTION = "matches"

GROUP_ONE_ID = "group-seed-t001"
GROUP_TWO_ID = "group-seed-t002"

GROUP_ONE_TEAM_ID = "T001padjsl92"
GROUP_TWO_TEAM_ID = "T002p24jslp2"

SEED_USERS = [
    {
        "_id": "user-seed-001",
        "mssv": "SV000001",
        "full_name": "Nguyen Van A",
        "password_hash": "seed_password_hash",
        "role": "student",
        "group_id": GROUP_ONE_ID,
    },
    {
        "_id": "user-seed-002",
        "mssv": "SV000002",
        "full_name": "Tran Thi B",
        "password_hash": "seed_password_hash",
        "role": "student",
        "group_id": GROUP_ONE_ID,
    },
    {
        "_id": "user-seed-003",
        "mssv": "SV000003",
        "full_name": "Le Van C",
        "password_hash": "seed_password_hash",
        "role": "student",
        "group_id": GROUP_TWO_ID,
    },
]

SEED_GROUPS = [
    {
        "_id": GROUP_ONE_ID,
        "group_code": "GRP-T001",
        "team_id": GROUP_ONE_TEAM_ID,
        "name": "Team T001",
        "description": "Seed team with 2 members",
        "avatar_url": None,
        "is_public": True,
        "leader_id": "user-seed-001",
        "members": [
            {
                "user_id": "user-seed-001",
                "mssv": "SV000001",
                "full_name": "Nguyen Van A",
            },
            {
                "user_id": "user-seed-002",
                "mssv": "SV000002",
                "full_name": "Tran Thi B",
            },
        ],
        "pending_requests": [],
        "match_history": [],
        "stats": {"total": 0, "wins": 0, "losses": 0, "draws": 0},
    },
    {
        "_id": GROUP_TWO_ID,
        "group_code": "GRP-T002",
        "team_id": GROUP_TWO_TEAM_ID,
        "name": "Team T002",
        "description": "Seed team with 1 member",
        "avatar_url": None,
        "is_public": True,
        "leader_id": "user-seed-003",
        "members": [
            {
                "user_id": "user-seed-003",
                "mssv": "SV000003",
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
    await _ensure_indexes(database)
    await _seed_local_data(database)


async def _ensure_collections(database: Any) -> None:
    existing_collections = set(await database.list_collection_names())

    for name in (USERS_COLLECTION, GROUPS_COLLECTION, MATCHES_COLLECTION):
        if name not in existing_collections:
            await database.create_collection(name)


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

    await database[GROUPS_COLLECTION].create_index(
        [("team_id", 1)],
        name="uq_groups_team_id",
        unique=True,
    )

    await database[MATCHES_COLLECTION].create_index(
        [("room_name", 1)],
        name="uq_matches_room_name",
        unique=True,
    )


async def _seed_local_data(database: Any) -> None:
    now = datetime.now(timezone.utc)

    # Upsert keeps startup idempotent even if the service is restarted many times.
    for user in SEED_USERS:
        await database[USERS_COLLECTION].update_one(
            {"mssv": user["mssv"]},
            {
                "$setOnInsert": {
                    **user,
                    "created_at": now,
                }
            },
            upsert=True,
        )

    for group in SEED_GROUPS:
        await database[GROUPS_COLLECTION].update_one(
            {"group_code": group["group_code"]},
            {
                "$setOnInsert": {
                    **group,
                    "created_at": now,
                }
            },
            upsert=True,
        )

    # User requested local seed without matches.
