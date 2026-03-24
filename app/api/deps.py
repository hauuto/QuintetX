from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import MATCHES_COLLECTION, USERS_COLLECTION


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return token


async def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    database = get_database()
    user = await database[USERS_COLLECTION].find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is deactivated")

    return user


CurrentUser = Depends(get_current_user)


async def get_agent_session(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_team_id: str | None = Header(default=None, alias="X-Team-ID"),
) -> dict[str, Any]:
    if not x_api_key or not x_team_id:
        raise HTTPException(status_code=401, detail="Missing X-API-Key or X-Team-ID")

    database = get_database()
    match = await database[MATCHES_COLLECTION].find_one(
        {
            "$or": [
                {"teams.X.team_id": x_team_id, "teams.X.api_key": x_api_key},
                {"teams.O.team_id": x_team_id, "teams.O.api_key": x_api_key},
            ],
            "status": {"$in": ["waiting", "playing", "finished"]},
        }
    )

    if not match:
        raise HTTPException(status_code=401, detail="Invalid agent credentials")

    side = "X"
    if match.get("teams", {}).get("X", {}).get("team_id") != x_team_id:
        side = "O"

    return {
        "match": match,
        "side": side,
        "team_id": x_team_id,
        "api_key": x_api_key,
    }


AgentSession = Depends(get_agent_session)
