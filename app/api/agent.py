from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_agent_session
from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import MATCHES_COLLECTION

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class MoveRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


def _now_utc() -> datetime:
    # MongoDB (Motor/PyMongo) commonly returns naive datetimes that represent UTC.
    # To avoid offset-aware/naive comparison bugs, we keep runtime timestamps naive UTC.
    return datetime.utcnow()


def _as_utc_naive(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _to_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _side_value(side: str) -> int:
    return 1 if side == "X" else 2


def _other_side(side: str) -> str:
    return "O" if side == "X" else "X"


def _build_event(
    event_type: str,
    *,
    message: str,
    side: str | None = None,
    team_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "message": message,
        "side": side,
        "team_id": team_id,
        "payload": payload or {},
        "created_at": _now_utc(),
    }


def _check_win(board: list[list[int]], x: int, y: int, value: int) -> bool:
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]

    for dx, dy in directions:
        count = 1

        step = 1
        while True:
            nx = x + dx * step
            ny = y + dy * step
            if nx < 0 or ny < 0 or nx >= settings.BOARD_SIZE or ny >= settings.BOARD_SIZE:
                break
            if board[nx][ny] != value:
                break
            count += 1
            step += 1

        step = 1
        while True:
            nx = x - dx * step
            ny = y - dy * step
            if nx < 0 or ny < 0 or nx >= settings.BOARD_SIZE or ny >= settings.BOARD_SIZE:
                break
            if board[nx][ny] != value:
                break
            count += 1
            step += 1

        if count >= 5:
            return True

    return False


async def _apply_turn_timeout_if_needed(match: dict[str, Any]) -> dict[str, Any]:
    if match.get("status") != "playing":
        return match

    deadline = _as_utc_naive(match.get("turn_deadline_at"))
    now = _now_utc()
    if not deadline or now <= deadline:
        return match

    loser_side = match.get("current_turn")
    winner_side = _other_side(loser_side)
    database = get_database()

    await database[MATCHES_COLLECTION].update_one(
        {
            "_id": match.get("_id"),
            "status": "playing",
            "current_turn": loser_side,
        },
        {
            "$set": {
                "status": "finished",
                "winner": winner_side,
                "finished_at": now,
                "finish_reason": "timeout_forfeit",
                "turn_deadline_at": None,
            },
            "$push": {
                "events": {
                    "$each": [
                        _build_event(
                            "timeout_forfeit",
                            message=f"Đội {loser_side} quá thời gian 10 giây và bị xử thua.",
                            side=loser_side,
                            team_id=match.get("teams", {}).get(loser_side, {}).get("team_id"),
                        ),
                        _build_event(
                            "match_finished",
                            message=f"Trận kết thúc. Đội {winner_side} chiến thắng do timeout.",
                            side=winner_side,
                            team_id=match.get("teams", {}).get(winner_side, {}).get("team_id"),
                            payload={"reason": "timeout_forfeit"},
                        ),
                    ]
                }
            },
        },
    )

    return await database[MATCHES_COLLECTION].find_one({"_id": match.get("_id")})


def _agent_state_payload(match: dict[str, Any], side: str) -> dict[str, Any]:
    teams = match.get("teams", {})
    events = match.get("events", [])

    return {
        "match_id": match.get("_id"),
        "board": match.get("board", []),
        "turn": match.get("current_turn"),
        "side": side,
        "match_status": match.get("status"),
        "winner": match.get("winner"),
        "turn_deadline_at": _to_iso(match.get("turn_deadline_at")),
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
        "events": [
            {
                "type": item.get("type"),
                "message": item.get("message"),
                "side": item.get("side"),
                "team_id": item.get("team_id"),
                "payload": item.get("payload") or {},
                "created_at": _to_iso(item.get("created_at")),
            }
            for item in events[-50:]
        ],
    }


