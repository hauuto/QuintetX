from __future__ import annotations

import pytest

from app.db.init_db import GROUPS_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from tests.conftest import auth_headers, create_group, create_student, login_student

pytestmark = pytest.mark.asyncio


async def test_student_create_group_and_reject_second_group(client, db):
    await create_student(db, mssv="25100001")
    token = await login_student(client, "25100001")

    created = await client.post(
        "/api/v1/groups",
        headers=auth_headers(token),
        json={"name": "New Team", "description": "desc", "is_public": True},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "success"
    group = created.json()["data"]["group"]
    assert group["leader_id"] == "U25100001"
    assert group["members"][0]["user_id"] == "U25100001"

    second = await client.post(
        "/api/v1/groups",
        headers=auth_headers(token),
        json={"name": "Other Team", "description": "desc", "is_public": True},
    )
    assert second.json()["status"] == "error"


async def test_open_groups_join_request_and_leader_approve(client, db):
    leader = await create_student(db, mssv="25100002")
    joiner = await create_student(db, mssv="25100003")
    group = await create_group(db, group_id="T2001JOIN", leader=leader, name="Joinable")
    leader_token = await login_student(client, "25100002")
    joiner_token = await login_student(client, "25100003")

    open_groups = await client.get("/api/v1/groups/open-missing", headers=auth_headers(joiner_token))
    assert open_groups.status_code == 200
    assert any(item["id"] == group["_id"] for item in open_groups.json()["data"]["groups"])

    join = await client.post(f"/api/v1/groups/{group['_id']}/join", headers=auth_headers(joiner_token), json={})
    assert join.status_code == 200
    assert join.json()["status"] == "success"

    requests = await client.get(f"/api/v1/groups/{group['_id']}/join-requests", headers=auth_headers(leader_token))
    assert requests.json()["data"]["pending_requests"][0]["user_id"] == joiner["_id"]

    approve = await client.post(
        f"/api/v1/groups/{group['_id']}/join-requests/{joiner['_id']}/approve",
        headers=auth_headers(leader_token),
    )
    assert approve.json()["status"] == "success"

    updated_group = await db[GROUPS_COLLECTION].find_one({"_id": group["_id"]})
    updated_joiner = await db[USERS_COLLECTION].find_one({"_id": joiner["_id"]})
    assert any(member["user_id"] == joiner["_id"] for member in updated_group["members"])
    assert updated_joiner["group_id"] == group["_id"]


async def test_non_leader_cannot_manage_group(client, db):
    leader = await create_student(db, mssv="25100004")
    outsider = await create_student(db, mssv="25100005")
    group = await create_group(db, group_id="T2002AUTH", leader=leader)
    outsider_token = await login_student(client, "25100005")

    rename = await client.patch(
        f"/api/v1/groups/{group['_id']}/name",
        headers=auth_headers(outsider_token),
        json={"name": "Hacked"},
    )
    assert rename.status_code == 403

    invite = await client.post(
        f"/api/v1/groups/{group['_id']}/invite",
        headers=auth_headers(outsider_token),
        json={"mssv": "25100005"},
    )
    assert invite.status_code == 403


async def test_invite_accept_reject_and_notifications(client, db):
    leader = await create_student(db, mssv="25100006")
    target = await create_student(db, mssv="25100007")
    group = await create_group(db, group_id="T2003INVT", leader=leader)
    leader_token = await login_student(client, "25100006")
    target_token = await login_student(client, "25100007")

    invite = await client.post(
        f"/api/v1/groups/{group['_id']}/invite",
        headers=auth_headers(leader_token),
        json={"mssv": target["mssv"]},
    )
    assert invite.json()["status"] == "success"

    notifications = await client.get("/api/v1/groups/notifications/me", headers=auth_headers(target_token))
    invite_id = notifications.json()["data"]["notifications"][0]["_id"]

    accept = await client.post(f"/api/v1/groups/invites/{invite_id}/accept", headers=auth_headers(target_token))
    assert accept.json()["status"] == "success"
    updated_target = await db[USERS_COLLECTION].find_one({"_id": target["_id"]})
    assert updated_target["group_id"] == group["_id"]

    read_all = await client.patch("/api/v1/groups/notifications/read-all", headers=auth_headers(target_token))
    assert read_all.json()["status"] == "success"
    unread_count = await db[NOTIFICATIONS_COLLECTION].count_documents({"user_id": target["_id"], "is_read": False})
    assert unread_count == 0
