# QuintetX Architecture

## Tổng quan

QuintetX là hệ thống thi đấu Gomoku/Caro AI dạng monolith, dùng FastAPI để phục vụ cả web UI server-rendered và REST API. Người dùng chính gồm student, admin và external agent/SDK.

```text
Browser / Student / Admin
        |
        | Jinja2 HTML + static JS
        | REST JSON /api/v1/*
        v
FastAPI app: main.py
        |
        +-- auth router       -> register/login/JWT
        +-- groups router     -> team/member/notification APIs
        +-- matches router    -> match management/API key APIs
        +-- agent router      -> SDK/gameplay protocol
        +-- metrics router    -> request metrics
        |
        v
MongoDB
  users
  groups
  matches
  notifications

External Python SDK / Agent
        |
        | X-Team-ID + X-API-Key
        v
/api/v1/agent/*
```

## Công nghệ

- Python 3.12.
- FastAPI + Uvicorn.
- Jinja2 templates.
- Static JavaScript vanilla.
- MongoDB qua Motor/PyMongo.
- JWT Bearer cho web/API.
- API key theo team cho agent.
- Game board 40x40, thắng khi có 5 quân liên tiếp.

## Entry point

`main.py` là entrypoint chính.

Startup flow:

```text
FastAPI lifespan
  -> connect_db()
  -> initialize_local_database()
       -> ensure collections
       -> apply collection validators
       -> ensure indexes
       -> seed local users/groups/admin
  -> serve app
  -> close_db() on shutdown
```

`main.py` cũng đảm nhiệm:

- Tạo `FastAPI` app.
- Gắn middleware metrics cho `/api/v1/*`.
- Chuẩn hóa response lỗi HTTP/validation/unhandled exception.
- Mount `/static`.
- Include API routers.
- Render các page student/admin.
- Cung cấp download SDK instruction/zip.
- Health/seed-check endpoints.

## Cấu trúc module

```text
app/
  api/
    auth.py       # student/admin auth, JWT issuing
    deps.py       # current_user dependency, agent_session dependency
    groups.py     # team, join request, invite, notification APIs
    matches.py    # match creation/view/history/delete APIs
    agent.py      # SDK/agent game protocol
    metrics.py    # in-memory request metrics APIs

  core/
    config.py     # app/server/game/db/security/env settings
    security.py   # password hashing/verification
    metrics.py    # in-memory request metrics collector

  db/
    client.py     # MongoDB client lifecycle
    init_db.py    # collection creation, validators, indexes, seed data
    validators.py # MongoDB JSON schema validators

templates/
  student/admin/login/register/error pages

static/
  js/api/client.js
  js/api/groups.js
  js/api/matches.js

QuintetX_SDK.py    # Python SDK client
sdk_run.py         # CLI runner for solutions
sdk_gui.py         # GUI runner/package asset
solutions/         # sample AI strategies
```

## API layer

### Auth router

Prefix: `/api/v1/auth`

- `POST /register/student`: đăng ký student bằng MSSV.
- `POST /login/student`: đăng nhập student.
- `POST /login/admin`: đăng nhập admin.

Auth flow:

```text
User submits credentials
  -> validate input
  -> find user in users collection
  -> verify password hash
  -> issue JWT {sub, role, exp}
  -> frontend stores token
  -> future API calls use Authorization: Bearer <token>
```

### Groups router

Prefix: `/api/v1/groups`

Chức năng:

- Liệt kê group public còn slot.
- Lấy group hiện tại/dashboard của student.
- Tạo group.
- Gửi join request.
- Leader duyệt/từ chối join request.
- Leader mời user bằng MSSV.
- Accept/reject invite.
- Search player bằng MSSV.
- Lấy/đọc notifications.
- Đổi tên group.
- Kick member.

Group constraint:

- Một user chỉ thuộc một group.
- Một group tối đa 6 thành viên.
- Chỉ leader được approve/reject/invite/rename/kick.

### Matches router

Prefix: `/api/v1/matches`

Chức năng:

- Admin lấy team options.
- Admin tạo match team-vs-team.
- Student tạo match vs Greedy Bot.
- Lấy overview current/upcoming/finished matches.
- Lấy match hiện tại của user.
- Lấy summary theo `rev` để polling nhẹ.
- Lấy events của match.
- Lấy history match của team.
- Admin xóa match.
- Lấy chi tiết match theo ID.

Match creation flow:

```text
Admin creates match
  -> validate admin role
  -> validate X/O teams exist
  -> reject same team
  -> reject active match conflict
  -> generate match_id
  -> generate api_key for X/O
  -> create 40x40 board
  -> status = waiting
  -> return match + API keys
```

