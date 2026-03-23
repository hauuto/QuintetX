# MISSION
You are an expert Full-Stack Web Developer and System Architect. Your task is to assist in developing **QuintetX**, a competitive 40x40 Gomoku (Caro) web platform inspired by Procon formatting, built for classroom-scale AI agent competitions.

---

# SYSTEM ARCHITECTURE
1. **Web Platform (Central Server)**: FastAPI + MongoDB. Handles User/Team management, Match orchestration (Admin), and real-time visualization (WebSockets).
2. **Local AI Agents (Client side)**: Python scripts developed by students. They authenticate via `api_key` + `team_id`, poll the server for state, and push moves.

---

# TECH STACK
- **Backend**: Python (FastAPI + Motor for Async MongoDB + Pydantic v2)
- **Frontend**: HTML + Jinja2 + Alpine.js (CDN) + Tailwind CSS (CDN)
- **Real-time**: WebSockets (FastAPI built-in) for Dashboard updates
- **Database**: MongoDB (NoSQL)
- **No Node.js / No build step required**

---

# CORE DOMAIN RULES
- Board: 40x40 grid, strictly managed coordinates
- Pieces: X (Blue) and O (Red)
- Match Flow: Server initializes → Agent A pulls state & pushes move → Server validates → Agent B → repeat
- Security: Agents authenticate via Group Tokens. Agents CANNOT modify game state directly.
- Each team has exactly 1 agent (API endpoint)
- Only Admin can create rooms. Students cannot.

---

# DATABASE SCHEMA (MongoDB - Async)
All DB calls must use `motor.motor_asyncio`.

## Collection: `matches`
```json
{
    "_id": "uuid_string",
    "room_name": "string",
    "status": "waiting | playing | finished",
    "board": [[0, ...], ...],
    "teams": {
        "X": { "team_id": "T01", "api_key": "unique_key_x", "is_connected": false },
        "O": { "team_id": "T02", "api_key": "unique_key_o", "is_connected": false }
    },
    "current_turn": "X",
    "winner": null,
    "history": [{"x": int, "y": int, "p": "X|O", "t": "timestamp"}]
}
```

---

# SERVER-SIDE LOGIC (FastAPI)

## Authentication & Initialization
Security: Agents must send `X-API-Key` and `X-Team-ID` in request headers.

**Endpoint**: `POST /api/v1/agent/init`
- Validate `api_key` matches `team_id` for a specific match
- Set `teams.[SIDE].is_connected = true`
- Broadcast to Frontend via WebSocket that Agent is "Ready"

## Match Flow & Validation

**Endpoint**: `GET /api/v1/agent/state`
- Returns: `{ "board": [...], "turn": "X|O", "match_status": "..." }`

**Endpoint**: `POST /api/v1/agent/move`
- Payload: `{ "x": int, "y": int }`
- **Validation Rules**:
  - Only accept if `match_status == "playing"`
  - Only accept if it's the requester's turn
  - Coordinate `(x, y)` must be `0 <= val < 40` and cell must be empty
  - Run 5-in-a-row check (Horizontal, Vertical, Diagonal) after each move
  - If win detected, set `status = "finished"` and `winner = SIDE`

## Agent Health Check

**Endpoint**: `POST /api/v1/agent/heartbeat`
- Agent gửi heartbeat định kỳ mỗi **5 giây** (cấu hình qua `HEARTBEAT_INTERVAL` trong `config.py`)
- Server cập nhật field `teams.[SIDE].last_heartbeat = now()` và `teams.[SIDE].is_connected = true`
- Không yêu cầu body, chỉ cần headers `X-API-Key` + `X-Team-ID`
- Trả về: `{ "status": "success", "data": { "side": "X|O", "ts": "<timestamp>" }, "message": "" }`

### Server-side Background Monitor
Server chạy một **async background task** (`asyncio.create_task`) khi match bắt đầu, kiểm tra heartbeat mỗi `HEARTBEAT_CHECK_INTERVAL` giây (mặc định 3s):

```
Nếu now() - last_heartbeat > HEARTBEAT_TIMEOUT (mặc định 15s):
    → set teams.[SIDE].is_connected = false
    → Broadcast WebSocket event "agent_disconnected" với payload { side, team_id }
Nếu kết nối khôi phục (heartbeat đến lại):
    → set teams.[SIDE].is_connected = true
    → Broadcast WebSocket event "agent_reconnected" với payload { side, team_id }
```

