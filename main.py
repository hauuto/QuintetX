from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Competitive Gomoku Platform",
    version=settings.VERSION,
    debug=settings.DEBUG
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login_student.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login_student.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register_student.html", {"request": request})

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
    return templates.TemplateResponse("student/history.html", {"request": request})

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("login_admin.html", {"request": request})

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})

# Placeholder routes for sidebar links
@app.get("/admin/teams", response_class=HTMLResponse)
async def admin_teams(request: Request):
    # Dummy data for teams
    teams = [
        {"id": "T001", "name": "Dragon Slayer", "members_count": 5, "status": "Active", "created_at": "2023-10-01"},
        {"id": "T002", "name": "Code Warriors", "members_count": 4, "status": "Active", "created_at": "2023-10-02"},
        {"id": "T003", "name": "AI Masters", "members_count": 3, "status": "Inactive", "created_at": "2023-10-03"},
        {"id": "T004", "name": "Gomoku Pros", "members_count": 5, "status": "Active", "created_at": "2023-10-05"},
        {"id": "T005", "name": "Strategy Kings", "members_count": 2, "status": "Pending", "created_at": "2023-10-06"},
    ]
    return templates.TemplateResponse("admin/teams.html", {"request": request, "teams": teams})


@app.get("/admin/rooms", response_class=HTMLResponse)
async def admin_rooms(request: Request):
    # Mock data for rooms
    rooms = [
        {"id": "1001", "name": "Room A-01", "team1": "Dragon Slayer", "team2": "Code Warriors", "status": "Đang diễn ra"},
        {"id": "1002", "name": "Room B-02", "team1": "AI Masters", "team2": "Gomoku Pros", "status": "Kết thúc"},
        {"id": "1003", "name": "Room C-03", "team1": "Strategy Kings", "team2": None, "status": "Chờ người chơi"},
        {"id": "1004", "name": "Trận Chung Kết", "team1": None, "team2": None, "status": "Chờ người chơi"},
    ]
    return templates.TemplateResponse("admin/rooms.html", {"request": request, "rooms": rooms})

@app.get("/admin/match", response_class=HTMLResponse)
async def admin_match(request: Request):
    return templates.TemplateResponse("admin/match.html", {"request": request})

@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals(request: Request):
    # Mock data for pending admins
    pending_admins = [
        {"id": "a001", "username": "tutor_minh", "email": "minh.nguyen@example.com", "created_at": "2023-10-10 08:30", "status": "pending"},
        {"id": "a002", "username": "ta_hoa", "email": "hoa.tran@example.com", "created_at": "2023-10-11 14:15", "status": "pending"},
         {"id": "a003", "username": "lab_assist_b", "email": "assist.b@example.com", "created_at": "2023-10-12 09:00", "status": "pending"},
    ]
    return templates.TemplateResponse("admin/approvals.html", {"request": request, "pending_admins": pending_admins})

# API endpoints for admin approvals (Mock)
@app.post("/api/v1/admin/approve/{admin_id}")
async def approve_admin(admin_id: str):
    # TODO: Implement DB update logic here
    return {"status": "success", "message": f"Admin {admin_id} approved"}

@app.delete("/api/v1/admin/reject/{admin_id}")
async def reject_admin(admin_id: str):
    # TODO: Implement DB delete logic here
    return {"status": "success", "message": f"Admin request {admin_id} rejected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8000, reload=True)
