from __future__ import annotations

import pytest

from tests.conftest import auth_headers, create_admin, create_student

pytestmark = pytest.mark.asyncio


async def test_register_student_success(client):
    response = await client.post(
        "/api/v1/auth/register/student",
        json={
            "mssv": "25000001",
            "full_name": "Nguyen Van Test",
            "class_name": "D21CQCN01-N",
            "password": "Pass1234",
            "confirm_password": "Pass1234",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["user"]["id"] == "U25000001"


async def test_register_rejects_invalid_duplicate_and_password_mismatch(client, db):
    invalid = await client.post(
        "/api/v1/auth/register/student",
        json={
            "mssv": "abcdef12",
            "full_name": "Invalid",
            "class_name": "D21",
            "password": "Pass1234",
            "confirm_password": "Pass1234",
        },
    )
    assert invalid.json()["status"] == "error"

    mismatch = await client.post(
        "/api/v1/auth/register/student",
        json={
            "mssv": "25000002",
            "full_name": "Mismatch",
            "class_name": "D21",
            "password": "Pass1234",
            "confirm_password": "Other1234",
        },
    )
    assert mismatch.json()["status"] == "error"

    await create_student(db, mssv="25000003")
    duplicate = await client.post(
        "/api/v1/auth/register/student",
        json={
            "mssv": "25000003",
            "full_name": "Duplicate",
            "class_name": "D21",
            "password": "Pass1234",
            "confirm_password": "Pass1234",
        },
    )
    assert duplicate.json()["status"] == "error"


async def test_student_login_success_and_failure(client, db):
    await create_student(db, mssv="25000004")

    ok = await client.post("/api/v1/auth/login/student", json={"mssv": "25000004", "password": "Pass1234"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "success"
    assert ok.json()["data"]["user"]["role"] == "student"
    assert ok.json()["data"]["access_token"]

    bad = await client.post("/api/v1/auth/login/student", json={"mssv": "25000004", "password": "wrong"})
    assert bad.status_code == 200
    assert bad.json()["status"] == "error"


async def test_admin_login_success_and_failure(client, db):
    await create_admin(db)

    ok = await client.post("/api/v1/auth/login/admin", json={"username_or_email": "admin", "password": "admin"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "success"
    assert ok.json()["data"]["user"]["role"] == "admin"

    bad = await client.post("/api/v1/auth/login/admin", json={"username_or_email": "admin", "password": "wrong"})
    assert bad.status_code == 200
    assert bad.json()["status"] == "error"


async def test_protected_endpoint_requires_valid_bearer(client, db):
    missing = await client.get("/api/v1/groups/me")
    assert missing.status_code == 401
    assert missing.json()["status"] == "error"

    invalid = await client.get("/api/v1/groups/me", headers=auth_headers("not-a-token"))
    assert invalid.status_code == 401

    await create_student(db, mssv="25000005")
    login = await client.post("/api/v1/auth/login/student", json={"mssv": "25000005", "password": "Pass1234"})
    token = login.json()["data"]["access_token"]
    ok = await client.get("/api/v1/groups/me", headers=auth_headers(token))
    assert ok.status_code == 200
    assert ok.json()["status"] == "success"
