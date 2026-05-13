# QuintetX System

## Mục tiêu hệ thống

QuintetX là nền tảng tổ chức thi đấu AI Gomoku/Caro cho sinh viên. Hệ thống cho phép sinh viên tạo nhóm, admin tạo phòng đấu, đội thi kết nối agent bằng SDK, server điều phối ván đấu và lưu toàn bộ trạng thái vào MongoDB.

## Tác nhân

```text
Student
  -> đăng ký/đăng nhập
  -> tạo/tham gia nhóm
  -> xem trận/histories
  -> tải SDK
  -> chạy agent

Leader
  -> quản lý thành viên nhóm
  -> duyệt join request
  -> gửi invite

Admin
  -> đăng nhập admin
  -> xem dashboard
  -> quản lý teams/rooms
  -> tạo/xóa match
  -> cấp API key cho đội

Agent/SDK
  -> init vào match
  -> heartbeat
  -> poll state
  -> gửi nước đi

MongoDB
  -> lưu users/groups/matches/notifications
```

## Luồng hệ thống tổng quát

```text
[User opens browser]
        |
        v
[Jinja2 page rendered by FastAPI]
        |
        v
[Static JS calls /api/v1/*]
        |
        v
[FastAPI router]
        |
        v
[MongoDB]
        |
        v
[JSON response]
        |
        v
[DOM updated]
```

## Luồng khởi động hệ thống

```text
Start process
  -> main.py creates FastAPI app
  -> lifespan starts
  -> connect MongoDB
  -> create missing collections
  -> apply Mongo validators
  -> create indexes
  -> seed data based on APP_ENV
  -> include routers
  -> mount static files
  -> serve HTML/API
```

Nếu MongoDB lỗi khi startup, app fail-fast.

## Luồng đăng ký/đăng nhập

### Student register

```text
Student submits MSSV/full_name/class/password
  -> validate MSSV 8 digits
  -> confirm password match
  -> check duplicate MSSV
  -> create user U{mssv}
  -> hash password
  -> insert users collection
```

### Student/Admin login

```text
User submits credentials
  -> find user by MSSV or username/email
  -> verify password_hash
  -> check is_active
  -> issue JWT
  -> frontend stores token
```

JWT payload:

```text
sub: user_id
role: student|admin
exp: expiry
```

## Luồng xác thực API

```text
Browser API request
  -> Authorization: Bearer <token>
  -> get_current_user()
  -> jwt.decode()
  -> find user by sub
  -> reject if missing/inactive
  -> route handler executes
```

Agent API request:

```text
SDK request
  -> X-Team-ID + X-API-Key
  -> get_agent_session()
  -> find match where team/api_key matches X or O
  -> infer side X/O
  -> route handler executes
```

## Luồng quản lý nhóm

### Tạo nhóm

```text
Student without group
  -> POST /api/v1/groups
  -> generate group_id T...
  -> generate group_code GRP-...
  -> members = [student]
  -> leader_id = student id
  -> insert group
  -> set user.group_id
```

### Xin vào nhóm

```text
Student without group
  -> list public groups with slots
  -> POST /groups/{group_id}/join
  -> validate group public/not full
  -> append pending_requests
  -> create notification for leader
```

### Duyệt join request

```text
Leader
  -> GET /groups/{group_id}/join-requests
  -> POST approve/reject
  -> approve:
       remove pending request
       push member
       set user.group_id
       notify user
  -> reject:
       remove pending request
       notify user
```

### Invite member

```text
Leader
  -> POST /groups/{group_id}/invite with MSSV
  -> validate target user exists/no group
  -> create invite notification

Target user
  -> accept invite
       push member
       set user.group_id
       mark notification accepted/read
       notify leader
  -> reject invite
       mark notification rejected/read
       notify leader
```

### Quản lý thành viên

```text
Leader
  -> rename group
  -> kick member
       remove member
       set kicked user's group_id = null
       notify kicked user
```

## Luồng tạo trận đấu

### Admin tạo trận team-vs-team

```text
Admin
  -> open admin match page
  -> get team options
  -> select X team, O team, start_time, room_name
  -> POST /api/v1/matches
  -> validate admin
  -> validate X/O different
  -> validate teams exist
  -> check no active match conflict
  -> create match:
       status = waiting
       board = 40x40 zeros
       current_turn = X
       api_key for X/O
       events = [match_created]
  -> return API keys
```

### Student tạo trận vs bot

```text
Student with group
  -> POST /api/v1/matches/bot
  -> validate student/group
  -> check no active match conflict
  -> create match:
       X = student group
       O = Greedy Bot
       O connected = true
       status = waiting
       start_time = now
  -> return X API key
```

## Luồng agent kết nối trận

```text
SDK starts
  -> login/reuse web session
  -> get current match via /api/v1/matches/me
  -> extract team_id, side, api_key
  -> POST /api/v1/agent/init
  -> server marks side connected
  -> if both sides connected:
       status = playing
       current_turn = X
       started_at = now
       turn_deadline_at = now + MOVE_TIMEOUT_SECONDS
  -> response includes board/turn/status/events
```

## Luồng chơi game

```text
Agent loop
  -> GET /api/v1/agent/state
  -> read board, side, turn, match_status
  -> if match_status != playing: wait/exit
  -> if turn != side: wait
  -> if turn == side:
       strategy(board/state) returns (x, y)
       POST /api/v1/agent/move {x, y}
```

