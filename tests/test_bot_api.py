from __future__ import annotations

import pytest

from app.db.init_db import MATCHES_COLLECTION
from tests.conftest import agent_headers, auth_headers, create_group, create_student, login_student

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def create_started_bot_match(client, db):
    student = await create_student(db, mssv="26400001")
    await create_group(db, group_id="T6401BOTX", leader=student)
    token = await login_student(client, student["mssv"])
    created = await client.post("/api/v1/matches/bot", headers=auth_headers(token), json={})
    my_team = created.json()["data"]["my_team"]
    await client.post("/api/v1/agent/init", headers=agent_headers(my_team["id"], my_team["api_key"]))
    return created.json()["data"]["match"], my_team


async def test_greedy_bot_invalid_strategy_falls_back(client, db, monkeypatch):
    match, my_team = await create_started_bot_match(client, db)

    def invalid_strategy(_state):
        return (999, 999)

    monkeypatch.setattr("app.api.agent.greedy_strategy", invalid_strategy)
    moved = await client.post(
        "/api/v1/agent/move",
        headers=agent_headers(my_team["id"], my_team["api_key"]),
        json={"x": 0, "y": 0},
    )
    board = moved.json()["data"]["board"]
    assert board[0][0] == 1
    assert sum(cell == 2 for row in board for cell in row) == 1


async def test_greedy_bot_can_win(client, db, monkeypatch):
    match, my_team = await create_started_bot_match(client, db)
    board = [[0 for _ in range(40)] for _ in range(40)]
    for y in range(4):
        board[5][y] = 2
    await db[MATCHES_COLLECTION].update_one({"_id": match["id"]}, {"$set": {"board": board}})

    def winning_strategy(_state):
        return (5, 4)

    monkeypatch.setattr("app.api.agent.greedy_strategy", winning_strategy)
    moved = await client.post(
        "/api/v1/agent/move",
        headers=agent_headers(my_team["id"], my_team["api_key"]),
        json={"x": 0, "y": 0},
    )
    data = moved.json()["data"]
    assert data["match_status"] == "finished"
    assert data["winner"] == "O"


async def test_greedy_bot_full_board_draw(client, db, monkeypatch):
    match, my_team = await create_started_bot_match(client, db)
    board = [[2 for _ in range(40)] for _ in range(40)]
    board[0][0] = 0
    await db[MATCHES_COLLECTION].update_one({"_id": match["id"]}, {"$set": {"board": board}})

    def no_move(_state):
        return None

    monkeypatch.setattr("app.api.agent.greedy_strategy", no_move)
    moved = await client.post(
        "/api/v1/agent/move",
        headers=agent_headers(my_team["id"], my_team["api_key"]),
        json={"x": 0, "y": 0},
    )
    data = moved.json()["data"]
    assert data["match_status"] == "finished"
    assert data["winner"] is None
    assert any(event["payload"].get("reason") == "draw" for event in data["events"])
