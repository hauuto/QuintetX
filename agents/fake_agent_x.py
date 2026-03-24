import os
import threading
import time
from typing import List, Tuple

import requests


SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
TEAM_ID = os.getenv("TEAM_X_ID", "")
API_KEY = os.getenv("TEAM_X_API_KEY", "")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "0.7"))
HEARTBEAT_INTERVAL_SECONDS = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5.0"))

OPENING_MOVES: List[Tuple[int, int]] = [
    (20, 20),
    (21, 20),
    (22, 20),
    (23, 20),
    (24, 20),
]


class FakeAgentX:
    def __init__(self, server_url: str, team_id: str, api_key: str):
        self.base_url = f"{server_url.rstrip('/')}/api/v1/agent"
        self.headers = {
            "X-Team-ID": team_id,
            "X-API-Key": api_key,
        }
        self.side = None
        self._stop_hb = threading.Event()
        self._hb_thread = None
        self._move_index = 0

    def connect(self) -> dict:
        response = requests.post(f"{self.base_url}/init", headers=self.headers, timeout=5)
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(payload.get("message") or "Cannot init agent")
        self.side = payload.get("data", {}).get("side")
        self._start_heartbeat()
        return payload

    def _start_heartbeat(self) -> None:
        def loop() -> None:
            while not self._stop_hb.is_set():
                try:
                    requests.post(f"{self.base_url}/heartbeat", headers=self.headers, timeout=3)
                except Exception:
                    pass
                self._stop_hb.wait(HEARTBEAT_INTERVAL_SECONDS)

        self._hb_thread = threading.Thread(target=loop, daemon=True)
        self._hb_thread.start()

    def get_state(self) -> dict:
        response = requests.get(f"{self.base_url}/state", headers=self.headers, timeout=5)
        return response.json()

    def send_move(self, x: int, y: int) -> dict:
        response = requests.post(
            f"{self.base_url}/move",
            headers=self.headers,
            json={"x": x, "y": y},
            timeout=5,
        )
        return response.json()

    def _next_move(self, board: List[List[int]]) -> Tuple[int, int]:
        if self._move_index < len(OPENING_MOVES):
            move = OPENING_MOVES[self._move_index]
            self._move_index += 1
            return move

        for x in range(len(board)):
            for y in range(len(board[x])):
                if board[x][y] == 0:
                    return x, y

        return 0, 0

    def run(self) -> None:
        print("[X] Connecting...")
        init_data = self.connect()
        print(f"[X] Connected. Side={init_data.get('data', {}).get('side')}")

        while True:
            state = self.get_state()
            if state.get("status") != "success":
                print(f"[X] State error: {state.get('message')}")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            data = state.get("data", {})
            status = data.get("match_status")
            if status == "finished":
                print(f"[X] Match finished. Winner={data.get('winner')}")
                break

            if status != "playing":
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if data.get("turn") == data.get("side"):
                board = data.get("board", [])
                x, y = self._next_move(board)
                result = self.send_move(x, y)
                print(f"[X] Move ({x}, {y}) => {result.get('status')} | {result.get('message')}")

            time.sleep(POLL_INTERVAL_SECONDS)

        self._stop_hb.set()


if __name__ == "__main__":
    if not TEAM_ID or not API_KEY:
        print("Missing config. Set TEAM_X_ID and TEAM_X_API_KEY environment variables.")
        raise SystemExit(1)

    agent = FakeAgentX(SERVER_URL, TEAM_ID, API_KEY)
    try:
        agent.run()
    finally:
        agent._stop_hb.set()
