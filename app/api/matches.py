from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
import string
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import GROUPS_COLLECTION, MATCHES_COLLECTION
from app.services.match_engine import advance_match, apply_move, build_event, now_utc, surrender_match, to_iso as engine_to_iso

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])

ACTIVE_MATCH_STATUSES = ["waiting", "playing"]
DEFAULT_API_KEY_LENGTH = 32
GREEDY_BOT_TEAM_NAME = "Greedy Bot"


def _ensure_can_view_match(_: dict[str, Any], __: dict[str, Any]) -> bool:
    # Match viewing is read-only and safe (API keys are never returned in payload).
    # Allow any authenticated user to view matches for now.
    return True


def _now_utc() -> datetime:
    return now_utc()


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
    return engine_to_iso(value)


def _create_board() -> list[list[int]]:
    return [[0 for _ in range(settings.BOARD_SIZE)] for _ in range(settings.BOARD_SIZE)]


def _generate_api_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(DEFAULT_API_KEY_LENGTH))


def _generate_match_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    numeric = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"M{numeric}{suffix}"

def _generate_bot_team_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    return f"T9999{suffix}"


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
        "mode": match.get("mode") or ("pve_greedy" if any((match.get("teams", {}).get(side, {}).get("is_bot") or match.get("teams", {}).get(side, {}).get("kind") == "bot") for side in ("X", "O")) else "ai_vs_ai"),
        "current_turn": match.get("current_turn"),
        "winner": match.get("winner"),
        "finish_reason": match.get("finish_reason"),
        "winning_cells": match.get("winning_cells") or [],
        "rev": int(match.get("rev") or 0),
        "start_time": _to_iso(match.get("start_time")),
        "started_at": _to_iso(match.get("started_at")),
        "finished_at": _to_iso(match.get("finished_at")),
        "turn_deadline_at": _to_iso(match.get("turn_deadline_at")),
        "created_at": _to_iso(match.get("created_at")),
        "teams": {
            "X": {
                "team_id": x_team_id,
                "name": team_x.get("bot", {}).get("name") if team_x.get("is_bot") else group_name_map.get(x_team_id, x_team_id),
                "is_connected": bool(team_x.get("is_connected", False)),
                "last_heartbeat": _to_iso(team_x.get("last_heartbeat")),
                "is_bot": bool(team_x.get("is_bot", False)),
                "kind": team_x.get("kind") or ("bot" if team_x.get("is_bot") else "team"),
                "bot": team_x.get("bot"),
            },
            "O": {
                "team_id": o_team_id,
                "name": team_o.get("bot", {}).get("name") if team_o.get("is_bot") else ("Đang chờ đối thủ" if match.get("mode") == "player_room" and not team_o.get("is_connected") else group_name_map.get(o_team_id, o_team_id)),
                "is_connected": bool(team_o.get("is_connected", False)),
                "last_heartbeat": _to_iso(team_o.get("last_heartbeat")),
                "is_bot": bool(team_o.get("is_bot", False)),
                "kind": team_o.get("kind") or ("bot" if team_o.get("is_bot") else "team"),
                "bot": team_o.get("bot"),
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

    group_name_map: dict[str, str] = {}
    query_ids = list(team_ids)
    if not query_ids:
        return group_name_map

    database = get_database()
    async for group in database[GROUPS_COLLECTION].find(
        {"_id": {"$in": query_ids}},
        {"_id": 1, "name": 1},
    ):
        group_name_map[group.get("_id")] = group.get("name", "")
    return group_name_map


def _ensure_admin(current_user: dict[str, Any]) -> bool:
    return current_user.get("role") == "admin"


def _ensure_student(current_user: dict[str, Any]) -> bool:
    return current_user.get("role") == "student"


class CreateMatchRequest(BaseModel):
    x_team_id: str = Field(min_length=1)
    o_team_id: str = Field(min_length=1)
    start_time: str = Field(min_length=1)
    room_name: str | None = Field(default=None, max_length=200)


class CreateGreedyBotMatchRequest(BaseModel):
    room_name: str | None = Field(default=None, max_length=200)
    human_team_id: str | None = Field(default=None, min_length=1)
    human_side: Literal["X", "O"] = "X"


class HumanMoveRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    side: Literal["X", "O"] | None = None


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


@router.post("/bot")
async def create_match_with_greedy_bot(
    payload: CreateGreedyBotMatchRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    role = current_user.get("role")
    human_side = payload.human_side

    if role == "student":
        group_id = str(current_user.get("group_id") or "").strip()
        if not group_id:
            return {"status": "error", "data": {}, "message": "Bạn chưa thuộc nhóm nào. Hãy tham gia hoặc tạo nhóm trước."}
    elif role == "admin":
        group_id = str(payload.human_team_id or "").strip()
        if not group_id:
            return {"status": "error", "data": {}, "message": "Admin must select a team for PvE"}
    else:
        return {"status": "error", "data": {}, "message": "Only student or admin can create a match with bot"}

    human_group = await database[GROUPS_COLLECTION].find_one({"_id": group_id}, {"_id": 1, "name": 1})
    if not human_group:
        return {"status": "error", "data": {}, "message": "Nhóm hiện tại không tồn tại."}

    active_conflict = await database[MATCHES_COLLECTION].find_one(
        {
            "status": {"$in": ACTIVE_MATCH_STATUSES},
            "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}],
        },
        {"_id": 1},
    )
    if active_conflict:
        return {"status": "error", "data": {}, "message": "Nhóm này đang có một trận đấu đang diễn ra hoặc chờ bắt đầu."}

    current = _now_utc()
    room_name = (payload.room_name or "").strip() or f"{human_group.get('name', group_id)} vs {GREEDY_BOT_TEAM_NAME}"
    match_id = await _generate_unique_match_id()
    human_api_key = _generate_api_key()
    bot_api_key = _generate_api_key()
    bot_team_id = _generate_bot_team_id()
    bot_side = "O" if human_side == "X" else "X"

    teams = {
        human_side: {
            "team_id": group_id,
            "api_key": human_api_key,
            "is_connected": True,
            "last_heartbeat": current,
            "kind": "human",
            "is_bot": False,
            "bot": None,
        },
        bot_side: {
            "team_id": bot_team_id,
            "api_key": bot_api_key,
            "is_connected": True,
            "last_heartbeat": current,
            "kind": "bot",
            "is_bot": True,
            "bot": {"type": "greedy", "name": GREEDY_BOT_TEAM_NAME},
        },
    }

    match_doc = {
        "_id": match_id,
        "room_name": room_name,
        "status": "playing",
        "mode": "pve_greedy",
        "created_by": current_user.get("_id"),
        "rev": 0,
        "updated_at": current,
        "board": _create_board(),
        "teams": {"X": teams["X"], "O": teams["O"]},
        "current_turn": "X",
        "winner": None,
        "history": [],
        "events": [
            build_event(
                "match_created",
                message="Trận đấu với Greedy Bot đã được tạo.",
                payload={
                    "created_by": current_user.get("_id"),
                    "human_team_id": group_id,
                    "human_side": human_side,
                    "bot_team_id": bot_team_id,
                    "mode": "pve_greedy",
                },
            ),
            build_event(
                "match_started",
                message="Trận PvE bắt đầu.",
                payload={"first_turn": "X"},
            ),
        ],
        "start_time": current,
        "started_at": current,
        "finished_at": None,
        "turn_deadline_at": None,
        "finish_reason": None,
        "created_at": current,
    }

    await database[MATCHES_COLLECTION].insert_one(match_doc)
    created = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    created = await advance_match(created)

    created_payload = _build_match_payload(
        created,
        {group_id: human_group.get("name", group_id)},
        include_board=True,
        include_history=True,
        include_events=True,
    )
    created_payload["teams"][human_side]["api_key"] = human_api_key

    return {"status": "success", "data": {"match": created_payload, "my_team": {"id": group_id, "side": human_side, "api_key": human_api_key}}, "message": ""}


@router.post("/{match_id}/move")
async def submit_human_move(
    match_id: str,
    payload: HumanMoveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    if not match:
        return {"status": "error", "data": {}, "message": "Match not found"}
    if match.get("mode") != "pve_greedy":
        return {"status": "error", "data": {}, "message": "Web moves are only available for PvE matches"}

    teams = match.get("teams", {})
    role = current_user.get("role")
    side = payload.side
    if role == "student":
        group_id = str(current_user.get("group_id") or "")
        side = "X" if teams.get("X", {}).get("team_id") == group_id else "O" if teams.get("O", {}).get("team_id") == group_id else None
    elif role == "admin":
        if side not in ("X", "O"):
            side = "X" if not teams.get("X", {}).get("is_bot") else "O"
    else:
        return {"status": "error", "data": {}, "message": "Forbidden"}

    if side not in ("X", "O") or teams.get(side, {}).get("is_bot"):
        return {"status": "error", "data": {}, "message": "Forbidden"}

    updated, error = await apply_move(match_id, side, payload.x, payload.y, team_id=teams.get(side, {}).get("team_id"))
    if error:
        return {"status": "error", "data": {}, "message": error}
    updated = await advance_match(updated)

    group_ids = {teams.get("X", {}).get("team_id", ""), teams.get("O", {}).get("team_id", "")}
    group_ids.discard("")
    group_name_map = await _load_group_name_map(group_ids)
    return {"status": "success", "data": {"match": _build_match_payload(updated, group_name_map, include_board=True, include_history=True, include_events=True)}, "message": ""}


@router.post("/{match_id}/surrender")
async def surrender_current_match(
    match_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    if not match:
        return {"status": "error", "data": {}, "message": "Match not found"}

    teams = match.get("teams", {})
    side = None
    role = current_user.get("role")
    if role == "student":
        group_id = str(current_user.get("group_id") or "")
        side = "X" if teams.get("X", {}).get("team_id") == group_id else "O" if teams.get("O", {}).get("team_id") == group_id else None
    elif role == "admin":
        side = str(match.get("current_turn") or "X")
    else:
        return {"status": "error", "data": {}, "message": "Forbidden"}

    if side not in ("X", "O"):
        return {"status": "error", "data": {}, "message": "Forbidden"}

    updated, error = await surrender_match(match_id, side, team_id=teams.get(side, {}).get("team_id"))
    if error:
        return {"status": "error", "data": {}, "message": error}

    updated_teams = updated.get("teams", {}) if updated else teams
    group_ids = {updated_teams.get("X", {}).get("team_id", ""), updated_teams.get("O", {}).get("team_id", "")}
    group_ids.discard("")
    group_name_map = await _load_group_name_map(group_ids)
    return {"status": "success", "data": {"match": _build_match_payload(updated, group_name_map, include_board=True, include_history=True, include_events=True)}, "message": ""}


@router.post("/player-room")
async def create_player_room(payload: CreatePlayerRoomRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_student(current_user):
        return {"status": "error", "data": {}, "message": "Only student can create player rooms"}
    database = get_database()
    group_id = str(current_user.get("group_id") or "").strip()
    if not group_id:
        return {"status": "error", "data": {}, "message": "Bạn cần tham gia một nhóm trước khi tạo phòng."}
    owner_group = await database[GROUPS_COLLECTION].find_one({"_id": group_id}, {"_id": 1, "name": 1})
    if not owner_group:
        return {"status": "error", "data": {}, "message": "Nhóm hiện tại không tồn tại."}
    opponent_group_id = str(payload.opponent_group_id or "").strip() or None
    if opponent_group_id == group_id:
        return {"status": "error", "data": {}, "message": "Đối thủ phải là nhóm khác."}
    opponent_group = None
    if opponent_group_id:
        opponent_group = await database[GROUPS_COLLECTION].find_one({"_id": opponent_group_id}, {"_id": 1, "name": 1})
        if not opponent_group:
            return {"status": "error", "data": {}, "message": "Nhóm đối thủ không tồn tại."}
    conflict_ids = [group_id] + ([opponent_group_id] if opponent_group_id else [])
    active_conflict = await database[MATCHES_COLLECTION].find_one({"status": {"$in": ACTIVE_MATCH_STATUSES}, "$or": [{"teams.X.team_id": {"$in": conflict_ids}}, {"teams.O.team_id": {"$in": conflict_ids}}]}, {"_id": 1})
    if active_conflict:
        return {"status": "error", "data": {}, "message": "Một trong các nhóm đã có trận đang hoạt động."}
    current = _now_utc()
    match_id = await _generate_unique_match_id()
    pending_team_id = _generate_bot_team_id()
    room_name = (payload.room_name or "").strip() or f"{owner_group.get('name', group_id)} vs Người chơi khác"
    o_team_id = opponent_group_id or pending_team_id
    o_name = opponent_group.get("name", o_team_id) if opponent_group else "Đang chờ đối thủ"
    status = "playing" if opponent_group_id else "waiting"
    match_doc = {
        "_id": match_id, "room_name": room_name, "status": status, "mode": "player_room", "visibility": payload.visibility,
        "owner_group_id": group_id, "opponent_group_id": opponent_group_id, "created_by": current_user.get("_id"),
        "rev": 0, "updated_at": current, "board": _create_board(),
        "teams": {
            "X": {"team_id": group_id, "api_key": _generate_api_key(), "is_connected": True, "last_heartbeat": current, "kind": "human", "is_bot": False, "bot": None},
            "O": {"team_id": o_team_id, "api_key": _generate_api_key(), "is_connected": bool(opponent_group_id), "last_heartbeat": current if opponent_group_id else None, "kind": "human", "is_bot": False, "bot": None},
        },
        "current_turn": "X", "winner": None, "history": [],
        "events": [build_event("match_created", message="Phòng đấu người chơi đã được tạo.", payload={"mode": "player_room", "owner_group_id": group_id, "visibility": payload.visibility})] + ([build_event("match_started", message="Hai đội đã sẵn sàng, trận đấu bắt đầu.", payload={"first_turn": "X"})] if opponent_group_id else []),
        "start_time": current, "started_at": current if opponent_group_id else None, "finished_at": None, "turn_deadline_at": None, "finish_reason": None, "created_at": current,
    }
    await database[MATCHES_COLLECTION].insert_one(match_doc)
    created = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    group_name_map = {group_id: owner_group.get("name", group_id), o_team_id: o_name}
    return {"status": "success", "data": {"match": _build_match_payload(created, group_name_map, include_board=True, include_history=True, include_events=True), "my_team": {"id": group_id, "side": "X"}}, "message": ""}


@router.post("/{match_id}/join")
async def join_player_room(match_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_student(current_user):
        return {"status": "error", "data": {}, "message": "Only student can join player rooms"}
    database = get_database()
    group_id = str(current_user.get("group_id") or "").strip()
    if not group_id:
        return {"status": "error", "data": {}, "message": "Bạn cần tham gia một nhóm trước khi vào phòng."}
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    if not match or match.get("mode") != "player_room":
        return {"status": "error", "data": {}, "message": "Room not found"}
    if match.get("status") != "waiting":
        return {"status": "error", "data": {}, "message": "Room is not joinable"}
    if match.get("owner_group_id") == group_id:
        return {"status": "error", "data": {}, "message": "Bạn không thể tự đấu với chính mình."}
    if match.get("opponent_group_id") and match.get("opponent_group_id") != group_id:
        return {"status": "error", "data": {}, "message": "Đây là phòng riêng của nhóm khác."}
    active_conflict = await database[MATCHES_COLLECTION].find_one({"_id": {"$ne": match_id}, "status": {"$in": ACTIVE_MATCH_STATUSES}, "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}]}, {"_id": 1})
    if active_conflict:
        return {"status": "error", "data": {}, "message": "Nhóm của bạn đang có trận đang hoạt động."}
    current = _now_utc()
    await database[MATCHES_COLLECTION].update_one(
        {"_id": match_id, "status": "waiting"},
        {"$set": {"status": "playing", "opponent_group_id": group_id, "teams.O.team_id": group_id, "teams.O.is_connected": True, "teams.O.last_heartbeat": current, "started_at": current, "updated_at": current}, "$inc": {"rev": 1}, "$push": {"events": {"$each": [build_event("room_joined", message="Đối thủ đã tham gia phòng.", side="O", team_id=group_id), build_event("match_started", message="Hai đội đã sẵn sàng, trận đấu bắt đầu.", payload={"first_turn": "X"})]}}},
    )
    updated = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    teams = updated.get("teams", {})
    group_name_map = await _load_group_name_map({teams.get("X", {}).get("team_id", ""), teams.get("O", {}).get("team_id", "")})
    return {"status": "success", "data": {"match": _build_match_payload(updated, group_name_map, include_board=True, include_history=True, include_events=True), "my_team": {"id": group_id, "side": "O"}}, "message": ""}

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
        "status": {"$in": ACTIVE_MATCH_STATUSES},
        "$or": [{"teams.X.team_id": group_id}, {"teams.O.team_id": group_id}],
    }
    my_match = await database[MATCHES_COLLECTION].find_one(
        my_match_query,
        sort=[("created_at", -1)],
    )

    if my_match:
        my_match = await advance_match(my_match)
        if not my_match or my_match.get("status") not in ACTIVE_MATCH_STATUSES:
            overview = await list_matches_overview(current_user)
            return {
                "status": "success",
                "data": {
                    "my_current_match": _build_match_payload(my_match, await _load_group_name_map({my_match.get("teams", {}).get("X", {}).get("team_id", ""), my_match.get("teams", {}).get("O", {}).get("team_id", "")}), include_board=True, include_history=True, include_events=True) if my_match else None,
                    "my_team": {"id": group_id},
                    "other_matches": overview.get("data", {}),
                },
                "message": "",
            }
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
        "status": {"$in": ACTIVE_MATCH_STATUSES},
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
        "board": 1,
        "history": 1,
        "events": 1,
        "winning_cells": 1,
    }

    my_match = await database[MATCHES_COLLECTION].find_one(
        my_match_query,
        projection,
        sort=[("created_at", -1)],
    )
    if my_match:
        my_match = await advance_match(my_match)

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


@router.delete("/{match_id}")
async def delete_match(match_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_admin(current_user):
        return {
            "status": "error",
            "data": {},
            "message": "Only admin can delete matches",
        }

    database = get_database()
    delete_result = await database[MATCHES_COLLECTION].delete_one({"_id": match_id})

    if delete_result.deleted_count == 0:
        return {
            "status": "error",
            "data": {},
            "message": "Match not found",
        }

    return {
        "status": "success",
        "data": {"deleted_match_id": match_id},
        "message": "",
    }


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