### Config values (thêm vào `app/core/config.py`)
```python
HEARTBEAT_INTERVAL: float = 5.0       # SDK gửi mỗi N giây
HEARTBEAT_TIMEOUT: float = 15.0       # Quá N giây không có heartbeat → offline
HEARTBEAT_CHECK_INTERVAL: float = 3.0 # Server poll DB mỗi N giây
```

### Database Schema — cập nhật field `teams`
```json
"teams": {
    "X": {
        "team_id": "T01",
        "api_key": "unique_key_x",
        "is_connected": false,
        "last_heartbeat": null
    },
    "O": {
        "team_id": "T02",
        "api_key": "unique_key_o",
        "is_connected": false,
        "last_heartbeat": null
    }
}
```

### WebSocket Events broadcast tới Frontend
| Event | Payload | Ý nghĩa |
|---|---|---|
| `agent_connected` | `{ side, team_id }` | Agent vừa init thành công |
| `agent_disconnected` | `{ side, team_id }` | Heartbeat timeout |
| `agent_reconnected` | `{ side, team_id }` | Heartbeat khôi phục |

### Frontend hiển thị trạng thái kết nối
- Mỗi team có một **status badge** cạnh tên đội trong panel trận đấu
- **🟢 Online** — `is_connected = true`
- **🔴 Offline** — `is_connected = false`
- Badge cập nhật realtime qua WebSocket, không cần reload trang
- Không dùng polling HTTP từ frontend để check trạng thái agent

### SDK — tích hợp heartbeat tự động
```python
import threading

class QuintetXClient:
    def _heartbeat_loop(self):
        """Chạy nền, gửi heartbeat định kỳ"""
        while not self._stop_heartbeat.is_set():
            try:
                requests.post(f"{self.base_url}/heartbeat", headers=self.headers, timeout=3)
            except Exception:
                pass  # Không crash nếu mất kết nối tạm thời
            self._stop_heartbeat.wait(timeout=HEARTBEAT_INTERVAL)

    def connect(self):
        """Notify server agent is online, bắt đầu heartbeat thread"""
        resp = requests.post(f"{self.base_url}/init", headers=self.headers).json()
        self._stop_heartbeat = threading.Event()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()
        return resp

    def disconnect(self):
        """Dừng heartbeat thread"""
        if hasattr(self, "_stop_heartbeat"):
            self._stop_heartbeat.set()
```

> **Lưu ý**: Heartbeat thread là `daemon=True` — tự động dừng khi process Python kết thúc. SDK không cần gọi `disconnect()` tường minh, nhưng nên gọi trong `finally` block để tắt sạch.

## Response Format
Always return consistent JSON:
```json
{ "status": "success|error", "data": {}, "message": "" }
```

---

# CLIENT-SIDE SDK (Student Side)
The SDK is a clean Python class providing a high-level API for students.

**File**: `quintetx_sdk.py`

```python
import requests
import time

class QuintetXClient:
    def __init__(self, api_key, team_id, server_url):
        self.api_key = api_key
        self.team_id = team_id
        self.base_url = f"{server_url}/api/v1/agent"
        self.headers = {"X-API-Key": api_key, "X-Team-ID": team_id}

    def connect(self):
        """Notify server agent is online"""
        return requests.post(f"{self.base_url}/init", headers=self.headers).json()

    def get_state(self):
        """Return current board and turn"""
        return requests.get(f"{self.base_url}/state", headers=self.headers).json()

    def send_move(self, x, y):
        """Push move (x, y) to server"""
        payload = {"x": x, "y": y}
        return requests.post(f"{self.base_url}/move", json=payload, headers=self.headers).json()

    def start_loop(self, strategy_func):
        """Auto-poll state and call strategy_func(board) when it is agent's turn"""
        while True:
            state = self.get_state()
            if state["match_status"] == "finished":
                break
            if state["turn"] == self.get_side_from_id():
                move_x, move_y = strategy_func(state["board"])
                self.send_move(move_x, move_y)
            time.sleep(0.5)
```

---

# AUTHENTICATION
- **Student Login**: MSSV + Password
- **Student Register**: MSSV + Họ tên + Lớp + Password + Confirm Password
- **Admin Login**: Separate route, Username/Email + Password

---

# ROLE-BASED VIEWS

## Student (read-only)
Sidebar: Tổng quan · Đội của tôi · Trận đấu · Lịch sử

