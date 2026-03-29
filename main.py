from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.api.auth import router as auth_router
from app.api.agent import router as agent_router
from app.api.groups import router as groups_router
from app.api.matches import router as matches_router
from app.api.metrics import router as metrics_router
from app.core.config import settings
from app.core.metrics import request_metrics
from app.db.client import close_db, connect_db, get_database
from app.db.init_db import (
    GROUPS_COLLECTION,
    MATCHES_COLLECTION,
    SEED_GROUP_CODE_LIST,
    SEED_ROOM_NAME,
    SEED_USER_MSSV_LIST,
    USERS_COLLECTION,
    initialize_local_database,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await connect_db()
        await initialize_local_database()
    except Exception as exc:
        # Fail fast on startup when local MongoDB is unavailable or initialization fails.
        raise RuntimeError(
            "MongoDB startup initialization failed. "
            "Ensure local MongoDB is running and MONGODB_URI is correct."
        ) from exc

    yield

    await close_db()

app = FastAPI(
    title=settings.APP_NAME,
    description="Competitive Gomoku Platform",
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


@app.middleware("http")
async def collect_request_metrics(request: Request, call_next):
    import time

    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000.0

    try:
        path = request.url.path
        if "/api/v1/" in path:
            request_metrics.observe(
                method=request.method,
                path=path,
                status=response.status_code,
                elapsed_ms=elapsed_ms,
            )
    except Exception:
        # Metrics must never break requests.
        pass

    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "data": {}, "message": message},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "data": {"errors": exc.errors()}, "message": "Validation error"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    message = str(exc) if settings.DEBUG else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"status": "error", "data": {}, "message": message},
    )

templates = Jinja2Templates(directory="templates")
templates.env.globals["QX_MATCH_STEP_DELAY_MS"] = int(max(0.05, float(settings.TIME_PER_MOVE)) * 1000)
templates.env.globals["QX_MOVE_TIMEOUT_SECONDS"] = int(settings.MOVE_TIMEOUT_SECONDS)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(groups_router)
app.include_router(matches_router)
app.include_router(metrics_router)

EMPTY_MATCH = {
    "id": "",
    "room_name": "",
    "status": "waiting",
    "time_elapsed": "00:00",
    "teams": {
        "X": {"team_id": "", "name": "Đội X", "is_connected": False},
        "O": {"team_id": "", "name": "Đội O", "is_connected": False},
    },
    "history": [],
}

EMPTY_TEAM = {
    "id": "",
    "name": "",
    "api_key": "",
}


def _format_date(value: datetime | None) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _map_match_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "playing":
        return "Đang diễn ra"
    if normalized == "waiting":
        return "Chờ người chơi"
    if normalized == "finished":
        return "Kết thúc"
    return ""

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login_student.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login_student.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register_student.html", {"request": request})


@app.get("/401", response_class=HTMLResponse)
async def unauthorized_page(request: Request):
    return templates.TemplateResponse("401.html", {"request": request})

@app.get("/student/dashboard", response_class=HTMLResponse)
async def student_dashboard(request: Request):
    return templates.TemplateResponse("student/dashboard.html", {"request": request})

@app.get("/student/team", response_class=HTMLResponse)
async def student_team(request: Request):
    return templates.TemplateResponse("student/team.html", {"request": request})

@app.get("/student/match", response_class=HTMLResponse)
async def student_match(request: Request):
    return templates.TemplateResponse("student/match.html", {"request": request})

@app.get("/student/history", response_class=HTMLResponse)
async def student_history(request: Request):
    return templates.TemplateResponse("student/history.html", {"request": request, "matches": []})

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("login_admin.html", {"request": request})

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    database = get_database()
    teams_count = await database[GROUPS_COLLECTION].count_documents({})
    matches_count = await database[MATCHES_COLLECTION].count_documents({})
    active_rooms = await database[MATCHES_COLLECTION].count_documents({"status": {"$in": ["waiting", "playing"]}})

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "stats": {
                "teams": teams_count,
                "matches": matches_count,
                "rooms": active_rooms,
                "pending": 0,
            },
            "recent_activity": [],
        },
    )

