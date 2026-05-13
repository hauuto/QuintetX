from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.init_db import MATCHES_COLLECTION
from tests.conftest import auth_headers, create_admin, create_group, create_student, login_admin, login_student

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def setup_student_group(db, mssv: str, group_id: str):
    user = await create_student(db, mssv=mssv)
    group = await create_group(db, group_id=group_id, leader=user)
    return user, group


async def test_match_negative_admin_student_cases(client, db):
    await create_admin(db)
    admin_token = await login_admin(client)
    student, group_x = await setup_student_group(db, "26200001", "T6201MATX")
    _, group_o = await setup_student_group(db, "26200002", "T6202MATO")
    student_token = await login_student(client, student["mssv"])

    options_forbidden = await client.get("/api/v1/matches/teams/options", headers=auth_headers(student_token))
    assert options_forbidden.json()["status"] == "error"

    missing_team = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={"x_team_id": group_x["_id"], "o_team_id": "TNOPE", "start_time": "2030-01-01T00:00:00Z"},
    )
    assert missing_team.json()["status"] == "error"

    invalid_time = await client.post(
        "/api/v1/matches",
        headers=auth_headers(admin_token),
        json={"x_team_id": group_x["_id"], "o_team_id": group_o["_id"], "start_time": "not-time"},
    )
    assert invalid_time.json()["status"] == "error"

    no_group = await create_student(db, mssv="26200003")
    no_group_token = await login_student(client, no_group["mssv"])
    bot_no_group = await client.post("/api/v1/matches/bot", headers=auth_headers(no_group_token), json={})
    assert bot_no_group.json()["status"] == "error"

    bot_admin = await client.post("/api/v1/matches/bot", headers=auth_headers(admin_token), json={})
    assert bot_admin.json()["status"] == "error"


async def test_match_bot_conflict_summary_rev_events_limit_delete_errors(client, db):
    await create_admin(db)
    admin_token = await login_admin(client)
    student, group = await setup_student_group(db, "26200004", "T6204BOTX")
    token = await login_student(client, student["mssv"])

    bot = await client.post("/api/v1/matches/bot", headers=auth_headers(token), json={})
    assert bot.json()["status"] == "success"
    match_id = bot.json()["data"]["match"]["id"]

    conflict = await client.post("/api/v1/matches/bot", headers=auth_headers(token), json={})
    assert conflict.json()["status"] == "error"

    summary_false = await client.get("/api/v1/matches/me/summary?since_rev=0", headers=auth_headers(token))
    assert summary_false.json()["data"]["rev_changed"] is False
    await db[MATCHES_COLLECTION].update_one({"_id": match_id}, {"$inc": {"rev": 1}})
    summary_true = await client.get("/api/v1/matches/me/summary?since_rev=0", headers=auth_headers(token))
    assert summary_true.json()["data"]["rev_changed"] is True

    await db[MATCHES_COLLECTION].update_one(
        {"_id": match_id},
        {"$push": {"events": {"$each": [{"type": "e", "message": str(i), "created_at": datetime.now(timezone.utc)} for i in range(5)]}}},
    )
    limited = await client.get(f"/api/v1/matches/{match_id}/events?limit=2", headers=auth_headers(token))
    assert len(limited.json()["data"]["events"]) == 2

    student_delete = await client.delete(f"/api/v1/matches/{match_id}", headers=auth_headers(token))
    assert student_delete.json()["status"] == "error"
    missing_delete = await client.delete("/api/v1/matches/Mmissing", headers=auth_headers(admin_token))
    assert missing_delete.json()["status"] == "error"


async def test_match_history_empty_for_student_without_group(client, db):
    user = await create_student(db, mssv="26200005")
    token = await login_student(client, user["mssv"])
    history = await client.get("/api/v1/matches/my/history", headers=auth_headers(token))
    assert history.json()["data"]["matches"] == []