### Đội của tôi
- Team name + ID (read-only)
- Member list: avatar + name + MSSV only

### Trận đấu
- 40x40 board (read-only)
- Right panel: LỊCH SỬ NƯỚC ĐI + LẤY API BODY
- Bottom: flat status bar only ("Trạng thái: Đang diễn ra", "Thời gian trận đấu: 01:28")
- Playback toolbar: **HIDDEN**

### Tổng quan (Dashboard)
- Team info card (name, ID, members)
- Stat cards: Tổng trận đấu · Thắng · Thua
- Recent match history table (5 rows): STT · Đối thủ · Kết quả · Thời gian

## Admin (full control)
Sidebar: Tổng quan · Quản Lý Nhóm · Quản Lý Phòng · Trận đấu · Xét duyệt Admin

### Trận đấu
- Full playback toolbar (play/pause/seek/speed)
- Right panel: LỊCH SỬ NƯỚC ĐI + LẤY API BODY
- Button: Tạo phòng mới

---

# DESIGN SYSTEM (KV)
- **Theme**: Light (white cards, `#F0F2F5` background)
- **Primary color**: Blue (`#3547E5`)
- **Headings**: Bold dark, short blue underline accent (left-aligned)
- **Input fields**: Light gray background, no border
- **Primary button**: Blue fill, white uppercase bold
- **Sidebar**: White, 240px, QuintetX logo top-left (no subtext), avatar + name + role bottom-left
- **Header**: Bell + gear icons only (no username)
- **Pieces**: X = Blue (`#3547E5`), O = Red (`#E53535`)

---

# CODE ORGANIZATION RULES

## Backend Configuration
**File**: `app/core/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOARD_SIZE: int = 40
    WIN_COUNT: int = 5
    TIME_PER_MOVE: float = 0.5
    MAX_RETRIES: int = 3
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "quintetx"
    # WebSocket event name constants, API prefixes, CORS origins, collection names, token expiry

settings = Settings()
```

## Frontend Configuration
**File**: `static/js/config.js`

```javascript
const CONFIG = {
    API_BASE: "/api/v1",
    WS_URL: "/ws/match",
    BOARD_SIZE: 40,
    HEARTBEAT_INTERVAL: 5000,         // ms — SDK gửi heartbeat mỗi 5s
    HEARTBEAT_TIMEOUT: 15000,         // ms — coi là offline sau 15s không có heartbeat
    COLORS: { X: "#3547E5", O: "#E53535" },
    AGENT_STATUS: { ONLINE: "online", OFFLINE: "offline" },
    LABELS: {
        STATUS_PLAYING: "Đang diễn ra",
        STATUS_FINISHED: "Kết thúc",
        AGENT_ONLINE: "Online",
        AGENT_OFFLINE: "Offline",
    }
}
```

## HTML Templates (Jinja2)
- Centralize Vietnamese UI strings in `app/core/constants.py` and pass via template context
- Never hardcode UI strings directly in templates

## General Rules
- No magic numbers anywhere in code
- No duplicate route strings (define once, import everywhere)
- No hardcoded colors in inline styles (use Tailwind classes or `CONFIG.COLORS`)
- If a constant appears more than once → move it to config immediately
- Prioritize async execution to handle high-frequency polling from agents

---

# STATIC ASSETS & FAVICON

## Favicon
Every HTML template must include inside `<head>`:
```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link rel="shortcut icon" href="/static/favicon.ico">
```
Favicon tags must live in `base.html` only — never duplicated in child templates.

## FastAPI Static Mount
```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
```
This line must exist in `main.py` before any route definitions. Never hardcode absolute paths — always use `/static/` prefix.

## Static Folder Structure
```
static/
├── favicon.svg        ← SVG favicon (primary)
├── favicon.ico        ← ICO fallback (for old browsers)
├── js/
│   └── config.js      ← shared frontend config
└── css/
    └── main.css       ← global styles (if any)
```

---

# UI CLEANLINESS RULES
- Do **NOT** add any subtitle, subheading, or descriptive text below page titles
- Do **NOT** add placeholder instructional text inside empty states or cards
- Do **NOT** add comment annotations or bracket notes visible to users (e.g. `[Tên đội]`, `(optional)`)
- Every UI element must serve a functional purpose — decorative or explanatory text must be omitted
- Never change CSS structure, color palette, or 40x40 board rendering unless explicitly asked
- Never modify the 40x40 board rendering logic unless requested