# Placeholder routes for sidebar links
@app.get("/admin/teams", response_class=HTMLResponse)
async def admin_teams(request: Request):
    database = get_database()
    groups = await database[GROUPS_COLLECTION].find(
        {},
        {
            "_id": 1,
            "name": 1,
            "members": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).to_list(length=500)

    teams = []
    for group in groups:
        members = group.get("members") or []
        teams.append(
            {
                "id": group.get("_id", ""),
                "name": group.get("name", ""),
                "members_count": len(members),
                "status": "Active",
                "created_at": _format_date(group.get("created_at")),
            }
        )

    return templates.TemplateResponse("admin/teams.html", {"request": request, "teams": teams})


@app.get("/admin/rooms", response_class=HTMLResponse)
async def admin_rooms(request: Request):
    database = get_database()
    matches = await database[MATCHES_COLLECTION].find(
        {},
        {
            "_id": 1,
            "room_name": 1,
            "status": 1,
            "teams": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).to_list(length=300)

    team_ids: set[str] = set()
    for match in matches:
        teams = match.get("teams") or {}
        team_ids.add((teams.get("X") or {}).get("team_id", ""))
        team_ids.add((teams.get("O") or {}).get("team_id", ""))
    team_ids.discard("")

    group_name_map: dict[str, str] = {}
    if team_ids:
        async for group in database[GROUPS_COLLECTION].find(
            {"_id": {"$in": list(team_ids)}},
            {"_id": 1, "name": 1},
        ):
            group_name_map[group.get("_id")] = group.get("name", "")

    rooms = []
    for match in matches:
        teams = match.get("teams") or {}
        team_x_id = (teams.get("X") or {}).get("team_id")
        team_o_id = (teams.get("O") or {}).get("team_id")

        rooms.append(
            {
                "id": match.get("_id", ""),
                "name": match.get("room_name", ""),
                "team1": group_name_map.get(team_x_id, team_x_id) if team_x_id else None,
                "team2": group_name_map.get(team_o_id, team_o_id) if team_o_id else None,
                "status": _map_match_status(match.get("status")),
            }
        )

    return templates.TemplateResponse("admin/rooms.html", {"request": request, "rooms": rooms})

@app.get("/admin/match", response_class=HTMLResponse)
async def admin_match(request: Request):
    return templates.TemplateResponse("admin/match.html", {"request": request})

@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals(request: Request):
    return templates.TemplateResponse("admin/approvals.html", {"request": request, "pending_admins": []})

# API endpoints for admin approvals (Mock)
@app.post("/api/v1/admin/approve/{admin_id}")
async def approve_admin(admin_id: str):
    return {
        "status": "error",
        "data": {},
        "message": "Not implemented",
    }

@app.delete("/api/v1/admin/reject/{admin_id}")
async def reject_admin(admin_id: str):
    return {
        "status": "error",
        "data": {},
        "message": "Not implemented",
    }


@app.get("/api/v1/system/db/health")
async def db_health_check():
    try:
        database = get_database()
        ping_result = await database.command("ping")
        collections = sorted(await database.list_collection_names())

        return {
            "status": "success",
            "data": {
                "database": settings.DATABASE_NAME,
                "ping_ok": bool(ping_result.get("ok") == 1.0),
                "collections": collections,
            },
            "message": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "data": {
                "database": settings.DATABASE_NAME,
                "ping_ok": False,
            },
            "message": f"Database unavailable: {exc}",
        }


@app.get("/api/v1/system/db/seed-test")
async def db_seed_test():
    try:
        database = get_database()
        env_name = (settings.APP_ENV or "dev").strip().lower()

        seeded_users = await database[USERS_COLLECTION].count_documents(
            {"mssv": {"$in": SEED_USER_MSSV_LIST}}
        )
        seeded_groups = await database[GROUPS_COLLECTION].count_documents(
            {"group_code": {"$in": SEED_GROUP_CODE_LIST}}
        )
        test_room_matches = await database[MATCHES_COLLECTION].count_documents(
            {"room_name": SEED_ROOM_NAME}
        )

        admin_count = await database[USERS_COLLECTION].count_documents({"role": "admin", "username": settings.INITIAL_ADMIN_USERNAME})

        if env_name == "prod":
            checks = {
                "admin_seeded": admin_count >= 1,
            }
        else:
            checks = {
                "users_seeded": seeded_users == 3,
                "groups_seeded": seeded_groups == 2,
                "matches_seeded": test_room_matches == 0,
                "admin_seeded": admin_count >= 1,
            }
        passed = all(checks.values())

        return {
            "status": "success" if passed else "error",
            "data": {
                "expected": {
                    "users": 3 if env_name != "prod" else "n/a",
                    "groups": 2 if env_name != "prod" else "n/a",
                    "matches_room_test": 0 if env_name != "prod" else "n/a",
                    "admins": ">=1",
                },
                "actual": {
                    "users": seeded_users,
                    "groups": seeded_groups,
                    "matches_room_test": test_room_matches,
                    "admins": admin_count,
                },
                "checks": checks,
            },
            "message": "" if passed else "Seed validation failed",
        }
    except Exception as exc:
        return {
            "status": "error",
            "data": {},
            "message": f"Seed test failed: {exc}",
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
    )