Student-vs-bot flow:

```text
Student creates bot match
  -> validate student role
  -> require current group
  -> reject active match conflict
  -> X = student's group
  -> O = Greedy Bot
  -> bot marked connected
  -> status = waiting
  -> return X api_key to student
```

### Agent router

Prefix: `/api/v1/agent`

Agent auth headers:

```text
X-Team-ID: <team id>
X-API-Key: <team side api key>
```

Endpoints:

- `POST /init`: agent ready/connect.
- `GET /state`: get board, turn, status, events.
- `POST /heartbeat`: keep team connected.
- `POST /move`: submit move.

Gameplay flow:

```text
Agent init
  -> get_agent_session validates team_id/api_key
  -> mark side connected
  -> if X and O connected:
       waiting -> playing
       current_turn = X
       set turn_deadline_at

Agent loop
  -> GET /state
  -> if turn == side:
       POST /move {x, y}

Move validation
  -> match must be playing
  -> side must equal current_turn
  -> x/y must be inside board
  -> board[x][y] must be empty

Move accepted
  -> write board cell
  -> push history event
  -> increment rev
  -> check win
  -> if win: finished
  -> else switch turn and set deadline
```

Timeout flow:

```text
state/init/move call
  -> apply_turn_timeout_if_needed
  -> if now > turn_deadline_at:
       current side loses
       other side wins
       status = finished
       finish_reason = timeout_forfeit
```

Greedy Bot flow:

```text
After state/init/move
  -> if current_turn belongs to Greedy Bot
  -> call solutions.solution_greedy.strategy
  -> validate/fallback first empty cell
  -> apply bot move
  -> check win or switch turn
```

## Database layer

### Collections

```text
users
  _id
  mssv
  full_name
  class_name
  username
  email
  password_hash
  role
  group_id
  is_active
  created_at

groups
  _id
  group_code
  name
  description
  avatar_url
  is_public
  leader_id
  members[]
  pending_requests[]
  match_history[]
  stats
  created_at

matches
  _id
  room_name
  status
  rev
  updated_at
  board
  teams.X
  teams.O
  current_turn
  winner
  history[]
  events[]
  start_time
  started_at
  finished_at
  turn_deadline_at
  finish_reason
  created_at

notifications
  _id
  user_id
  sender_id
  type
  message
  is_read
  status
  group_id
  link
  metadata
  created_at
```

### Indexes

- Unique `users.mssv`.
- Unique `groups.group_code`.
- Non-unique `matches.room_name`.
- `matches.start_time` descending.
- Team lookup indexes for X/O by `created_at`.
- Partial unique indexes to prevent a team from having more than one active match per side.
- Notification indexes by user/read/created and status/type.

## Frontend architecture

Frontend dùng Jinja2 để render pages, sau đó static JS gọi REST API.

```text
Jinja2 page
  -> static JS module
  -> api/client.js fetch wrapper
  -> attaches Bearer token
  -> receives JSON response
  -> updates DOM
```

Auth behavior:

- Token lưu trong `localStorage`.
- API wrapper tự gắn `Authorization` header.
- Response 401 redirect tới `/401`.

## SDK architecture

SDK là Python client cho đội thi.

```text
sdk_run.py
  -> chọn server
  -> login/reuse session
  -> load solution from solutions/*.py
  -> get active match credentials
  -> QuintetXClient init/connect
  -> heartbeat background thread
  -> poll state loop
  -> call user strategy
  -> send move
```

SDK giao tiếp với server qua:

- Web/API auth để lấy match/team credentials.
- Agent API auth bằng `X-Team-ID` + `X-API-Key`.

## Deployment/runtime notes

- App mặc định chạy host `0.0.0.0`, port `2111`.
- DB mặc định `mongodb://localhost:27017`, database `quintetx`.
- `APP_ENV=prod` chỉ seed admin.
- `APP_ENV=dev` seed thêm student/group mẫu.
- Metrics là in-memory, reset khi process restart.
- Realtime hiện dùng polling, chưa dùng WebSocket.

## Điểm còn placeholder/giới hạn

- Admin approval APIs trả `Not implemented`.
- Admin dashboard recent activity đang rỗng.
- Pending admin count đang hardcoded `0`.
- Agent heartbeat timeout config tồn tại, nhưng disconnect checker nền chưa thấy tách riêng.
- Greedy Bot team ID chưa đồng nhất giữa `matches.py` và `agent.py` trong code hiện tại.