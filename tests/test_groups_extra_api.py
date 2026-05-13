from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.init_db import GROUPS_COLLECTION, NOTIFICATIONS_COLLECTION, USERS_COLLECTION
from tests.conftest import auth_headers, create_group, create_student, login_student

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


def member_doc(user):
    return {"user_id": user["_id"], "mssv": user["mssv"], "full_name": user["full_name"], "joined_at": datetime.now(timezone.utc)}


async def test_group_dashboard_search_pagination_and_player_search(client, db):
    no_group = await create_student(db, mssv="26100001")
    leader = await create_student(db, mssv="26100002")
    await create_group(db, group_id="T6100ALFA", leader=leader, name="Alpha Search")
    token = await login_student(client, no_group["mssv"])

    dashboard = await client.get("/api/v1/groups/me/dashboard", headers=auth_headers(token))
    assert dashboard.json()["data"]["team"] is None

    search = await client.get("/api/v1/groups/open-missing?q=Alpha&page=1&page_size=1", headers=auth_headers(token))
    data = search.json()["data"]
    assert data["groups"][0]["name"] == "Alpha Search"
    assert data["pagination"]["page_size"] == 1

    found = await client.get(f"/api/v1/groups/players/search?mssv={leader['mssv']}", headers=auth_headers(token))
    assert found.json()["data"]["player"]["id"] == leader["_id"]
    missing = await client.get("/api/v1/groups/players/search?mssv=26999999", headers=auth_headers(token))
    assert missing.json()["data"]["player"] is None


async def test_join_reject_private_full_duplicate_and_leader_reject(client, db):
    leader = await create_student(db, mssv="26100003")
    joiner = await create_student(db, mssv="26100004")
    private_group = await create_group(db, group_id="T6101PRIV", leader=leader, is_public=False)
    joiner_token = await login_student(client, joiner["mssv"])

    private_join = await client.post(f"/api/v1/groups/{private_group['_id']}/join", headers=auth_headers(joiner_token), json={})
    assert private_join.json()["status"] == "error"

    full_leader = await create_student(db, mssv="26100005")
    extra_members = [member_doc(full_leader)]
    for i in range(6, 11):
        extra_members.append(member_doc(await create_student(db, mssv=f"261000{i:02d}")))
    full_group = await create_group(db, group_id="T6102FULL", leader=full_leader, members=extra_members)
    full_join = await client.post(f"/api/v1/groups/{full_group['_id']}/join", headers=auth_headers(joiner_token), json={})
    assert full_join.json()["status"] == "error"

    public_group = await create_group(db, group_id="T6103DUPE", leader=leader, name="Public")
    first = await client.post(f"/api/v1/groups/{public_group['_id']}/join", headers=auth_headers(joiner_token), json={})
    second = await client.post(f"/api/v1/groups/{public_group['_id']}/join", headers=auth_headers(joiner_token), json={})
    assert first.json()["status"] == "success"
    assert second.json()["status"] == "error"

    leader_token = await login_student(client, leader["mssv"])
    reject = await client.post(
        f"/api/v1/groups/{public_group['_id']}/join-requests/{joiner['_id']}/reject",
        headers=auth_headers(leader_token),
    )
    assert reject.json()["status"] == "success"
    updated = await db[GROUPS_COLLECTION].find_one({"_id": public_group["_id"]})
    assert updated["pending_requests"] == []


async def test_invite_negative_reject_rename_and_kick(client, db):
    leader = await create_student(db, mssv="26100011")
    target = await create_student(db, mssv="26100012")
    grouped = await create_student(db, mssv="26100013")
    group = await create_group(db, group_id="T6104MGMT", leader=leader)
    other_group = await create_group(db, group_id="T6105OTHR", leader=grouped)
    leader_token = await login_student(client, leader["mssv"])
    target_token = await login_student(client, target["mssv"])

    not_found = await client.post(f"/api/v1/groups/{group['_id']}/invite", headers=auth_headers(leader_token), json={"mssv": "26999999"})
    assert not_found.json()["status"] == "error"
    self_invite = await client.post(f"/api/v1/groups/{group['_id']}/invite", headers=auth_headers(leader_token), json={"mssv": leader["mssv"]})
    assert self_invite.json()["status"] == "error"
    already_grouped = await client.post(f"/api/v1/groups/{group['_id']}/invite", headers=auth_headers(leader_token), json={"mssv": grouped["mssv"]})
    assert already_grouped.json()["status"] == "error"

    invite = await client.post(f"/api/v1/groups/{group['_id']}/invite", headers=auth_headers(leader_token), json={"mssv": target["mssv"]})
    assert invite.json()["status"] == "success"
    notifications = await client.get("/api/v1/groups/notifications/me?unread_only=true", headers=auth_headers(target_token))
    invite_id = notifications.json()["data"]["notifications"][0]["_id"]
    single_read = await client.patch(f"/api/v1/groups/notifications/{invite_id}/read", headers=auth_headers(target_token))
    assert single_read.json()["status"] == "success"
    reject = await client.post(f"/api/v1/groups/invites/{invite_id}/reject", headers=auth_headers(target_token))
    assert reject.json()["status"] == "success"
    unknown = await client.post("/api/v1/groups/invites/N0000missing/reject", headers=auth_headers(target_token))
    assert unknown.json()["status"] == "error"

    rename = await client.patch(f"/api/v1/groups/{group['_id']}/name", headers=auth_headers(leader_token), json={"name": "Renamed"})
    assert rename.json()["status"] == "success"
    assert (await db[GROUPS_COLLECTION].find_one({"_id": group["_id"]}))["name"] == "Renamed"

    await db[GROUPS_COLLECTION].update_one({"_id": group["_id"]}, {"$push": {"members": member_doc(target)}})
    await db[USERS_COLLECTION].update_one({"_id": target["_id"]}, {"$set": {"group_id": group["_id"]}})
    kick = await client.delete(f"/api/v1/groups/{group['_id']}/members/{target['_id']}", headers=auth_headers(leader_token))
    assert kick.json()["status"] == "success"
    assert (await db[USERS_COLLECTION].find_one({"_id": target["_id"]}))["group_id"] is None
    kick_self = await client.delete(f"/api/v1/groups/{group['_id']}/members/{leader['_id']}", headers=auth_headers(leader_token))
    assert kick_self.json()["status"] == "error"

    cross_read = await client.patch(f"/api/v1/groups/notifications/{invite_id}/read", headers=auth_headers(leader_token))
    assert cross_read.status_code == 404
    assert await db[NOTIFICATIONS_COLLECTION].count_documents({}) >= 1
    assert other_group["_id"]