Server xử lý move:

```text
Receive move
  -> apply timeout check
  -> require status = playing
  -> require current_turn == side
  -> require x/y inside board
  -> require board[x][y] == 0
  -> set board[x][y] = 1 if X else 2
  -> update heartbeat for side
  -> push history
  -> push move_accepted event
  -> increment rev
  -> check 5-in-row
       yes:
         status = finished
         winner = side
         finish_reason = win
         push win_detected + match_finished events
       no:
         current_turn = other side
         turn_deadline_at = now + timeout
         push turn_changed event
```

## Luồng timeout

```text
Any init/state/move call
  -> check match.status == playing
  -> compare now with turn_deadline_at
  -> if overdue:
       loser = current_turn
       winner = other side
       status = finished
       finish_reason = timeout_forfeit
       turn_deadline_at = null
       push timeout_forfeit + match_finished events
```

## Luồng Greedy Bot

```text
After init/state/move
  -> if match playing
  -> if current_turn side belongs to Greedy Bot
  -> call greedy_strategy({board, side})
  -> if invalid move: fallback first empty cell
  -> apply move like normal agent
  -> if win: finish
  -> else switch turn
```

## Luồng frontend xem trận

```text
Student opens /student/match
  -> page loads static JS
  -> JS calls /api/v1/matches/me
  -> receives my_current_match/my_team/other_matches
  -> renders board/status/API key/events
  -> periodic summary polling with since_rev
  -> if rev_changed:
       fetch full match/events
       update UI
```

## Luồng lịch sử trận

```text
Student opens /student/history
  -> JS calls /api/v1/matches/my/history
  -> server finds finished matches where team is X or O
  -> joins group names
  -> returns result, winner, finish_reason, move_count
  -> UI renders history table/cards
```

## Luồng admin

```text
Admin login
  -> JWT role = admin
  -> /admin/dashboard
       count groups
       count matches
       count active rooms
  -> /admin/teams
       list groups
  -> /admin/rooms
       list matches + team names
  -> /admin/match
       create/delete matches via API
```

Admin approvals hiện là placeholder:

```text
POST /api/v1/admin/approve/{admin_id} -> Not implemented
DELETE /api/v1/admin/reject/{admin_id} -> Not implemented
```

## Luồng SDK

```text
sdk_run.py
  -> discover solutions/*.py
  -> select solution
  -> login student or reuse .quintetx_session.json
  -> call /api/v1/matches/me
  -> get my_team.id, side, api_key
  -> QuintetXClient.connect_with_retry()
  -> start heartbeat thread
  -> loop:
       state = client.get_state()
       if my turn:
          move = solution.strategy(state) or next_move(board)
          client.send_move(move)
```

## Trạng thái match

```text
waiting
  -> match created, waiting agents

playing
  -> both sides connected, moves accepted

finished
  -> win, timeout_forfeit, draw, or terminal condition
```

## Event types chính

```text
match_created
agent_ready
match_started
move_accepted
move_rejected
turn_changed
win_detected
match_finished
timeout_forfeit
```

## Response convention

API response thường theo dạng:

```json
{
  "status": "success|error",
  "data": {},
  "message": ""
}
```

Exception handlers cũng chuẩn hóa lỗi HTTP/validation/internal server error về cùng dạng.

## Cấu hình chính

```text
APP_NAME = QuintetX
SERVER_HOST = 0.0.0.0
SERVER_PORT = 2111
BOARD_SIZE = 40
TIME_PER_MOVE = 0.5
MOVE_TIMEOUT_SECONDS = 10
MONGODB_URI = mongodb://localhost:27017
DATABASE_NAME = quintetx
HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_TIMEOUT = 15.0
ACCESS_TOKEN_EXPIRE_MINUTES = 30
```

## Ranh giới hệ thống

Trong scope:

- User auth.
- Team management.
- Match management.
- Agent protocol.
- Gomoku engine.
- SDK download/use.
- Basic admin dashboard.
- MongoDB persistence.
- Polling-based live updates.

Ngoài scope/đang thiếu:

- WebSocket realtime.
- Background heartbeat disconnect monitor.
- Full admin approval workflow.
- Persistent metrics.
- Fine-grained match visibility authorization.
- Production secret management beyond env override.

## Luồng dữ liệu cốt lõi

```text
users.group_id <---------- groups.members[].user_id
      |                              |
      |                              v
      +-----------------------> matches.teams.X/O.team_id
                                      |
                                      v
                              matches.board/history/events
                                      |
                                      v
                              frontend + SDK state views
```

## Quy tắc nghiệp vụ chính

- MSSV phải đúng 8 chữ số.
- Student ID dạng `U{mssv}`.
- Admin seed ID mặc định `A0001`.
- Team/group ID dạng `T...`.
- Match ID dạng `M...`.
- Notification ID dạng `N...`.
- User chỉ được thuộc một nhóm.
- Group tối đa 6 thành viên.
- Chỉ leader quản lý group members/requests/invites.
- Chỉ admin tạo match team-vs-team.
- Student chỉ tạo được match bot nếu đã có group.
- Một team không được có nhiều active match.
- Agent chỉ đi được khi đúng lượt.
- Move ngoài board/ô đã có quân bị reject.
- 5 quân liên tiếp theo ngang/dọc/chéo là thắng.
- Quá hạn lượt thì bên hiện tại thua timeout.
