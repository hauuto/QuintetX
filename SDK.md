# QuintetX Python SDK (single-file)

SDK Python tối giản để viết AI agent chơi Gomoku/Caro trên QuintetX qua HTTP polling.

- 1 file duy nhất: `QuintetX_SDK.py`
- Không cần `.env`, không cần config phụ

## Yêu cầu

- Python 3.10+ (khuyến nghị)
- `requests`

Cài `requests`:

```bash
pip install requests
```

## Cài đặt

Chỉ cần copy file `QuintetX_SDK.py` vào project của bạn.

## Cách chạy (khuyến nghị) — Login + Multi-solution

Không cần nhập `team_id` và `api_key` nữa.

1) Chạy runner:

```bash
python sdk_run.py --server-url http://127.0.0.1:8000
```

2) SDK sẽ hiện danh sách solution trong thư mục `solutions/` để bạn chọn.

3) Lần chạy đầu tiên sẽ hỏi:
- MSSV
- Password

Sau khi login, SDK lưu session vào file `.quintetx_session.json` (cùng thư mục với `sdk_run.py`). Lần sau chỉ cần chạy lại `sdk_run.py` là đủ.

## Template có giao diện (GUI)

SDK có sẵn template GUI chạy local (Tkinter, không cần cài thêm thư viện):

```bash
python sdk_gui.py --server-url http://127.0.0.1:8000
```

GUI hỗ trợ: login/load session, chọn solution trong `solutions/`, Start/Stop, xem log.

> Lưu ý: SDK sẽ gọi `GET /api/v1/matches/me` để lấy `team_id/api_key` của nhóm bạn trong match đang `waiting/playing`. Nếu nhóm chưa có match active thì SDK sẽ báo lỗi.

## Thông tin cần có (legacy)

Nếu bạn vẫn muốn chạy theo cách cũ, bạn cần 3 giá trị từ Admin/match:

- `server_url` (ví dụ `http://127.0.0.1:8000`)
- `team_id` (ví dụ `T0001padjsl92`)
- `api_key` (key của đúng team trong đúng match)

Agent auth bằng headers:

- `X-Team-ID: <team_id>`
- `X-API-Key: <api_key>`

## Quickstart (tối giản)

```python
from QuintetX_SDK import QuintetXClient

client = QuintetXClient(
    server_url="http://127.0.0.1:8000",
    team_id="T0001padjsl92",
    api_key="YOUR_API_KEY",
)

# init + (mặc định) bắt đầu heartbeat nền
init = client.connect()
print("init:", init)
print("side:", client.side)  # "X" hoặc "O"

# Gợi ý: Nếu bạn muốn SDK tự reconnect đến khi /init thành công
# (chỉ retry khi lỗi mạng/server; sai team_id/api_key sẽ báo lỗi và dừng)
# init = client.connect_with_retry()

# Gợi ý: Nếu bạn muốn SDK tự login + tự lấy team_id/api_key (không nhập tay)
# client = QuintetXClient.from_student_login(server_url="http://127.0.0.1:8000")

state = client.get_state()
print("state:", state)

# nếu đang chơi và đúng lượt thì đi thử 1 nước
if state["status"] == "success":
    data = state["data"]
    if data["match_status"] == "playing" and data["turn"] == data["side"]:
        print(client.send_move(20, 20))
```

## Chạy agent tự động (strategy loop)

Bạn chỉ cần viết `next_move(board) -> (x, y)`.

Ví dụ: đi vào ô trống đầu tiên:

```python
from QuintetX_SDK import QuintetXClient

def next_move(board: list[list[int]]) -> tuple[int, int]:
    for x in range(len(board)):
        for y in range(len(board[x])):
            if board[x][y] == 0:
                return x, y
    return 0, 0

client = QuintetXClient("http://127.0.0.1:8000", "T0001padjsl92", "YOUR_API_KEY")
client.run(next_move)
```

## File mẫu

Repo có file mẫu `sdk_example_agent.py`.

Luồng login + multi-solution: chạy `sdk_run.py` và tạo các solution trong `solutions/`.

Chạy:

```bash
python sdk_example_agent.py --server-url http://127.0.0.1:8000 --team-id T0001padjsl92 --api-key YOUR_API_KEY
```

`run()` sẽ:
- `connect_with_retry()` (mặc định) — tự reconnect cho đến khi init thành công
- poll `GET /api/v1/agent/state`
- chỉ gửi move khi `match_status == "playing"` và tới lượt agent
- dừng khi match `finished`

## API của SDK

- `connect()` → `POST /api/v1/agent/init` (1 lần)
- `connect_with_retry()` → reconnect /init cho đến khi thành công (fail-fast nếu sai credential)
- `get_state()` → `GET /api/v1/agent/state`
- `send_move(x, y)` → `POST /api/v1/agent/move`
- `heartbeat_once()` → `POST /api/v1/agent/heartbeat`
- `start_heartbeat()` / `stop_heartbeat()`
- `run(next_move, ...)`
- `run_with_state(strategy, ...)` (nâng cao)

## Ghi chú vận hành

- Nếu server trả về response không phải JSON (ví dụ lỗi 500), SDK sẽ trả về object dạng:
  - `{ "status": "error", "message": "Non-JSON response: ..." }`
- Mỗi team chỉ được tham gia 1 match “active” tại một thời điểm (server sẽ chặn tạo match mới nếu team đang có match `waiting/playing`).

## License

Tuỳ repo bạn thiết lập.
