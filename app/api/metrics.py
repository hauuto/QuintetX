from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.metrics import request_metrics


router = APIRouter(prefix="/api/v1/admin/metrics", tags=["metrics"])


def _ensure_admin(current_user: dict[str, Any]) -> bool:
    return current_user.get("role") == "admin"


@router.get("")
async def get_metrics(
    current_user: dict[str, Any] = Depends(get_current_user),
    top_n: int = 200,
):
    if not _ensure_admin(current_user):
        return {"status": "error", "data": {}, "message": "Only admin can access metrics"}

    return {
        "status": "success",
        "data": request_metrics.snapshot(top_n=top_n),
        "message": "",
    }


@router.post("/reset")
async def reset_metrics(current_user: dict[str, Any] = Depends(get_current_user)):
    if not _ensure_admin(current_user):
        return {"status": "error", "data": {}, "message": "Only admin can access metrics"}

    request_metrics.reset()
    return {"status": "success", "data": {}, "message": ""}
