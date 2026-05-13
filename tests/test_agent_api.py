from __future__ import annotations

import pytest

from tests.conftest import agent_headers, auth_headers, create_group, create_student, login_student

pytestmark = pytest.mark.asyncio


async def start_match(client, match):
    x = match["teams"]["X"]
    o = match["teams"]["O"]
    init_x = await client.post("/api/v1/agent/init", headers=agent_headers(x["team_id"], x["api_key"]))
    init_o = await client.post("/api/v1/agent/init", headers=agent_headers(o["team_id"], o["api_key"]))
    assert init_x.status_code == 200
    assert init_o.status_code == 200
    return init_o.json()["data"]


async def post_move(client, match, side, x, y):
    team = match["teams"][side]
    return await client.post(
        "/api/v1/agent/move",
        headers=agent_headers(team["team_id"], team["api_key"]),
        json={"x": x, "y": y},
    )


async def test_agent_auth_and_init_starts_match(client, two_group_match):
    match = two_group_match["match"]

    missing = await client.post("/api/v1/agent/init")
    assert missing.status_code == 401

    invalid = await client.post("/api/v1/agent/init", headers=agent_headers("bad", "bad"))
    assert invalid.status_code == 401

    state = await start_match(client, match)
    assert state["match_status"] == "playing"
    assert state["turn"] == "X"


async def test_valid_move_updates_board_history_and_turn(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)

    moved = await post_move(client, match, "X", 0, 0)
    payload = moved.json()
    assert payload["status"] == "success"
    assert payload["data"]["board"][0][0] == 1
    assert payload["data"]["turn"] == "O"

    state = await client.get(
        "/api/v1/agent/state",
        headers=agent_headers(match["teams"]["O"]["team_id"], match["teams"]["O"]["api_key"]),
    )
    assert any(event["type"] == "move_accepted" for event in state.json()["data"]["events"])


async def test_invalid_moves_are_rejected(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)

    wrong_turn = await post_move(client, match, "O", 0, 0)
    assert wrong_turn.json()["status"] == "error"

    out_of_board = await post_move(client, match, "X", 40, 0)
    assert out_of_board.json()["status"] == "error"

    first = await post_move(client, match, "X", 0, 0)
    assert first.json()["status"] == "success"
    occupied = await post_move(client, match, "O", 0, 0)
    assert occupied.json()["status"] == "error"


async def test_horizontal_win_detection(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)

    moves = [
        ("X", 0, 0), ("O", 1, 0),
        ("X", 0, 1), ("O", 1, 1),
        ("X", 0, 2), ("O", 1, 2),
        ("X", 0, 3), ("O", 1, 3),
        ("X", 0, 4),
    ]
    latest = None
    for side, x, y in moves:
        latest = await post_move(client, match, side, x, y)
        assert latest.json()["status"] == "success"

    data = latest.json()["data"]
    assert data["match_status"] == "finished"
    assert data["winner"] == "X"
    assert any(event["type"] == "win_detected" for event in data["events"])


async def test_greedy_bot_auto_moves_after_student_move(client, db):
    student = await create_student(db, mssv="25300001")
    await create_group(db, group_id="T4001BOTX", leader=student)
    token = await login_student(client, "25300001")

    created = await client.post("/api/v1/matches/bot", headers=auth_headers(token), json={"room_name": "Bot Regression"})
    match = created.json()["data"]["match"]
    my_team = created.json()["data"]["my_team"]

    init = await client.post("/api/v1/agent/init", headers=agent_headers(my_team["id"], my_team["api_key"]))
    assert init.json()["data"]["match_status"] == "playing"

    moved = await client.post(
        "/api/v1/agent/move",
        headers=agent_headers(my_team["id"], my_team["api_key"]),
        json={"x": 0, "y": 0},
    )
    data = moved.json()["data"]
    assert data["board"][0][0] == 1
    assert sum(cell == 2 for row in data["board"] for cell in row) == 1
    assert data["turn"] == "X"
