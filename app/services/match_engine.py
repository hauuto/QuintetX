from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import MATCHES_COLLECTION
from solutions.solution_greedy import strategy as greedy_strategy

LEGACY_GREEDY_BOT_TEAM_IDS = {"T9999GREEDY01", "T9999GREEDY02"}


def now_utc() -> datetime:
    return datetime.utcnow()


def as_utc_naive(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def to_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def side_value(side: str) -> int:
    return 1 if side == "X" else 2


def other_side(side: str) -> str:
    return "O" if side == "X" else "X"


def build_event(
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
        "created_at": now_utc(),
    }


def find_winning_cells(board: list[list[int]], x: int, y: int, value: int) -> list[dict[str, int]]:
    for dx, dy in [(1, 0), (0, 1), (1, 1), (1, -1)]:
        cells = [{"x": x, "y": y}]
        step = 1
        while True:
            nx = x + dx * step
            ny = y + dy * step
            if nx < 0 or ny < 0 or nx >= settings.BOARD_SIZE or ny >= settings.BOARD_SIZE:
                break
            if board[nx][ny] != value:
                break
            cells.append({"x": nx, "y": ny})
            step += 1

        step = 1
        while True:
            nx = x - dx * step
            ny = y - dy * step
            if nx < 0 or ny < 0 or nx >= settings.BOARD_SIZE or ny >= settings.BOARD_SIZE:
                break
            if board[nx][ny] != value:
                break
            cells.insert(0, {"x": nx, "y": ny})
            step += 1

        if len(cells) >= 5:
            return cells
    return []


def check_win(board: list[list[int]], x: int, y: int, value: int) -> bool:
    return bool(find_winning_cells(board, x, y, value))


def is_bot_side(match: dict[str, Any], side: str) -> bool:
    team = match.get("teams", {}).get(side, {})
    return bool(
        team.get("is_bot")
        or team.get("kind") == "bot"
        or team.get("team_id") in LEGACY_GREEDY_BOT_TEAM_IDS
    )


def first_empty_cell(board: list[list[int]]) -> tuple[int, int] | None:
    for x in range(settings.BOARD_SIZE):
        for y in range(settings.BOARD_SIZE):
            if board[x][y] == 0:
                return x, y
    return None


def resolve_greedy_bot_move(board: list[list[int]], side: str) -> tuple[int, int] | None:
    fallback = first_empty_cell(board)
    if not fallback:
        return None

    try:
        move = greedy_strategy({"board": board, "side": side})
    except Exception:
        return fallback

    if not isinstance(move, (tuple, list)) or len(move) != 2:
        return fallback

    try:
        x = int(move[0])
        y = int(move[1])
    except Exception:
        return fallback

    if not (0 <= x < settings.BOARD_SIZE and 0 <= y < settings.BOARD_SIZE):
        return fallback
    if board[x][y] != 0:
        return fallback
    return x, y


async def apply_turn_timeout_if_needed(match: dict[str, Any] | None) -> dict[str, Any] | None:
    if not match or match.get("status") != "playing":
        return match
    if match.get("mode") in ("pve_greedy", "player_room"):
        return match

    deadline = as_utc_naive(match.get("turn_deadline_at"))
    current = now_utc()
    if not deadline or current <= deadline:
        return match

    loser_side = match.get("current_turn")
    winner_side = other_side(loser_side)
    database = get_database()

    await database[MATCHES_COLLECTION].update_one(
        {"_id": match.get("_id"), "status": "playing", "current_turn": loser_side},
        {
            "$set": {
                "status": "finished",
                "winner": winner_side,
                "finished_at": current,
                "finish_reason": "timeout_forfeit",
                "turn_deadline_at": None,
                "updated_at": current,
            },
            "$inc": {"rev": 1},
            "$push": {
                "events": {
                    "$each": [
                        build_event(
                            "timeout_forfeit",
                            message=f"Đội {loser_side} quá thời gian {settings.MOVE_TIMEOUT_SECONDS} giây và bị xử thua.",
                            side=loser_side,
                            team_id=match.get("teams", {}).get(loser_side, {}).get("team_id"),
                        ),
                        build_event(
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


async def apply_move(
    match_id: str,
    side: str,
    x: int,
    y: int,
    *,
    team_id: str | None = None,
    is_bot: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    match = await apply_turn_timeout_if_needed(match)
    if not match:
        return None, "Match not found"
    if match.get("status") != "playing":
        return match, "Match is not playing"
    if match.get("current_turn") != side:
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id},
            {
                "$push": {
                    "events": build_event(
                        "move_rejected",
                        message=f"Đội {side} gửi nước đi sai lượt.",
                        side=side,
                        team_id=team_id,
                        payload={"x": x, "y": y, "reason": "not_your_turn"},
                    )
                }
            },
        )
        return match, "Not your turn"
    if x < 0 or y < 0 or x >= settings.BOARD_SIZE or y >= settings.BOARD_SIZE:
        return match, "Move is out of board range"

    current = now_utc()
    board_cell_path = f"board.{x}.{y}"
    result = await database[MATCHES_COLLECTION].update_one(
        {"_id": match_id, "status": "playing", "current_turn": side, board_cell_path: 0},
        {
            "$set": {
                board_cell_path: side_value(side),
                f"teams.{side}.last_heartbeat": current,
                f"teams.{side}.is_connected": True,
                "updated_at": current,
            },
            "$inc": {"rev": 1},
            "$push": {
                "history": {"x": x, "y": y, "p": side, "t": current},
                "events": build_event(
                    "move_accepted",
                    message=f"Đội {side} đi nước ({x}, {y}).",
                    side=side,
                    team_id=team_id,
                    payload={"x": x, "y": y, **({"is_bot": True} if is_bot else {})},
                ),
            },
        },
    )
    if result.matched_count == 0:
        return await database[MATCHES_COLLECTION].find_one({"_id": match_id}), "Cell is occupied or state changed"

    updated = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    board = updated.get("board", [])
    winning_cells = find_winning_cells(board, x, y, side_value(side))
    if winning_cells:
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id, "status": "playing"},
            {
                "$set": {
                    "status": "finished",
                    "winner": side,
                    "finished_at": current,
                    "finish_reason": "win",
                    "winning_cells": winning_cells,
                    "turn_deadline_at": None,
                    "updated_at": current,
                },
                "$inc": {"rev": 1},
                "$push": {
                    "events": {
                        "$each": [
                            build_event(
                                "win_detected",
                                message=f"Đội {side} đã tạo 5 quân liên tiếp.",
                                side=side,
                                team_id=team_id,
                                payload={"winning_cells": winning_cells},
                            ),
                            build_event(
                                "match_finished",
                                message=f"Trận kết thúc. Đội {side} chiến thắng.",
                                side=side,
                                team_id=team_id,
                                payload={"reason": "win", "winning_cells": winning_cells, **({"is_bot": True} if is_bot else {})},
                            ),
                        ]
                    }
                },
            },
        )
    else:
        next_side = other_side(side)
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id, "status": "playing"},
            {
                "$set": {
                    "current_turn": next_side,
                    "turn_deadline_at": None if updated.get("mode") in ("pve_greedy", "player_room") else current + timedelta(seconds=settings.MOVE_TIMEOUT_SECONDS),
                    "updated_at": current,
                },
                "$inc": {"rev": 1},
                "$push": {
                    "events": build_event(
                        "turn_changed",
                        message=f"Đến lượt đội {next_side}.",
                        side=next_side,
                        team_id=updated.get("teams", {}).get(next_side, {}).get("team_id"),
                    )
                },
            },
        )

    return await database[MATCHES_COLLECTION].find_one({"_id": match_id}), None


async def surrender_match(match_id: str, side: str, *, team_id: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if side not in ("X", "O"):
        return None, "Invalid side"

    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one({"_id": match_id})
    if not match:
        return None, "Match not found"
    if match.get("status") not in ("waiting", "playing"):
        return match, "Match is already finished"

    current = now_utc()
    winner_side = other_side(side)
    result = await database[MATCHES_COLLECTION].update_one(
        {"_id": match_id, "status": {"$in": ["waiting", "playing"]}},
        {
            "$set": {
                "status": "finished",
                "winner": winner_side,
                "finished_at": current,
                "finish_reason": "surrender",
                "turn_deadline_at": None,
                "updated_at": current,
            },
            "$inc": {"rev": 1},
            "$push": {
                "events": {
                    "$each": [
                        build_event(
                            "match_surrendered",
                            message=f"Đội {side} đã đầu hàng.",
                            side=side,
                            team_id=team_id,
                            payload={"winner": winner_side},
                        ),
                        build_event(
                            "match_finished",
                            message=f"Trận kết thúc. Đội {winner_side} chiến thắng do đối thủ đầu hàng.",
                            side=winner_side,
                            team_id=match.get("teams", {}).get(winner_side, {}).get("team_id"),
                            payload={"reason": "surrender", "surrendered_side": side},
                        ),
                    ]
                }
            },
        },
    )
    if result.matched_count == 0:
        return await database[MATCHES_COLLECTION].find_one({"_id": match_id}), "Match is already finished"
    return await database[MATCHES_COLLECTION].find_one({"_id": match_id}), None


async def finish_existing_win_if_needed(match: dict[str, Any] | None) -> dict[str, Any] | None:
    if not match or match.get("status") != "playing":
        return match

    board = match.get("board", [])
    history = match.get("history", []) or []
    for move in reversed(history):
        side = move.get("p")
        if side not in ("X", "O"):
            continue
        x = move.get("x")
        y = move.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            continue
        winning_cells = find_winning_cells(board, x, y, side_value(side))
        if not winning_cells:
            continue

        current = now_utc()
        database = get_database()
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match.get("_id"), "status": "playing"},
            {
                "$set": {
                    "status": "finished",
                    "winner": side,
                    "finished_at": current,
                    "finish_reason": "win",
                    "winning_cells": winning_cells,
                    "turn_deadline_at": None,
                    "updated_at": current,
                },
                "$inc": {"rev": 1},
                "$push": {
                    "events": {
                        "$each": [
                            build_event(
                                "win_detected",
                                message=f"Đội {side} đã tạo 5 quân liên tiếp.",
                                side=side,
                                team_id=match.get("teams", {}).get(side, {}).get("team_id"),
                                payload={"winning_cells": winning_cells},
                            ),
                            build_event(
                                "match_finished",
                                message=f"Trận kết thúc. Đội {side} chiến thắng.",
                                side=side,
                                team_id=match.get("teams", {}).get(side, {}).get("team_id"),
                                payload={"reason": "win", "winning_cells": winning_cells},
                            ),
                        ]
                    }
                },
            },
        )
        return await database[MATCHES_COLLECTION].find_one({"_id": match.get("_id")})
    return match


async def play_greedy_bot_turn_if_needed(match: dict[str, Any] | None) -> dict[str, Any] | None:
    if not match or match.get("status") != "playing":
        return match

    bot_side = str(match.get("current_turn") or "")
    if bot_side not in ("X", "O") or not is_bot_side(match, bot_side):
        return match

    board = match.get("board", [])
    move = resolve_greedy_bot_move(board, bot_side)
    database = get_database()
    match_id = match.get("_id")
    team_id = match.get("teams", {}).get(bot_side, {}).get("team_id")
    if not move:
        current = now_utc()
        await database[MATCHES_COLLECTION].update_one(
            {"_id": match_id, "status": "playing"},
            {
                "$set": {
                    "status": "finished",
                    "winner": None,
                    "finished_at": current,
                    "finish_reason": "draw",
                    "turn_deadline_at": None,
                    "updated_at": current,
                },
                "$inc": {"rev": 1},
                "$push": {
                    "events": build_event(
                        "match_finished",
                        message="Trận kết thúc hòa do bàn cờ đã đầy.",
                        payload={"reason": "draw"},
                    )
                },
            },
        )
        return await database[MATCHES_COLLECTION].find_one({"_id": match_id})

    updated, _ = await apply_move(match_id, bot_side, move[0], move[1], team_id=team_id, is_bot=True)
    return updated


async def advance_match(match: dict[str, Any] | None) -> dict[str, Any] | None:
    match = await finish_existing_win_if_needed(match)
    match = await apply_turn_timeout_if_needed(match)
    match = await play_greedy_bot_turn_if_needed(match)
    match = await finish_existing_win_if_needed(match)
    match = await apply_turn_timeout_if_needed(match)
    return match


def agent_state_payload(match: dict[str, Any], side: str) -> dict[str, Any]:
    teams = match.get("teams", {})
    return {
        "match_id": match.get("_id"),
        "board": match.get("board", []),
        "turn": match.get("current_turn"),
        "side": side,
        "match_status": match.get("status"),
        "winner": match.get("winner"),
        "turn_deadline_at": to_iso(match.get("turn_deadline_at")),
        "teams": {
            side_key: {
                "team_id": teams.get(side_key, {}).get("team_id"),
                "is_connected": bool(teams.get(side_key, {}).get("is_connected", False)),
                "last_heartbeat": to_iso(teams.get(side_key, {}).get("last_heartbeat")),
            }
            for side_key in ("X", "O")
        },
        "events": [
            {
                "type": item.get("type"),
                "message": item.get("message"),
                "side": item.get("side"),
                "team_id": item.get("team_id"),
                "payload": item.get("payload") or {},
                "created_at": to_iso(item.get("created_at")),
            }
            for item in match.get("events", [])[-50:]
        ],
    }

