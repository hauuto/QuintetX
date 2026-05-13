from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_db_health_and_seed_test(client):
    health = await client.get("/api/v1/system/db/health")
    assert health.status_code == 200
    assert health.json()["status"] == "success"
    assert health.json()["data"]["ping_ok"] is True

    seed = await client.get("/api/v1/system/db/seed-test")
    assert seed.status_code == 200
    assert seed.json()["status"] in {"success", "error"}
    assert "checks" in seed.json().get("data", {})


async def test_sdk_downloads(client):
    instruction = await client.get("/downloads/sdk/instruction")
    assert instruction.status_code == 200
    assert "SDK" in instruction.text or "QuintetX" in instruction.text

    package = await client.get("/downloads/sdk/zip")
    assert package.status_code == 200
    assert package.headers["content-type"] == "application/zip"
    assert package.content


async def test_template_routes_smoke(client):
    routes = [
        "/",
        "/login",
        "/register",
        "/401",
        "/student/dashboard",
        "/student/team",
        "/student/match",
        "/student/history",
        "/student/instructions",
        "/admin/login",
        "/admin/dashboard",
        "/admin/teams",
        "/admin/rooms",
        "/admin/match",
        "/admin/approvals",
    ]

    for route in routes:
        response = await client.get(route)
        assert response.status_code == 200, route
        assert "text/html" in response.headers.get("content-type", "")


async def test_validation_error_response_shape(client):
    response = await client.post("/api/v1/auth/register/student", json={"mssv": "1"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["status"] == "error"
    assert "errors" in payload["data"]
