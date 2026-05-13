from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.init_db import MATCHES_COLLECTION
from tests.conftest import agent_headers
from tests.test_agent_api import post_move, start_match

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def play_moves(client, match, moves):
    latest = None
    for side, x, y in moves:
        latest = await post_move(client, match, side, x, y)
        assert latest.json()["status"] == "success"
    return latest.json()["data"]


@pytest.mark.parametrize(
    "moves",
    [
        [("X", 0, 0), ("O", 0, 1), ("X", 1, 0), ("O", 0, 2), ("X", 2, 0), ("O", 0, 3), ("X", 3, 0), ("O", 0, 4), ("X", 4, 0)],
        [("X", 0, 0), ("O", 0, 1), ("X", 1, 1), ("O", 0, 2), ("X", 2, 2), ("O", 0, 3), ("X", 3, 3), ("O", 0, 4), ("X", 4, 4)],
        [("X", 4, 0), ("O", 1, 0), ("X", 3, 1), ("O", 1, 1), ("X", 2, 2), ("O", 1, 2), ("X", 1, 3), ("O", 1, 4), ("X", 0, 4)],
    ],
)
async def test_win_detection_vertical_and_diagonals(client, two_group_match, moves):
    match = two_group_match["match"]
    await start_match(client, match)
    data = await play_moves(client, match, moves)
    assert data["match_status"] == "finished"
    assert data["winner"] == "X"


async def test_four_in_row_and_gap_do_not_win(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)
    data = await play_moves(
        client,
        match,
        [("X", 0, 0), ("O", 1, 0), ("X", 0, 1), ("O", 1, 1), ("X", 0, 2), ("O", 1, 2), ("X", 0, 3)],
    )
    assert data["match_status"] == "playing"
    assert data["winner"] is None

    data = await play_moves(client, match, [("O", 1, 3), ("X", 0, 5)])
    assert data["match_status"] == "playing"
    assert data["winner"] is None


async def test_timeout_forfeit_board_encoding_and_turn_flip(client, db, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)
    moved = await post_move(client, match, "X", 0, 0)
    data = moved.json()["data"]
    assert data["board"][0][0] == 1
    assert data["turn"] == "O"

    await db[MATCHES_COLLECTION].update_one(
        {"_id": match["id"]},
        {"$set": {"turn_deadline_at": datetime.utcnow() - timedelta(seconds=1)}},
    )
    state = await client.get(
        "/api/v1/agent/state",
        headers=agent_headers(match["teams"]["O"]["team_id"], match["teams"]["O"]["api_key"]),
    )
    payload = state.json()["data"]
    assert payload["match_status"] == "finished"
    assert payload["winner"] == "X"


async def test_move_after_finished_is_rejected(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)
    await play_moves(
        client,
        match,
        [("X", 0, 0), ("O", 1, 0), ("X", 0, 1), ("O", 1, 1), ("X", 0, 2), ("O", 1, 2), ("X", 0, 3), ("O", 1, 3), ("X", 0, 4)],
    )
    rejected = await post_move(client, match, "O", 2, 2)
    assert rejected.json()["status"] == "error"
    assert rejected.json()["message"] == "Match is not playing"
