from __future__ import annotations

from pathlib import Path

import pytest

import main
from app.core.metrics import request_metrics
from tests.conftest import auth_headers, create_admin, login_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def test_metrics_snapshot_and_reset(client, db):
    await create_admin(db)
    token = await login_admin(client)
    await client.get("/api/v1/system/db/health")

    metrics = await client.get("/api/v1/admin/metrics", headers=auth_headers(token))
    assert metrics.json()["status"] == "success"
    assert metrics.json()["data"]

    reset = await client.post("/api/v1/admin/metrics/reset", headers=auth_headers(token))
    assert reset.json()["status"] == "success"

    forbidden = await client.get("/api/v1/admin/metrics")
    assert forbidden.status_code == 401


async def test_admin_approval_placeholders(client):
    approve = await client.post("/api/v1/admin/approve/A123")
    reject = await client.delete("/api/v1/admin/reject/A123")
    assert approve.json()["status"] == "error"
    assert approve.json()["message"] == "Not implemented"
    assert reject.json()["status"] == "error"


async def test_sdk_missing_files_return_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "SDK_INSTRUCTION_FILE", tmp_path / "missing.md")
    instruction = await client.get("/downloads/sdk/instruction")
    assert instruction.status_code == 404

    monkeypatch.setattr(main, "SDK_PACKAGE_FILES", (("missing.py", tmp_path / "missing.py"),))
    package = await client.get("/downloads/sdk/zip")
    assert package.status_code == 404


async def test_response_shapes_for_success_business_error_and_missing_auth(client, db):
    health = await client.get("/api/v1/system/db/health")
    assert set(["status", "data", "message"]).issubset(health.json())

    await create_admin(db)
    token = await login_admin(client)
    business_error = await client.post(
        "/api/v1/matches",
        headers=auth_headers(token),
        json={"x_team_id": "T1", "o_team_id": "T1", "start_time": "2030-01-01T00:00:00Z"},
    )
    assert business_error.json()["status"] == "error"
    assert "Traceback" not in business_error.text

    missing_auth = await client.get("/api/v1/groups/me")
    assert missing_auth.status_code == 401
    assert missing_auth.json()["status"] == "error"


async def test_metrics_reset_direct():
    request_metrics.observe(method="GET", path="/api/v1/test", status=200, elapsed_ms=1.0)
    assert request_metrics.snapshot()
    request_metrics.reset()
    assert request_metrics.snapshot()["total_keys"] == 0
