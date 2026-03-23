from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.config import settings
from app.db.client import get_database
from app.db.init_db import USERS_COLLECTION


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
