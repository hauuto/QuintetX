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


def _ensure_can_view_match(_: dict[str, Any], __: dict[str, Any]) -> bool:
    # Match viewing is read-only and safe (API keys are never returned in payload).
    # Allow any authenticated user to view matches for now.
    return True


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
    include_history: bool = True,
    include_events: bool = True,
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
        "finish_reason": match.get("finish_reason"),
        "rev": int(match.get("rev") or 0),
        "start_time": _to_iso(match.get("start_time")),
        "started_at": _to_iso(match.get("started_at")),
        "finished_at": _to_iso(match.get("finished_at")),
        "turn_deadline_at": _to_iso(match.get("turn_deadline_at")),
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
    }

    if include_history:
        payload["history"] = _normalize_history(match.get("history", []))
    else:
        payload["history"] = []

    if include_events:
        payload["events"] = [
            {
                "type": item.get("type"),
                "message": item.get("message"),
                "side": item.get("side"),
                "team_id": item.get("team_id"),
                "payload": item.get("payload") or {},
                "created_at": _to_iso(item.get("created_at")),
            }
            for item in match.get("events", [])[-100:]
        ]
    else:
        payload["events"] = []

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
    # Always create in "waiting". Match should start when both agents are ready.
    match_status = "waiting"
    room_name = (payload.room_name or "").strip() or f"{team_name_map.get(x_team_id, x_team_id)} vs {team_name_map.get(o_team_id, o_team_id)}"

    # Room names are allowed to be duplicated.

    match_id = await _generate_unique_match_id()
    x_api_key = _generate_api_key()
    o_api_key = _generate_api_key()

    match_doc = {
        "_id": match_id,
        "room_name": room_name,
        "status": match_status,
        "rev": 0,
        "updated_at": now,
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
        "events": [
            {
                "type": "match_created",
                "message": "Trận đấu đã được tạo.",
                "side": None,
                "team_id": None,
                "payload": {
                    "created_by": current_user.get("_id"),
                    "x_team_id": x_team_id,
                    "o_team_id": o_team_id,
                },
                "created_at": now,
            }
        ],
        "start_time": start_time,
        "started_at": None,
        "finished_at": None,
        "turn_deadline_at": None,
        "finish_reason": None,
        "created_at": now,
    }

    await database[MATCHES_COLLECTION].insert_one(match_doc)

    created_payload = _build_match_payload(
        match_doc,
        team_name_map,
        include_board=False,
        include_history=False,
        include_events=False,
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
            "rev": 1,
            "teams": 1,
            "started_at": 1,
            "finished_at": 1,
            "turn_deadline_at": 1,
            "finish_reason": 1,
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
        item = _build_match_payload(match, group_name_map, include_board=False, include_history=False, include_events=False)
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
        "status": {"$in": ["waiting", "playing", "finished"]},
        "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}],
    }
    my_match = await database[MATCHES_COLLECTION].find_one(
        my_match_query,
        sort=[("created_at", -1)],
    )

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
                "my_current_match": _build_match_payload(my_match, group_name_map, include_board=True, include_history=True, include_events=True),
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
            "rev": 1,
            "teams": 1,
            "started_at": 1,
            "finished_at": 1,
            "turn_deadline_at": 1,
            "finish_reason": 1,
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
        item = _build_match_payload(match, group_name_map, include_board=False, include_history=False, include_events=False)
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


@router.get("/me/summary")
async def get_my_match_summary(
    current_user: dict[str, Any] = Depends(get_current_user),
    since_rev: int | None = None,
):
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
                "rev_changed": False,
            },
            "message": "",
        }

    my_match_query = {
        "status": {"$in": ["waiting", "playing", "finished"]},
        "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}],
    }

    projection = {
        "_id": 1,
        "room_name": 1,
        "status": 1,
        "current_turn": 1,
        "winner": 1,
        "finish_reason": 1,
        "started_at": 1,
        "finished_at": 1,
        "turn_deadline_at": 1,
        "created_at": 1,
        "rev": 1,
        "teams": 1,
    }

    my_match = await database[MATCHES_COLLECTION].find_one(
        my_match_query,
        projection,
        sort=[("created_at", -1)],
    )

    if not my_match:
        return {
            "status": "success",
            "data": {
                "my_current_match": None,
                "my_team": {"id": group_id},
                "other_matches": {
                    "current_matches": [],
                    "upcoming_matches": [],
                    "finished_matches": [],
                },
                "rev_changed": False,
            },
            "message": "",
        }

    teams = my_match.get("teams", {})
    my_side = "X" if teams.get("X", {}).get("team_id") == group_id else "O"

    rev_value = int(my_match.get("rev") or 0)
    rev_changed = True
    if since_rev is not None:
        try:
            rev_changed = int(since_rev) != rev_value
        except Exception:
            rev_changed = True

    summary_match = {
        "id": my_match.get("_id"),
        "room_name": my_match.get("room_name"),
        "status": my_match.get("status"),
        "current_turn": my_match.get("current_turn"),
        "winner": my_match.get("winner"),
        "finish_reason": my_match.get("finish_reason"),
        "started_at": _to_iso(my_match.get("started_at")),
        "finished_at": _to_iso(my_match.get("finished_at")),
        "turn_deadline_at": _to_iso(my_match.get("turn_deadline_at")),
        "created_at": _to_iso(my_match.get("created_at")),
        "rev": rev_value,
        "teams": {
            "X": {
                "team_id": teams.get("X", {}).get("team_id"),
                "is_connected": bool(teams.get("X", {}).get("is_connected", False)),
                "last_heartbeat": _to_iso(teams.get("X", {}).get("last_heartbeat")),
            },
            "O": {
                "team_id": teams.get("O", {}).get("team_id"),
                "is_connected": bool(teams.get("O", {}).get("is_connected", False)),
                "last_heartbeat": _to_iso(teams.get("O", {}).get("last_heartbeat")),
            },
        },
    }

    return {
        "status": "success",
        "data": {
            "my_current_match": summary_match,
            "my_team": {"id": group_id, "side": my_side},
            "other_matches": {
                "current_matches": [],
                "upcoming_matches": [],
                "finished_matches": [],
            },
            "rev_changed": rev_changed,
        },
        "message": "",
    }


