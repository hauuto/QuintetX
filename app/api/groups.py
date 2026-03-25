from __future__ import annotations

from datetime import datetime, timezone
import math
import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.db.client import get_database
from app.db.init_db import (
    GROUPS_COLLECTION,
    MATCHES_COLLECTION,
    NOTIFICATIONS_COLLECTION,
    USERS_COLLECTION,
    SETTINGS_COLLECTION,
)

MAX_GROUP_MEMBERS = 6

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _gen_group_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    numeric = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"T{numeric}{suffix}"


def _gen_group_code() -> str:
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"GRP-{suffix}"


def _gen_notification_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    numeric = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"N{numeric}{suffix}"


async def _create_notification(
    *,
    user_id: str,
    sender_id: str,
    notification_type: str,
    message: str,
    group_id: str | None,
    status: str,
    link: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    database = get_database()
    await database[NOTIFICATIONS_COLLECTION].insert_one(
        {
            "_id": _gen_notification_id(),
            "user_id": user_id,
            "sender_id": sender_id,
            "type": notification_type,
            "message": message,
            "is_read": False,
            "status": status,
            "group_id": group_id,
            "link": link,
            "metadata": metadata or {},
            "created_at": _now_utc(),
        }
    )


def _build_member(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user.get("_id"),
        "mssv": user.get("mssv"),
        "full_name": user.get("full_name"),
        "joined_at": _now_utc(),
    }


async def _find_group_or_404(group_id: str) -> dict[str, Any]:
    database = get_database()
    group = await database[GROUPS_COLLECTION].find_one({"_id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


async def _ensure_group_leader(group: dict[str, Any], current_user: dict[str, Any]) -> None:
    if group.get("leader_id") != current_user.get("_id"):
        raise HTTPException(status_code=403, detail="Only leader can perform this action")


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    avatar_url: str | None = None
    is_public: bool = True


class JoinGroupRequest(BaseModel):
    message: str | None = None


class InviteRequest(BaseModel):
    mssv: str = Field(min_length=8, max_length=8)


class RenameGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ModerationToggleRequest(BaseModel):
    enabled: bool


@router.post("/moderation/toggle")
async def toggle_group_moderation(
    payload: ModerationToggleRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can toggle moderation")

    database = get_database()

    await database[SETTINGS_COLLECTION].update_one(
        {"_id": "moderation"},
        {"$set": {"group_moderation_enabled": payload.enabled}},
        upsert=True
    )

    return {"status": "success", "data": {"enabled": payload.enabled}, "message": "Updated group moderation"}


@router.post("/{group_id}/approve")
async def admin_approve_group(
    group_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can approve")
    database = get_database()
    group = await _find_group_or_404(group_id)
    if group.get("status") != "Pending":
        return {"status": "error", "data": {}, "message": "Nhóm không ở trạng thái chờ duyệt"}

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$set": {"status": "Active"}}
    )
    # Assign group to the leader actually
    await database[USERS_COLLECTION].update_one(
        {"_id": group.get("leader_id")},
        {"$set": {"group_id": group_id}}
    )

    await _create_notification(
        user_id=group.get("leader_id"),
        sender_id=current_user.get("_id"),
        notification_type="group_approved",
        message=f"Yêu cầu tạo nhóm {group.get('name')} đã được admin duyệt.",
        group_id=group_id,
        status="sent",
        link="/student/team",
    )
    return {"status": "success", "data": {}, "message": "Đã duyệt nhóm"}


@router.post("/{group_id}/reject")
async def admin_reject_group(
    group_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can reject")
    database = get_database()
    group = await _find_group_or_404(group_id)
    if group.get("status") != "Pending":
        return {"status": "error", "data": {}, "message": "Nhóm không ở trạng thái chờ duyệt"}

    await database[GROUPS_COLLECTION].delete_one({"_id": group_id})

    await _create_notification(
        user_id=group.get("leader_id"),
        sender_id=current_user.get("_id"),
        notification_type="group_rejected",
        message=f"Yêu cầu tạo nhóm {group.get('name')} đã bị admin từ chối.",
        group_id=None,
        status="sent",
    )
    return {"status": "success", "data": {}, "message": "Đã từ chối nhóm"}


@router.get("/open-missing")
async def list_open_groups_missing_members(
    current_user: dict[str, Any] = Depends(get_current_user),
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=10),
):
    del current_user
    database = get_database()

    search_query = q.strip()
    base_filter: dict[str, Any] = {
        "is_public": True,
        "status": {"$ne": "Pending"},
        "$expr": {"$lt": [{"$size": "$members"}, MAX_GROUP_MEMBERS]},
    }
    if search_query:
        base_filter["name"] = {"$regex": search_query, "$options": "i"}

    total_items = await database[GROUPS_COLLECTION].count_documents(base_filter)
    total_pages = max(1, math.ceil(total_items / page_size))
    current_page = min(page, total_pages)
    skip_count = (current_page - 1) * page_size

    groups_cursor = (
        database[GROUPS_COLLECTION]
        .find(
            base_filter,
            {
                "_id": 1,
                "group_code": 1,
                "name": 1,
                "description": 1,
                "avatar_url": 1,
                "is_public": 1,
                "leader_id": 1,
                "members": 1,
                "stats": 1,
            },
        )
        .sort("created_at", -1)
        .skip(skip_count)
        .limit(page_size)
    )

    groups = []
    async for group in groups_cursor:
        members_count = len(group.get("members", []))
        groups.append(
            {
                "id": group.get("_id"),
                "group_code": group.get("group_code"),
                "name": group.get("name"),
                "description": group.get("description"),
                "avatar_url": group.get("avatar_url"),
                "is_public": group.get("is_public"),
                "leader_id": group.get("leader_id"),
                "members_count": members_count,
                "slots_left": MAX_GROUP_MEMBERS - members_count,
                "stats": group.get("stats", {}),
            }
        )

    return {
        "status": "success",
        "data": {
            "groups": groups,
            "pagination": {
                "page": current_page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_prev": current_page > 1,
                "has_next": current_page < total_pages,
            },
            "query": search_query,
        },
        "message": "",
    }


@router.get("/me/dashboard")
async def get_my_group_dashboard(current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    group_id = current_user.get("group_id")

    if not group_id:
        return {
            "status": "success",
            "data": {
                "team": None,
                "stats": {"matches": 0, "wins": 0, "losses": 0},
                "matches": [],
            },
            "message": "",
        }

    group = await database[GROUPS_COLLECTION].find_one({"_id": group_id})
    if not group:
        return {
            "status": "success",
            "data": {
                "team": None,
                "stats": {"matches": 0, "wins": 0, "losses": 0},
                "matches": [],
            },
            "message": "",
        }

    match_filter = {
        "status": "finished",
        "$or": [
            {"teams.X.team_id": group_id},
            {"teams.O.team_id": group_id},
        ],
    }

    total_matches = await database[MATCHES_COLLECTION].count_documents(match_filter)

    wins_filter = {
        "status": "finished",
        "$or": [
            {"teams.X.team_id": group_id, "winner": "X"},
            {"teams.O.team_id": group_id, "winner": "O"},
        ],
    }
    wins = await database[MATCHES_COLLECTION].count_documents(wins_filter)
    losses = max(total_matches - wins, 0)

    recent_cursor = (
        database[MATCHES_COLLECTION]
        .find(
            match_filter,
            {
                "_id": 1,
                "teams": 1,
                "winner": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(5)
    )

    raw_recent_matches = []
    opponent_ids: set[str] = set()
    async for match in recent_cursor:
        teams = match.get("teams", {})
        team_x = teams.get("X", {})
        team_o = teams.get("O", {})

        my_side = "X" if team_x.get("team_id") == group_id else "O"
        opponent_side = "O" if my_side == "X" else "X"
        opponent_team_id = teams.get(opponent_side, {}).get("team_id")
        if opponent_team_id:
            opponent_ids.add(opponent_team_id)

        raw_recent_matches.append(
            {
                "id": match.get("_id"),
                "my_side": my_side,
                "opponent_side": opponent_side,
                "opponent_team_id": opponent_team_id,
                "winner": match.get("winner"),
                "played_at": match.get("created_at"),
            }
        )

    opponent_name_map: dict[str, str] = {}
    if opponent_ids:
        async for opponent in database[GROUPS_COLLECTION].find(
            {"_id": {"$in": list(opponent_ids)}},
            {"_id": 1, "name": 1},
        ):
            opponent_name_map[opponent.get("_id")] = opponent.get("name", "Đối thủ chưa rõ")

    recent_matches = []
    for item in raw_recent_matches:
        winner = item.get("winner")
        my_side = item.get("my_side")
        result = "thắng" if winner == my_side else "thua"
        if winner is None:
            result = "hòa"

        played_at = item.get("played_at")
        recent_matches.append(
            {
                "id": item.get("id"),
                "opponent": opponent_name_map.get(item.get("opponent_team_id"), "Đối thủ chưa rõ"),
                "result": result,
                "played_at": played_at.isoformat() if played_at else None,
            }
        )

    team = {
        "id": group.get("_id"),
        "group_code": group.get("group_code"),
        "name": group.get("name"),
        "description": group.get("description"),
        "members": group.get("members", []),
    }

    return {
        "status": "success",
        "data": {
            "team": team,
            "stats": {
                "matches": total_matches,
                "wins": wins,
                "losses": losses,
            },
            "matches": recent_matches,
        },
        "message": "",
    }


@router.get("/me")
async def get_my_group(current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    group_id = current_user.get("group_id")
    if not group_id:
        return {"status": "success", "data": {"group": None}, "message": ""}

    group = await database[GROUPS_COLLECTION].find_one({"_id": group_id})
    if not group:
        return {"status": "success", "data": {"group": None}, "message": ""}

    return {"status": "success", "data": {"group": group}, "message": ""}


@router.post("")
async def create_group(payload: CreateGroupRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()

    if current_user.get("group_id"):
        return {"status": "error", "data": {}, "message": "User already has a group"}

    # Check if user already has a pending group
    pending_group = await database[GROUPS_COLLECTION].find_one({"leader_id": current_user.get("_id"), "status": "Pending"})
    if pending_group:
        return {"status": "error", "data": {}, "message": "Bạn đang có một yêu cầu tạo nhóm chờ duyệt"}

    from app.db.init_db import SETTINGS_COLLECTION
    settings_doc = await database[SETTINGS_COLLECTION].find_one({"_id": "moderation"})
    is_moderation_enabled = settings_doc.get("group_moderation_enabled", False) if settings_doc else False

    group_id = _gen_group_id()
    group_code = _gen_group_code()
    now = _now_utc()

    member = _build_member(current_user)
    group_doc = {
        "_id": group_id,
        "group_code": group_code,
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "avatar_url": payload.avatar_url,
        "is_public": payload.is_public,
        "leader_id": current_user.get("_id"),
        "members": [member],
        "pending_requests": [],
        "match_history": [],
        "stats": {"total": 0, "wins": 0, "losses": 0, "draws": 0},
        "created_at": now,
        "status": "Pending" if is_moderation_enabled else "Active"
    }

    await database[GROUPS_COLLECTION].insert_one(group_doc)

    if not is_moderation_enabled:
        await database[USERS_COLLECTION].update_one(
            {"_id": current_user.get("_id")},
            {"$set": {"group_id": group_id}},
        )

    return {"status": "success", "data": {"group": group_doc}, "message": "Yêu cầu tạo nhóm đang chờ duyệt" if is_moderation_enabled else "Tạo nhóm thành công"}


@router.post("/{group_id}/join")
async def request_join_group(
    group_id: str,
    payload: JoinGroupRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()

    if current_user.get("group_id"):
        return {"status": "error", "data": {}, "message": "User already has a group"}

    from app.db.init_db import SETTINGS_COLLECTION
    settings_doc = await database[SETTINGS_COLLECTION].find_one({"_id": "moderation"})
    is_moderation_enabled = settings_doc.get("group_moderation_enabled", False) if settings_doc else False

    if is_moderation_enabled:
        # Instead of adding to group.pending_requests for leader to approve
        # Or you can reject directly to keep it simple, since "đợi kiểm duyệt" could mean they can't join freely
        return {"status": "error", "data": {}, "message": "Không thể xin vào nhóm khi chế độ kiểm duyệt đang bật. Liên hệ Admin!"}

    group = await _find_group_or_404(group_id)

    if group.get("status") == "Pending":
       return {"status": "error", "data": {}, "message": "Nhóm đang chờ admin duyệt, chưa thể tham gia"}

    if not group.get("is_public", False):
        return {
            "status": "error",
            "data": {},
            "message": "Private group only accepts invited users",
        }

    if len(group.get("members", [])) >= MAX_GROUP_MEMBERS:
        return {"status": "error", "data": {}, "message": "Group is full"}

    user_id = current_user.get("_id")
    for request in group.get("pending_requests", []):
        if request.get("user_id") == user_id:
            return {"status": "error", "data": {}, "message": "Join request already sent"}

    join_request = {
        "user_id": user_id,
        "mssv": current_user.get("mssv"),
        "full_name": current_user.get("full_name"),
        "requested_at": _now_utc(),
    }

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$push": {"pending_requests": join_request}},
    )

    await _create_notification(
        user_id=group.get("leader_id"),
        sender_id=user_id,
        notification_type="join_request",
        message=f"{current_user.get('full_name')} gửi yêu cầu tham gia nhóm.",
        group_id=group_id,
        status="pending",
        link="/student/team",
        metadata={"request_user_id": user_id},
    )

    return {"status": "success", "data": {"request": join_request}, "message": ""}


@router.get("/{group_id}/join-requests")
async def list_join_requests(group_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    return {
        "status": "success",
        "data": {"pending_requests": group.get("pending_requests", [])},
        "message": "",
    }


@router.post("/{group_id}/join-requests/{user_id}/approve")
async def approve_join_request(group_id: str, user_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    pending_requests = group.get("pending_requests", [])
    request_item = next((item for item in pending_requests if item.get("user_id") == user_id), None)
    if not request_item:
        return {"status": "error", "data": {}, "message": "Join request not found"}

    if len(group.get("members", [])) >= MAX_GROUP_MEMBERS:
        return {"status": "error", "data": {}, "message": "Group is full"}

    user = await database[USERS_COLLECTION].find_one({"_id": user_id})
    if not user or user.get("group_id"):
        return {"status": "error", "data": {}, "message": "User cannot join this group"}

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {
            "$pull": {"pending_requests": {"user_id": user_id}},
            "$push": {"members": _build_member(user)},
        },
    )
    await database[USERS_COLLECTION].update_one({"_id": user_id}, {"$set": {"group_id": group_id}})

    await _create_notification(
        user_id=user_id,
        sender_id=current_user.get("_id"),
        notification_type="join_approved",
        message=f"Yêu cầu vào nhóm {group.get('name')} đã được chấp nhận.",
        group_id=group_id,
        status="sent",
        link="/student/team",
    )

    return {"status": "success", "data": {}, "message": ""}


@router.post("/{group_id}/join-requests/{user_id}/reject")
async def reject_join_request(group_id: str, user_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$pull": {"pending_requests": {"user_id": user_id}}},
    )

    await _create_notification(
        user_id=user_id,
        sender_id=current_user.get("_id"),
        notification_type="join_rejected",
        message=f"Yêu cầu vào nhóm {group.get('name')} đã bị từ chối.",
        group_id=group_id,
        status="rejected",
        link="/student/team",
    )

    return {"status": "success", "data": {}, "message": ""}


@router.post("/{group_id}/invite")
async def invite_user_to_group(
    group_id: str,
    payload: InviteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    from app.db.init_db import SETTINGS_COLLECTION
    settings_doc = await database[SETTINGS_COLLECTION].find_one({"_id": "moderation"})
    if settings_doc and settings_doc.get("group_moderation_enabled", False):
        return {"status": "error", "data": {}, "message": "Không thể mời người khác khi chế độ kiểm duyệt đang bật."}

    if len(group.get("members", [])) >= MAX_GROUP_MEMBERS:
        return {"status": "error", "data": {}, "message": "Group is full"}

    target_user = await database[USERS_COLLECTION].find_one({"mssv": payload.mssv.strip()})
    if not target_user:
        return {"status": "error", "data": {}, "message": "User not found"}
    if target_user.get("_id") == current_user.get("_id"):
        return {"status": "error", "data": {}, "message": "Cannot invite yourself"}
    if target_user.get("group_id"):
        return {"status": "error", "data": {}, "message": "User already has a group"}

    await _create_notification(
        user_id=target_user.get("_id"),
        sender_id=current_user.get("_id"),
        notification_type="invite",
        message=f"Bạn được mời vào nhóm {group.get('name')}.",
        group_id=group_id,
        status="pending",
        link="/student/team",
        metadata={
            "group_id": group_id,
            "group_name": group.get("name"),
            "inviter_name": current_user.get("full_name"),
            "inviter_id": current_user.get("_id"),
        },
    )

    return {"status": "success", "data": {}, "message": ""}


@router.get("/players/search")
async def search_player_by_mssv(
    mssv: str = Query(min_length=8, max_length=8),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    user = await database[USERS_COLLECTION].find_one({"mssv": mssv.strip()})

    if not user:
        return {"status": "success", "data": {"player": None}, "message": ""}

    return {
        "status": "success",
        "data": {
            "player": {
                "id": user.get("_id"),
                "mssv": user.get("mssv"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
                "has_group": bool(user.get("group_id")),
                "group_id": user.get("group_id"),
            }
        },
        "message": "",
    }


@router.post("/invites/{notification_id}/accept")
async def accept_invite(notification_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()

    from app.db.init_db import SETTINGS_COLLECTION
    settings_doc = await database[SETTINGS_COLLECTION].find_one({"_id": "moderation"})
    if settings_doc and settings_doc.get("group_moderation_enabled", False):
        return {"status": "error", "data": {}, "message": "Không thể vào nhóm khi chế độ kiểm duyệt đang bật."}

    invite = await database[NOTIFICATIONS_COLLECTION].find_one(
        {
            "_id": notification_id,
            "user_id": current_user.get("_id"),
            "type": "invite",
            "status": "pending",
        }
    )
    if not invite:
        return {"status": "error", "data": {}, "message": "Invite not found"}

    if current_user.get("group_id"):
        return {"status": "error", "data": {}, "message": "User already has a group"}

    group_id = invite.get("group_id")
    group = await _find_group_or_404(group_id)
    if len(group.get("members", [])) >= MAX_GROUP_MEMBERS:
        return {"status": "error", "data": {}, "message": "Group is full"}

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$push": {"members": _build_member(current_user)}},
    )
    await database[USERS_COLLECTION].update_one(
        {"_id": current_user.get("_id")},
        {"$set": {"group_id": group_id}},
    )
    await database[NOTIFICATIONS_COLLECTION].update_one(
        {"_id": notification_id},
        {"$set": {"status": "accepted", "is_read": True}},
    )

    await _create_notification(
        user_id=invite.get("sender_id"),
        sender_id=current_user.get("_id"),
        notification_type="invite_accepted",
        message=f"{current_user.get('full_name')} đã chấp nhận lời mời vào nhóm.",
        group_id=group_id,
        status="sent",
        link="/student/team",
    )

    return {"status": "success", "data": {}, "message": ""}


@router.post("/invites/{notification_id}/reject")
async def reject_invite(notification_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    invite = await database[NOTIFICATIONS_COLLECTION].find_one(
        {
            "_id": notification_id,
            "user_id": current_user.get("_id"),
            "type": "invite",
            "status": "pending",
        }
    )
    if not invite:
        return {"status": "error", "data": {}, "message": "Invite not found"}

    await database[NOTIFICATIONS_COLLECTION].update_one(
        {"_id": notification_id},
        {"$set": {"status": "rejected", "is_read": True}},
    )

    await _create_notification(
        user_id=invite.get("sender_id"),
        sender_id=current_user.get("_id"),
        notification_type="invite_rejected",
        message=f"{current_user.get('full_name')} đã từ chối lời mời vào nhóm.",
        group_id=invite.get("group_id"),
        status="sent",
        link="/student/team",
    )

    return {"status": "success", "data": {}, "message": ""}


@router.get("/notifications/me")
async def get_my_notifications(
    current_user: dict[str, Any] = Depends(get_current_user),
    unread_only: bool = Query(False),
):
    database = get_database()
    
    query = {"user_id": current_user.get("_id")}
    if unread_only:
        query["is_read"] = False
    
    notifications = await database[NOTIFICATIONS_COLLECTION].find(
        query
    ).sort("created_at", -1).to_list(length=100)
    
    # Enrich notifications with sender info
    enriched = []
    for notif in notifications:
        sender = await database[USERS_COLLECTION].find_one({"_id": notif.get("sender_id")})
        enriched.append({
            **notif,
            "sender_name": sender.get("full_name") if sender else "Hệ thống",
            "link": notif.get("link") or "/student/team",
        })
    
    return {"status": "success", "data": {"notifications": enriched}, "message": ""}


@router.patch("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict[str, Any] = Depends(get_current_user)):
    database = get_database()
    await database[NOTIFICATIONS_COLLECTION].update_many(
        {
            "user_id": current_user.get("_id"),
            "is_read": False,
        },
        {"$set": {"is_read": True}},
    )
    return {"status": "success", "data": {}, "message": ""}


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    
    result = await database[NOTIFICATIONS_COLLECTION].update_one(
        {
            "_id": notification_id,
            "user_id": current_user.get("_id"),
        },
        {"$set": {"is_read": True}},
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"status": "success", "data": {}, "message": ""}


@router.patch("/{group_id}/name")
async def rename_group(
    group_id: str,
    payload: RenameGroupRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$set": {"name": payload.name.strip()}},
    )

    return {"status": "success", "data": {}, "message": ""}


@router.delete("/{group_id}/members/{member_user_id}")
async def kick_group_member(
    group_id: str,
    member_user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    database = get_database()
    group = await _find_group_or_404(group_id)
    await _ensure_group_leader(group, current_user)

    if member_user_id == current_user.get("_id"):
        return {"status": "error", "data": {}, "message": "Leader cannot kick self"}

    await database[GROUPS_COLLECTION].update_one(
        {"_id": group_id},
        {"$pull": {"members": {"user_id": member_user_id}}},
    )
    await database[USERS_COLLECTION].update_one(
        {"_id": member_user_id},
        {"$set": {"group_id": None}},
    )

    await _create_notification(
        user_id=member_user_id,
        sender_id=current_user.get("_id"),
        notification_type="kicked",
        message=f"Bạn đã bị mời khỏi nhóm {group.get('name')}.",
        group_id=group_id,
        status="sent",
        link="/student/team",
    )

    return {"status": "success", "data": {}, "message": ""}
