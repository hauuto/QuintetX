# QuintetX SDK Instruction

This guide is for students who want to run an AI agent on QuintetX quickly.

## 1) Get SDK package

Download `quintetx_sdk.zip` from the Instructions tab in the student website.

Extract the zip and keep these files in one folder:

- `QuintetX_SDK.py`
- `sdk_run.py`
- `sdk_gui.py`
- `sdk_example_agent.py`
- `solutions/*.py`

## 2) Install Python package(s)

Minimum:

```bash
pip install requests
```

Optional for ML workflow:

```bash
pip install numpy
pip install torch
pip install tensorflow
```

## 3) Start agent quickly (login flow)

CLI mode:

```bash
python sdk_run.py --server-url http://127.0.0.1:8000
```

GUI mode:

```bash
python sdk_gui.py --server-url http://127.0.0.1:8000
```

The SDK can login with student credentials and resolve `team_id` and `api_key` automatically.

## 4) Board data format

Server state includes:

```python
state = {
    "board": list[list[int]],
    "turn": "X" or "O",
    "side": "X" or "O",
    "match_status": "waiting" | "playing" | "finished",
}
```

Board values:

- `0`: empty
- `1`: X
- `2`: O

## 5) Convert board to tensor/array

`QuintetX_SDK.py` provides built-in helpers:

```python
from QuintetX_SDK import QuintetXClient

board_np = QuintetXClient.board_to_numpy(board, dtype="float32")
board_torch = QuintetXClient.board_to_torch(board, dtype="float32", device="cpu")
board_tf = QuintetXClient.board_to_tensorflow(board, dtype="float32")
```

This helps when your model expects NumPy or tensor input instead of Python lists.

## 6) Simple bot example

```python
from QuintetX_SDK import QuintetXClient


def strategy(state: dict) -> tuple[int, int]:
    board = state["board"]

    # Optional: convert board for your model
    board_np = QuintetXClient.board_to_numpy(board, dtype="float32")
    _ = board_np

    # Very simple bot: pick first empty cell
    for x, row in enumerate(board):
        for y, cell in enumerate(row):
            if cell == 0:
                return x, y
    return 0, 0


client = QuintetXClient.from_student_login(server_url="http://127.0.0.1:8000")
client.run_with_state(strategy, poll_interval_seconds=0.5, heartbeat_interval_seconds=5.0)
```

## 7) Common issues

- `No active match for your team`: your team is not in a `waiting/playing` match yet.
- `Invalid agent credentials`: team credentials are wrong or expired for the current match.
- `Network error`: check `--server-url` and server status.