@router.get("/{match_id}/events")
async def get_match_events(
    match_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = 100,
):
    del current_user
    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id}, {"events": 1})

    if not match:
        return {"status": "error", "data": {}, "message": "Match not found"}

    raw_events = match.get("events", [])
    events = [
        {
            "type": item.get("type"),
            "message": item.get("message"),
            "side": item.get("side"),
            "team_id": item.get("team_id"),
            "payload": item.get("payload") or {},
            "created_at": _to_iso(item.get("created_at")),
        }
        for item in raw_events[-max(1, min(limit, 300)):]
    ]

    return {
        "status": "success",
        "data": {"events": events},
        "message": "",
    }


@router.get("/my/history")
async def list_my_finished_matches(
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = 50,
):
    database = get_database()
    group_id = current_user.get("group_id")
    capped = max(1, min(int(limit or 50), 200))

    if not group_id:
        return {"status": "success", "data": {"matches": []}, "message": ""}

    pipeline = [
        {
            "$match": {
                "status": "finished",
                "$or": [
                    {"teams.X.team_id": group_id},
                    {"teams.O.team_id": group_id},
                ],
            }
        },
        {"$sort": {"finished_at": -1, "created_at": -1}},
        {
            "$project": {
                "_id": 1,
                "room_name": 1,
                "status": 1,
                "winner": 1,
                "finish_reason": 1,
                "start_time": 1,
                "started_at": 1,
                "finished_at": 1,
                "created_at": 1,
                "teams": 1,
                "rev": 1,
                "move_count": {"$size": {"$ifNull": ["$history", []]}},
            }
        },
        {"$limit": capped},
    ]

    raw = await database[MATCHES_COLLECTION].aggregate(pipeline).to_list(length=capped)

    team_ids: set[str] = set()
    for match in raw:
        teams = match.get("teams", {})
        team_ids.add(teams.get("X", {}).get("team_id", ""))
        team_ids.add(teams.get("O", {}).get("team_id", ""))
    team_ids.discard("")
    group_name_map = await _load_group_name_map(team_ids)

    matches: list[dict[str, Any]] = []
    for match in raw:
        teams = match.get("teams", {})
        x_id = teams.get("X", {}).get("team_id")
        o_id = teams.get("O", {}).get("team_id")

        matches.append(
            {
                "id": match.get("_id"),
                "room_name": match.get("room_name"),
                "status": match.get("status"),
                "winner": match.get("winner"),
                "finish_reason": match.get("finish_reason"),
                "start_time": _to_iso(match.get("start_time")),
                "started_at": _to_iso(match.get("started_at")),
                "finished_at": _to_iso(match.get("finished_at")),
                "created_at": _to_iso(match.get("created_at")),
                "rev": int(match.get("rev") or 0),
                "move_count": int(match.get("move_count") or 0),
                "teams": {
                    "X": {
                        "team_id": x_id,
                        "name": group_name_map.get(x_id, x_id),
                    },
                    "O": {
                        "team_id": o_id,
                        "name": group_name_map.get(o_id, o_id),
                    },
                },
                "my_side": "X" if x_id == group_id else "O",
            }
        )

    return {"status": "success", "data": {"matches": matches}, "message": ""}


@router.get("/{match_id}")
async def get_match_by_id(match_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    if not match:
        return {"status": "error", "data": {}, "message": "Match not found"}

    if not _ensure_can_view_match(current_user, match):
        return {"status": "error", "data": {}, "message": "Forbidden"}

    teams = match.get("teams", {})
    team_ids = {
        teams.get("X", {}).get("team_id", ""),
        teams.get("O", {}).get("team_id", ""),
    }
    team_ids.discard("")
    group_name_map = await _load_group_name_map(team_ids)

    return {
        "status": "success",
        "data": {
            "match": _build_match_payload(match, group_name_map, include_board=True, include_history=True, include_events=True),
        },
        "message": "",
    }