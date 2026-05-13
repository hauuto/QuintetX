from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_agent_session
from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import MATCHES_COLLECTION
from app.services.match_engine import (
    advance_match,
    agent_state_payload,
    apply_move,
    build_event,
    now_utc,
    to_iso,
)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class MoveRequest(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


@router.post("/init")
async def agent_init(session: dict[str, Any] = Depends(get_agent_session)):
    match = session["match"]
    side = session["side"]
    team_id = session["team_id"]

    if match.get("status") == "finished":
        return {"status": "success", "data": agent_state_payload(match, side), "message": ""}

    database = get_database()
    current = now_utc()

    await database[MATCHES_COLLECTION].update_one(
        {"_id": match.get("_id")},
        {
            "$set": {
                f"teams.{side}.is_connected": True,
                f"teams.{side}.last_heartbeat": current,
                "updated_at": current,
            },
            "$inc": {"rev": 1},
            "$push": {
                "events": build_event(
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
                    "started_at": current,
                    "turn_deadline_at": current + timedelta(seconds=settings.MOVE_TIMEOUT_SECONDS),
                    "updated_at": current,
                },
                "$inc": {"rev": 1},
                "$push": {
                    "events": build_event(
                        "match_started",
                        message="Hai đội đã sẵn sàng, trận đấu bắt đầu.",
                        payload={"first_turn": "X"},
                    )
                },
            },
        )

    latest = await database[MATCHES_COLLECTION].find_one({"_id": match.get("_id")})
    latest = await advance_match(latest)

    return {"status": "success", "data": agent_state_payload(latest, side), "message": ""}


@router.get("/state")
async def agent_state(session: dict[str, Any] = Depends(get_agent_session)):
    database = get_database()
    side = session["side"]
    match = await database[MATCHES_COLLECTION].find_one({"_id": session["match"].get("_id")})
    match = await advance_match(match)
    return {"status": "success", "data": agent_state_payload(match, side), "message": ""}


@router.post("/heartbeat")
async def agent_heartbeat(session: dict[str, Any] = Depends(get_agent_session)):
    database = get_database()
    side = session["side"]
    current = now_utc()

    await database[MATCHES_COLLECTION].update_one(
        {"_id": session["match"].get("_id")},
        {
            "$set": {
                f"teams.{side}.last_heartbeat": current,
                f"teams.{side}.is_connected": True,
                "updated_at": current,
            }
        },
    )

    return {"status": "success", "data": {"side": side, "ts": to_iso(current)}, "message": ""}


@router.post("/move")
async def agent_move(payload: MoveRequest, session: dict[str, Any] = Depends(get_agent_session)):
    side = session["side"]
    team_id = session["team_id"]
    match_id = session["match"].get("_id")

    match, error = await apply_move(match_id, side, payload.x, payload.y, team_id=team_id)
    if error:
        return {"status": "error", "data": {}, "message": error}

    match = await advance_match(match)
    return {"status": "success", "data": agent_state_payload(match, side), "message": ""}
