from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import requests


JsonDict = dict
StrategyFunc = Callable[[JsonDict], Tuple[int, int]]


@dataclass(frozen=True)
class QuintetXConfig:
    server_url: str
    team_id: str
    api_key: str
    timeout_seconds: float = 5.0


class QuintetXClient:
    """Client tối giản cho API Agent của QuintetX."""

    def __init__(
        self,
        server_url: str,
        team_id: str,
        api_key: str,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        server_url = (server_url or "").strip().rstrip("/")
        team_id = (team_id or "").strip()
        api_key = (api_key or "").strip()

        if not server_url:
            raise ValueError("server_url is required")
        if not team_id:
            raise ValueError("team_id is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.config = QuintetXConfig(
            server_url=server_url,
            team_id=team_id,
            api_key=api_key,
            timeout_seconds=float(timeout_seconds),
        )

        self.base_url = f"{self.config.server_url}/api/v1/agent"
        self.headers = {
            "X-Team-ID": self.config.team_id,
            "X-API-Key": self.config.api_key,
        }

        self.side: Optional[str] = None

        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    # -------------------------
    # Low-level HTTP helpers
    # -------------------------

    def _safe_json(self, resp: requests.Response) -> JsonDict:
        try:
            return resp.json()
        except Exception:
            text_head = (resp.text or "")[:500]
            return {
                "status": "error",
                "data": {},
                "message": f"Non-JSON response: HTTP {resp.status_code} | {text_head}",
            }

    def _get(self, path: str) -> JsonDict:
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=self.config.timeout_seconds,
        )
        return self._safe_json(resp)

    def _post(self, path: str, *, json: JsonDict | None = None) -> JsonDict:
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self.headers,
            json=json,
            timeout=self.config.timeout_seconds,
        )
        return self._safe_json(resp)

    # -------------------------
    # Public API
    # -------------------------

    def connect(self, *, start_heartbeat: bool = True, heartbeat_interval: float = 5.0) -> JsonDict:
        """POST /init. Server sẽ trả về side (X/O) trong payload."""
        payload = self._post("/init")
        if payload.get("status") == "success":
            self.side = (payload.get("data") or {}).get("side")
            if start_heartbeat:
                self.start_heartbeat(interval_seconds=heartbeat_interval)
        return payload

    def get_state(self) -> JsonDict:
        """GET /state."""
        return self._get("/state")

    def send_move(self, x: int, y: int) -> JsonDict:
        """POST /move."""
        return self._post("/move", json={"x": int(x), "y": int(y)})

    def heartbeat_once(self) -> JsonDict:
        """POST /heartbeat (1 lần)."""
        return self._post("/heartbeat")

    def start_heartbeat(self, *, interval_seconds: float = 5.0) -> None:
        """Chạy thread gửi heartbeat định kỳ (daemon)."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._stop_heartbeat.clear()
        interval = max(0.2, float(interval_seconds))

        def loop() -> None:
            while not self._stop_heartbeat.is_set():
                try:
                    self.heartbeat_once()
                except Exception:
                    pass
                self._stop_heartbeat.wait(interval)

        self._heartbeat_thread = threading.Thread(target=loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._stop_heartbeat.set()

    def run(
        self,
        strategy: StrategyFunc,
        *,
        poll_interval_seconds: float = 0.5,
        connect_first: bool = True,
        start_heartbeat: bool = True,
        heartbeat_interval_seconds: float = 5.0,
        max_steps: int | None = None,
    ) -> None:
        """Vòng lặp tối giản: poll state; nếu đến lượt thì gọi strategy và gửi move.

        - strategy(state_data) -> (x, y)
        - Dừng khi match finished, hoặc khi đạt max_steps (nếu set).
        """
        if connect_first:
            init = self.connect(
                start_heartbeat=start_heartbeat,
                heartbeat_interval=heartbeat_interval_seconds,
            )
            if init.get("status") != "success":
                raise RuntimeError(init.get("message") or "Cannot connect")

        sleep_s = max(0.05, float(poll_interval_seconds))
        steps = 0

        try:
            while True:
                if max_steps is not None and steps >= max_steps:
                    return

                state = self.get_state()
                steps += 1

                if state.get("status") != "success":
                    time.sleep(sleep_s)
                    continue

                data = state.get("data") or {}
                match_status = data.get("match_status")

                if match_status == "finished":
                    return

                if match_status != "playing":
                    time.sleep(sleep_s)
                    continue

                if data.get("turn") == data.get("side"):
                    x, y = strategy(data)
                    self.send_move(x, y)

                time.sleep(sleep_s)
        finally:
            self.stop_heartbeat()
