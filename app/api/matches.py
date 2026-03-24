from __future__ import annotations

from datetime import datetime, timezone
import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import GROUPS_COLLECTION, MATCHES_COLLECTION

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])

ACTIVE_MATCH_STATUSES = ["waiting", "playing"]
DEFAULT_API_KEY_LENGTH = 32


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _create_board() -> list[list[int]]:
    return [[0 for _ in range(settings.BOARD_SIZE)] for _ in range(settings.BOARD_SIZE)]


def _generate_api_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(DEFAULT_API_KEY_LENGTH))


def _generate_match_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    numeric = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"M{numeric}{suffix}"


async def _generate_unique_match_id() -> str:
    database = get_database()
    for _ in range(50):
        candidate = _generate_match_id()
        exists = await database[MATCHES_COLLECTION].find_one({"_id": candidate}, {"_id": 1})
        if not exists:
            return candidate
    raise RuntimeError("Cannot generate unique match id")


def _normalize_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, move in enumerate(history or [], start=1):
        normalized.append(
            {
                "order": idx,
                "x": move.get("x"),
                "y": move.get("y"),
                "team": move.get("p"),
                "coord": f"({move.get('x')}, {move.get('y')})",
                "played_at": _to_iso(move.get("t")),
            }
        )
    return normalized


def _build_match_payload(
    match: dict[str, Any],
    group_name_map: dict[str, str],
    *,
    include_board: bool,
) -> dict[str, Any]:
    teams = match.get("teams", {})
    team_x = teams.get("X", {})
    team_o = teams.get("O", {})
    x_team_id = team_x.get("team_id", "")
    o_team_id = team_o.get("team_id", "")

    payload = {
        "id": match.get("_id"),
        "room_name": match.get("room_name"),
        "status": match.get("status"),
        "current_turn": match.get("current_turn"),
        "winner": match.get("winner"),
        "start_time": _to_iso(match.get("start_time")),
        "created_at": _to_iso(match.get("created_at")),
        "teams": {
            "X": {
                "team_id": x_team_id,
                "name": group_name_map.get(x_team_id, x_team_id),
                "is_connected": bool(team_x.get("is_connected", False)),
                "last_heartbeat": _to_iso(team_x.get("last_heartbeat")),
            },
            "O": {
                "team_id": o_team_id,
                "name": group_name_map.get(o_team_id, o_team_id),
                "is_connected": bool(team_o.get("is_connected", False)),
                "last_heartbeat": _to_iso(team_o.get("last_heartbeat")),
            },
        },
        "history": _normalize_history(match.get("history", [])),
    }

    if include_board:
        payload["board"] = match.get("board", _create_board())

    return payload


async def _load_group_name_map(team_ids: set[str]) -> dict[str, str]:
    if not team_ids:
        return {}

    database = get_database()
    group_name_map: dict[str, str] = {}
    async for group in database[GROUPS_COLLECTION].find(
        {"_id": {"$in": list(team_ids)}},
        {"_id": 1, "name": 1},
    ):
        group_name_map[group.get("_id")] = group.get("name", "")
    return group_name_map


def _ensure_admin(current_user: dict[str, Any]) -> bool:
    return current_user.get("role") == "admin"


class CreateMatchRequest(BaseModel):
    x_team_id: str = Field(min_length=1)
    o_team_id: str = Field(min_length=1)
    start_time: str = Field(min_length=1)
    room_name: str | None = Field(default=None, max_length=200)


