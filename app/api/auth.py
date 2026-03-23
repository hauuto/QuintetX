from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import secrets

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.client import get_database
from app.db.init_db import USERS_COLLECTION

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class StudentRegisterRequest(BaseModel):
    mssv: str = Field(min_length=3, max_length=32)
    full_name: str = Field(min_length=1, max_length=120)
    class_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)


class StudentLoginRequest(BaseModel):
    mssv: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AdminLoginRequest(BaseModel):
    username_or_email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)


def _normalize_text(value: str) -> str:
    return value.strip()


@router.post("/register/student")
async def register_student(payload: StudentRegisterRequest):
    mssv = _normalize_text(payload.mssv)
    full_name = _normalize_text(payload.full_name)
    class_name = _normalize_text(payload.class_name)

    if payload.password != payload.confirm_password:
        return {
            "status": "error",
            "data": {},
            "message": "Password confirmation does not match",
        }

    database = get_database()
    users_collection = database[USERS_COLLECTION]

    existing_user = await users_collection.find_one({"mssv": mssv})
    if existing_user:
        return {
            "status": "error",
            "data": {},
            "message": "MSSV already exists",
        }

    user_id = str(uuid4())
    await users_collection.insert_one(
        {
            "_id": user_id,
            "mssv": mssv,
            "full_name": full_name,
            "class_name": class_name,
            "password_hash": hash_password(payload.password),
            "role": "student",
            "group_id": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    return {
        "status": "success",
        "data": {
            "user": {
                "id": user_id,
                "mssv": mssv,
                "full_name": full_name,
                "class_name": class_name,
                "role": "student",
            }
        },
        "message": "",
    }


@router.post("/login/student")
async def login_student(payload: StudentLoginRequest):
    mssv = _normalize_text(payload.mssv)

    database = get_database()
    users_collection = database[USERS_COLLECTION]

    user = await users_collection.find_one({"mssv": mssv, "role": "student"})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        return {
            "status": "error",
            "data": {},
            "message": "Invalid credentials",
        }

    access_token = secrets.token_urlsafe(32)

    return {
        "status": "success",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "user": {
                "id": user.get("_id"),
                "mssv": user.get("mssv"),
                "full_name": user.get("full_name"),
                "class_name": user.get("class_name"),
                "role": user.get("role"),
            },
        },
        "message": "",
    }


@router.post("/login/admin")
async def login_admin(payload: AdminLoginRequest):
    username_or_email = _normalize_text(payload.username_or_email)

    database = get_database()
    users_collection = database[USERS_COLLECTION]

    user = await users_collection.find_one(
        {
            "role": "admin",
            "$or": [
                {"username": username_or_email},
                {"email": username_or_email},
                {"mssv": username_or_email},
            ],
        }
    )

    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        return {
            "status": "error",
            "data": {},
            "message": "Invalid credentials",
        }

    access_token = secrets.token_urlsafe(32)

    return {
        "status": "success",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "user": {
                "id": user.get("_id"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
            },
        },
        "message": "",
    }
