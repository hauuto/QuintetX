from __future__ import annotations

import pytest

from app.db.init_db import MATCHES_COLLECTION
from tests.conftest import auth_headers, create_group, create_student, login_student

pytestmark = pytest.mark.asyncio


async def test_admin_create_match_and_reject_invalid_cases(client, db, admin_token):
    leader_x = await create_student(db, mssv="25200001")
    leader_o = await create_student(db, mssv="25200002")
    group_x = await create_group(db, group_id="T3001MATX", leader=leader_x)
    group_o = await create_group(db, group_id="T3002MATO", leader=leader_o)

    options = await client.get("/api/v1/matches/teams/options", headers=auth_headers(admin_token))
    assert options.json()["status"] == "success"
    assert len(options.json()["data"]["teams"]) == 2

    created = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={
            "x_team_id": group_x["_id"],
            "o_team_id": group_o["_id"],
            "start_time": "2030-01-01T00:00:00Z",
            "room_name": "Admin Match",
        },
    )
    payload = created.json()
    assert payload["status"] == "success"
    match = payload["data"]["match"]
    assert match["status"] == "waiting"
    assert match["teams"]["X"]["api_key"]
    assert match["teams"]["O"]["api_key"]
    assert "board" not in match

    same_team = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={
            "x_team_id": group_x["_id"],
            "o_team_id": group_x["_id"],
            "start_time": "2030-01-01T00:00:00Z",
        },
    )
    assert same_team.json()["status"] == "error"

    conflict = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={
            "x_team_id": group_x["_id"],
            "o_team_id": group_o["_id"],
            "start_time": "2030-01-02T00:00:00Z",
        },
    )
    assert conflict.json()["status"] == "error"


async def test_student_cannot_create_team_match_and_can_create_bot_match(client, db, admin_token):
    student = await create_student(db, mssv="25200003")
    group = await create_group(db, group_id="T3003BOTX", leader=student)
    student_token = await login_student(client, "25200003")

    forbidden = await client.post(
        "/api/v1/matches",
        headers=auth_headers(student_token),
        json={
            "x_team_id": group["_id"],
            "o_team_id": "TNOPE",
            "start_time": "2030-01-01T00:00:00Z",
        },
    )
    assert forbidden.json()["status"] == "error"

    bot = await client.post("/api/v1/matches/bot", headers=auth_headers(student_token), json={"room_name": "Bot Match"})
    payload = bot.json()
    assert payload["status"] == "success"
    assert payload["data"]["my_team"]["side"] == "X"
    assert payload["data"]["my_team"]["api_key"]
    assert payload["data"]["match"]["teams"]["O"]["is_connected"] is True


async def test_match_overview_me_summary_events_history_detail_delete(client, db, admin_token):
    leader_x = await create_student(db, mssv="25200004")
    leader_o = await create_student(db, mssv="25200005")
    group_x = await create_group(db, group_id="T3004OVRX", leader=leader_x)
    group_o = await create_group(db, group_id="T3005OVRO", leader=leader_o)
    token_x = await login_student(client, "25200004")

    created = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={
            "x_team_id": group_x["_id"],
            "o_team_id": group_o["_id"],
            "start_time": "2030-01-01T00:00:00Z",
            "room_name": "Overview Match",
        },
    )
    match_id = created.json()["data"]["match"]["id"]

    overview = await client.get("/api/v1/matches/overview", headers=auth_headers(token_x))
    assert overview.json()["status"] == "success"
    assert overview.json()["data"]["upcoming_matches"]

    me = await client.get("/api/v1/matches/me", headers=auth_headers(token_x))
    assert me.json()["data"]["my_current_match"]["id"] == match_id
    assert me.json()["data"]["my_team"]["side"] == "X"

    summary = await client.get("/api/v1/matches/me/summary?since_rev=0", headers=auth_headers(token_x))
    assert summary.json()["data"]["rev_changed"] is False

    events = await client.get(f"/api/v1/matches/{match_id}/events", headers=auth_headers(token_x))
    assert events.json()["data"]["events"][0]["type"] == "match_created"

    detail = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(token_x))
    assert detail.json()["data"]["match"]["board"]
    assert "api_key" not in detail.json()["data"]["match"]["teams"]["X"]

    await db[MATCHES_COLLECTION].update_one({"_id": match_id}, {"$set": {"status": "finished", "winner": "X"}})
    history = await client.get("/api/v1/matches/my/history", headers=auth_headers(token_x))
    assert history.json()["data"]["matches"][0]["id"] == match_id

    deleted = await client.delete(f"/api/v1/matches/{match_id}", headers=auth_headers(admin_token))
    assert deleted.json()["status"] == "success"
