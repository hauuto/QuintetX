from __future__ import annotations

import pytest

from tests.conftest import auth_headers, create_admin, create_group, create_student, login_admin, login_student

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def test_admin_only_and_non_leader_authorization(client, db):
    await create_admin(db)
    admin_token = await login_admin(client)
    leader = await create_student(db, mssv="26500001")
    outsider = await create_student(db, mssv="26500002")
    group = await create_group(db, group_id="T6501SECU", leader=leader)
    outsider_token = await login_student(client, outsider["mssv"])

    delete_missing_as_student = await client.delete("/api/v1/matches/Mmissing", headers=auth_headers(outsider_token))
    assert delete_missing_as_student.json()["status"] == "error"

    approve = await client.post(
        f"/api/v1/groups/{group['_id']}/join-requests/{outsider['_id']}/approve",
        headers=auth_headers(outsider_token),
    )
    assert approve.status_code == 403

    kick = await client.delete(f"/api/v1/groups/{group['_id']}/members/{leader['_id']}", headers=auth_headers(outsider_token))
    assert kick.status_code == 403
    assert admin_token


async def test_match_payload_does_not_leak_api_keys(client, db):
    await create_admin(db)
    admin_token = await login_admin(client)
    leader_x = await create_student(db, mssv="26500003")
    leader_o = await create_student(db, mssv="26500004")
    group_x = await create_group(db, group_id="T6502KEYX", leader=leader_x)
    group_o = await create_group(db, group_id="T6503KEYO", leader=leader_o)
    token_x = await login_student(client, leader_x["mssv"])

    created = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={"x_team_id": group_x["_id"], "o_team_id": group_o["_id"], "start_time": "2030-01-01T00:00:00Z"},
    )
    match_id = created.json()["data"]["match"]["id"]
    detail = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(token_x))
    teams = detail.json()["data"]["match"]["teams"]
    assert "api_key" not in teams["X"]
    assert "api_key" not in teams["O"]


async def test_xss_and_nosql_like_payloads_do_not_execute_or_crash(client, db):
    user = await create_student(db, mssv="26500005")
    token = await login_student(client, user["mssv"])
    payload = "<script>alert(1)</script>"
    created = await client.post(
        "/api/v1/groups",
        headers=auth_headers(token),
        json={"name": payload, "description": "{'$ne': null}", "is_public": True},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "success"
    assert created.json()["data"]["group"]["name"] == payload