@router.get("/teams/options")
async def list_team_options(current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_admin(current_user):
        return {"status": "error", "data": {}, "message": "Only admin can access team options"}

    database = get_database()
    groups = await database[GROUPS_COLLECTION].find(
        {},
        {
            "_id": 1,
            "group_code": 1,
            "name": 1,
        },
    ).sort("created_at", -1).to_list(length=500)

    teams = [
        {
            "id": group.get("_id"),
            "group_code": group.get("group_code"),
            "name": group.get("name"),
        }
        for group in groups
    ]

    return {
        "status": "success",
        "data": {"teams": teams},
        "message": "",
    }


@router.post("")
async def create_match(payload: CreateMatchRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_admin(current_user):
        return {"status": "error", "data": {}, "message": "Only admin can create matches"}

    x_team_id = payload.x_team_id.strip()
    o_team_id = payload.o_team_id.strip()
    if not x_team_id or not o_team_id:
        return {"status": "error", "data": {}, "message": "Both team ids are required"}
    if x_team_id == o_team_id:
        return {"status": "error", "data": {}, "message": "Two sides must be different teams"}

    start_time = _parse_iso_datetime(payload.start_time)
    if not start_time:
        return {"status": "error", "data": {}, "message": "Invalid start_time. Use ISO 8601"}

    database = get_database()
    team_groups = await database[GROUPS_COLLECTION].find(
        {"_id": {"$in": [x_team_id, o_team_id]}},
        {"_id": 1, "name": 1},
    ).to_list(length=2)
    if len(team_groups) != 2:
        return {"status": "error", "data": {}, "message": "One or both teams do not exist"}

    team_name_map = {item.get("_id"): item.get("name", "") for item in team_groups}

    active_filter = {
        "status": {"$in": ACTIVE_MATCH_STATUSES},
        "$or": [
            {"teams.X.team_id": {"$in": [x_team_id, o_team_id]}},
            {"teams.O.team_id": {"$in": [x_team_id, o_team_id]}},
        ],
    }
    active_conflict = await database[MATCHES_COLLECTION].find_one(active_filter, {"_id": 1})
    if active_conflict:
        return {
            "status": "error",
            "data": {},
            "message": "One of the selected teams already has an active match",
        }

    now = _now_utc()
    match_status = "playing" if start_time <= now else "waiting"
    room_name = (payload.room_name or "").strip() or f"{team_name_map.get(x_team_id, x_team_id)} vs {team_name_map.get(o_team_id, o_team_id)}"

    duplicated_room = await database[MATCHES_COLLECTION].find_one({"room_name": room_name}, {"_id": 1})
    if duplicated_room:
        return {
            "status": "error",
            "data": {},
            "message": "Room name already exists",
        }

    match_id = await _generate_unique_match_id()
    x_api_key = _generate_api_key()
    o_api_key = _generate_api_key()

    match_doc = {
        "_id": match_id,
        "room_name": room_name,
        "status": match_status,
        "board": _create_board(),
        "teams": {
            "X": {
                "team_id": x_team_id,
                "api_key": x_api_key,
                "is_connected": False,
                "last_heartbeat": None,
            },
            "O": {
                "team_id": o_team_id,
                "api_key": o_api_key,
                "is_connected": False,
                "last_heartbeat": None,
            },
        },
        "current_turn": "X",
        "winner": None,
        "history": [],
        "start_time": start_time,
        "created_at": now,
    }

    await database[MATCHES_COLLECTION].insert_one(match_doc)

    created_payload = _build_match_payload(
        match_doc,
        team_name_map,
        include_board=False,
    )
    created_payload["teams"]["X"]["api_key"] = x_api_key
    created_payload["teams"]["O"]["api_key"] = o_api_key

    return {
        "status": "success",
        "data": {"match": created_payload},
        "message": "",
    }


@router.get("/overview")
async def list_matches_overview(current_user: dict[str, Any] = Depends(get_current_user)):
    del current_user
    database = get_database()

    matches = await database[MATCHES_COLLECTION].find(
        {},
        {
            "_id": 1,
            "room_name": 1,
            "status": 1,
            "current_turn": 1,
            "winner": 1,
            "start_time": 1,
            "created_at": 1,
            "teams": 1,
            "history": 1,
        },
    ).sort("start_time", -1).to_list(length=300)

    team_ids: set[str] = set()
    for match in matches:
        teams = match.get("teams", {})
        team_ids.add(teams.get("X", {}).get("team_id", ""))
        team_ids.add(teams.get("O", {}).get("team_id", ""))
    team_ids.discard("")

    group_name_map = await _load_group_name_map(team_ids)

    current_matches: list[dict[str, Any]] = []
    upcoming_matches: list[dict[str, Any]] = []
    finished_matches: list[dict[str, Any]] = []

    for match in matches:
        item = _build_match_payload(match, group_name_map, include_board=False)
        status = item.get("status")
        if status == "playing":
            current_matches.append(item)
        elif status == "waiting":
            upcoming_matches.append(item)
        else:
            finished_matches.append(item)

    return {
        "status": "success",
        "data": {
            "current_matches": current_matches,
            "upcoming_matches": upcoming_matches,
            "finished_matches": finished_matches,
        },
        "message": "",
    }


@router.get("/me")
async def get_my_match(current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    group_id = current_user.get("group_id")

    if not group_id:
        overview = await list_matches_overview(current_user)
        return {
            "status": "success",
            "data": {
                "my_current_match": None,
                "my_team": None,
                "other_matches": overview.get("data", {}),
            },
            "message": "",
        }

    my_match_query = {
        "status": "playing",
        "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}],
    }
    my_match = await database[MATCHES_COLLECTION].find_one(my_match_query)

    if my_match:
        team_ids = {
            my_match.get("teams", {}).get("X", {}).get("team_id", ""),
            my_match.get("teams", {}).get("O", {}).get("team_id", ""),
        }
        team_ids.discard("")
        group_name_map = await _load_group_name_map(team_ids)

        my_side = "X" if my_match.get("teams", {}).get("X", {}).get("team_id") == group_id else "O"
        my_team = {
            "id": group_id,
            "side": my_side,
            "api_key": my_match.get("teams", {}).get(my_side, {}).get("api_key", ""),
        }

        return {
            "status": "success",
            "data": {
                "my_current_match": _build_match_payload(my_match, group_name_map, include_board=True),
                "my_team": my_team,
                "other_matches": {
                    "current_matches": [],
                    "upcoming_matches": [],
                    "finished_matches": [],
                },
            },
            "message": "",
        }

    all_matches = await database[MATCHES_COLLECTION].find(
        {
            "$and": [
                {"teams.X.team_id": {"$ne": group_id}},
                {"teams.O.team_id": {"$ne": group_id}},
            ]
        },
        {
            "_id": 1,
            "room_name": 1,
            "status": 1,
            "current_turn": 1,
            "winner": 1,
            "start_time": 1,
            "created_at": 1,
            "teams": 1,
            "history": 1,
        },
    ).sort("start_time", -1).to_list(length=300)

    team_ids: set[str] = set()
    for match in all_matches:
        teams = match.get("teams", {})
        team_ids.add(teams.get("X", {}).get("team_id", ""))
        team_ids.add(teams.get("O", {}).get("team_id", ""))
    team_ids.discard("")

    group_name_map = await _load_group_name_map(team_ids)

    current_matches: list[dict[str, Any]] = []
    upcoming_matches: list[dict[str, Any]] = []
    finished_matches: list[dict[str, Any]] = []
    for match in all_matches:
        item = _build_match_payload(match, group_name_map, include_board=False)
        status = item.get("status")
        if status == "playing":
            current_matches.append(item)
        elif status == "waiting":
            upcoming_matches.append(item)
        else:
            finished_matches.append(item)

    return {
        "status": "success",
        "data": {
            "my_current_match": None,
            "my_team": {"id": group_id},
            "other_matches": {
                "current_matches": current_matches,
                "upcoming_matches": upcoming_matches,
                "finished_matches": finished_matches,
            },
        },
        "message": "",
    }