@router.post("/init")
async def agent_init(session: dict[str, Any] = Depends(get_agent_session)):
    match = session["match"]
    side = session["side"]
    team_id = session["team_id"]

    if match.get("status") == "finished":
        return {
            "status": "success",
            "data": _agent_state_payload(match, side),
            "message": "",
        }

    database = get_database()
    now = _now_utc()

    await database[MATCHES_COLLECTION].update_one(
        {"_id": match.get("_id")},
        {
            "$set": {
                f"teams.{side}.is_connected": True,
                f"teams.{side}.last_heartbeat": now,
            },
            "$push": {
                "events": _build_event(
                    "agent_ready",
                    message=f"Đội {side} đã sẵn sàng.",
                    side=side,
                    team_id=team_id,
                )
            },
        },
    )

    refreshed = await database[MATCHES_COLLECTION].find_one({"_id": match.get("_id")})

    can_start = (
        refreshed.get("status") == "waiting"
        and refreshed.get("teams", {}).get("X", {}).get("is_connected")
        and refreshed.get("teams", {}).get("O", {}).get("is_connected")
    )

    if can_start:
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match.get("_id"), "status": "waiting"},
            {
                "$set": {
                    "status": "playing",
                    "current_turn": "X",
                    "started_at": now,
                    "turn_deadline_at": now + timedelta(seconds=settings.MOVE_TIMEOUT_SECONDS),
                },
                "$push": {
                    "events": _build_event(
                        "match_started",
                        message="Hai đội đã sẵn sàng, trận đấu bắt đầu.",
                        payload={"first_turn": "X"},
                    )
                },
            },
        )

    # Backward-compatible bootstrap: older matches could be created with status
    # "playing" but without started_at/turn_deadline_at. Ensure those fields exist
    # once both agents are connected so timeout logic is consistent.
    if (
        refreshed.get("status") == "playing"
        and refreshed.get("teams", {}).get("X", {}).get("is_connected")
        and refreshed.get("teams", {}).get("O", {}).get("is_connected")
    ):
        bootstrap_set: dict[str, Any] = {}
        bootstrap_events: list[dict[str, Any]] = []

        if not refreshed.get("started_at"):
            bootstrap_set["started_at"] = now
            bootstrap_events.append(
                _build_event(
                    "match_started",
                    message="Hai đội đã sẵn sàng, trận đấu bắt đầu.",
                    payload={"first_turn": refreshed.get("current_turn") or "X"},
                )
            )

        if not refreshed.get("current_turn"):
            bootstrap_set["current_turn"] = "X"

        if not refreshed.get("turn_deadline_at"):
            bootstrap_set["turn_deadline_at"] = now + timedelta(seconds=settings.MOVE_TIMEOUT_SECONDS)

        if bootstrap_set or bootstrap_events:
            update_doc: dict[str, Any] = {}
            if bootstrap_set:
                update_doc["$set"] = bootstrap_set
            if bootstrap_events:
                update_doc["$push"] = {"events": {"$each": bootstrap_events}}

            await database[MATCHES_COLLECTION].update_one(
                {"_id": match.get("_id"), "status": "playing"},
                update_doc,
            )

    latest = await database[MATCHES_COLLECTION].find_one({"_id": match.get("_id")})
    latest = await _apply_turn_timeout_if_needed(latest)

    return {
        "status": "success",
        "data": _agent_state_payload(latest, side),
        "message": "",
    }


@router.get("/state")
async def agent_state(session: dict[str, Any] = Depends(get_agent_session)):
    database = get_database()
    side = session["side"]
    match = await database[MATCHES_COLLECTION].find_one({"_id": session["match"].get("_id")})
    match = await _apply_turn_timeout_if_needed(match)

    return {
        "status": "success",
        "data": _agent_state_payload(match, side),
        "message": "",
    }


