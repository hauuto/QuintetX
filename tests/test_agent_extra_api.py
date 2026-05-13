from __future__ import annotations

import pytest

from tests.conftest import agent_headers
from tests.test_agent_api import post_move, start_match

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def test_heartbeat_updates_agent_state(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)
    x = match["teams"]["X"]
    heartbeat = await client.post("/api/v1/agent/heartbeat", headers=agent_headers(x["team_id"], x["api_key"]))
    assert heartbeat.json()["status"] == "success"
    assert heartbeat.json()["data"]["side"] == "X"


async def test_move_while_waiting_is_rejected(client, two_group_match):
    match = two_group_match["match"]
    x = match["teams"]["X"]
    await client.post("/api/v1/agent/init", headers=agent_headers(x["team_id"], x["api_key"]))
    move = await post_move(client, match, "X", 0, 0)
    assert move.json()["status"] == "error"
    assert move.json()["message"] == "Match is not playing"


async def test_multi_move_history_and_rev_consistency(client, two_group_match):
    match = two_group_match["match"]
    await start_match(client, match)
    first = await post_move(client, match, "X", 0, 0)
    second = await post_move(client, match, "O", 1, 0)
    assert second.json()["data"]["board"][0][0] == 1
    assert second.json()["data"]["board"][1][0] == 2
    assert len([e for e in second.json()["data"]["events"] if e["type"] == "move_accepted"]) >= 2


async def test_finished_init_returns_state(client, db, two_group_match):
    match = two_group_match["match"]
    await db["matches"].update_one({"_id": match["id"]}, {"$set": {"status": "finished", "winner": "X"}})
    x = match["teams"]["X"]
    response = await client.post("/api/v1/agent/init", headers=agent_headers(x["team_id"], x["api_key"]))
    assert response.json()["status"] == "success"
    assert response.json()["data"]["match_status"] == "finished"
