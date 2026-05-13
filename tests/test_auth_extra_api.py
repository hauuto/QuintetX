from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from tests.conftest import auth_headers, create_student

pytestmark = [pytest.mark.asyncio, pytest.mark.api]


async def test_auth_rejects_short_mssv_and_invalid_login_mssv(client):
    short_register = await client.post(
        "/api/v1/auth/register/student",
        json={
            "mssv": "123",
            "full_name": "Short MSSV",
            "class_name": "D21",
            "password": "Pass1234",
            "confirm_password": "Pass1234",
        },
    )
    assert short_register.status_code == 422

    invalid_login = await client.post("/api/v1/auth/login/student", json={"mssv": "abcdefgh", "password": "Pass1234"})
    assert invalid_login.status_code == 200
    assert invalid_login.json()["status"] == "error"


async def test_expired_jwt_is_rejected(client, db):
    user = await create_student(db, mssv="25990001")
    expired_token = jwt.encode(
        {"sub": user["_id"], "role": "student", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = await client.get("/api/v1/groups/me", headers=auth_headers(expired_token))
    assert response.status_code == 401
    assert response.json()["status"] == "error"