@router.post("/heartbeat")
async def agent_heartbeat(session: dict[str, Any] = Depends(get_agent_session)):
    database = get_database()
    side = session["side"]
    now = _now_utc()

    await database[MATCHES_COLLECTION].update_one(
        {"_id": session["match"].get("_id")},
        {
            "$set": {
                f"teams.{side}.last_heartbeat": now,
                f"teams.{side}.is_connected": True,
            }
        },
    )

    return {
        "status": "success",
        "data": {"side": side, "ts": _to_iso(now)},
        "message": "",
    }


@router.post("/move")
async def agent_move(payload: MoveRequest, session: dict[str, Any] = Depends(get_agent_session)):
    database = get_database()
    side = session["side"]
    team_id = session["team_id"]
    match_id = session["match"].get("_id")

    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    match = await _apply_turn_timeout_if_needed(match)

    if match.get("status") != "playing":
        return {"status": "error", "data": {}, "message": "Match is not playing"}

    if match.get("current_turn") != side:
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id},
            {
                "$push": {
                    "events": _build_event(
                        "move_rejected",
                        message=f"Đội {side} gửi nước đi sai lượt.",
                        side=side,
                        team_id=team_id,
                        payload={"x": payload.x, "y": payload.y, "reason": "not_your_turn"},
                    )
                }
            },
        )
        return {"status": "error", "data": {}, "message": "Not your turn"}

    if payload.x >= settings.BOARD_SIZE or payload.y >= settings.BOARD_SIZE:
        return {"status": "error", "data": {}, "message": "Move is out of board range"}

    board_cell_path = f"board.{payload.x}.{payload.y}"
    now = _now_utc()

    result = await database[MATCHES_COLLECTION].update_one(
        {
            "_id": match_id,
            "status": "playing",
            "current_turn": side,
            board_cell_path: 0,
        },
        {
            "$set": {
                board_cell_path: _side_value(side),
                f"teams.{side}.last_heartbeat": now,
                f"teams.{side}.is_connected": True,
            },
            "$push": {
                "history": {"x": payload.x, "y": payload.y, "p": side, "t": now},
                "events": _build_event(
                    "move_accepted",
                    message=f"Đội {side} đi nước ({payload.x}, {payload.y}).",
                    side=side,
                    team_id=team_id,
                    payload={"x": payload.x, "y": payload.y},
                ),
            },
        },
    )

    if result.matched_count == 0:
        return {"status": "error", "data": {}, "message": "Cell is occupied or state changed"}

    updated = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    board = updated.get("board", [])

    if _check_win(board, payload.x, payload.y, _side_value(side)):
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id, "status": "playing"},
            {
                "$set": {
                    "status": "finished",
                    "winner": side,
                    "finished_at": now,
                    "finish_reason": "win",
                    "turn_deadline_at": None,
                },
                "$push": {
                    "events": {
                        "$each": [
                            _build_event(
                                "win_detected",
                                message=f"Đội {side} đã tạo 5 quân liên tiếp.",
                                side=side,
                                team_id=team_id,
                            ),
                            _build_event(
                                "match_finished",
                                message=f"Trận kết thúc. Đội {side} chiến thắng.",
                                side=side,
                                team_id=team_id,
                                payload={"reason": "win"},
                            ),
                        ]
                    }
                },
            },
        )
    else:
        next_side = _other_side(side)
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id, "status": "playing"},
            {
                "$set": {
                    "current_turn": next_side,
                    "turn_deadline_at": now + timedelta(seconds=settings.MOVE_TIMEOUT_SECONDS),
                },
                "$push": {
                    "events": _build_event(
                        "turn_changed",
                        message=f"Đến lượt đội {next_side}.",
                        side=next_side,
                        team_id=updated.get("teams", {}).get(next_side, {}).get("team_id"),
                    )
                },
            },
        )

    latest = await database[MATCHES_COLLECTION].find_one({"_id": match_id})

    return {
        "status": "success",
        "data": _agent_state_payload(latest, side),
        "message": "",
    }
