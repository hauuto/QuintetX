from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import requests


JsonDict = dict
Board = list[list[int]]
NextMoveFunc = Callable[[Board], Tuple[int, int]]
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
        log: Callable[[str], None] | None = print,
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

        self._log_fn = log

        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    # -------------------------
    # Low-level HTTP helpers
    # -------------------------

    def _log(self, message: str) -> None:
        if not self._log_fn:
            return
        try:
            self._log_fn(f"[QuintetX] {message}")
        except Exception:
            # Never crash user code because of logging.
            pass

    def _normalize_response(self, *, resp: requests.Response | None, exc: Exception | None) -> JsonDict:
        if exc is not None:
            return {
                "status": "error",
                "data": {},
                "message": f"Network error: {exc}",
                "http_status": None,
                "error_type": "network",
            }

        assert resp is not None
        status_code = int(getattr(resp, "status_code", 0) or 0)

        try:
            payload = resp.json()
        except Exception:
            text_head = (resp.text or "")[:500]
            return {
                "status": "error" if not resp.ok else "success",
                "data": {},
                "message": f"Non-JSON response: HTTP {status_code} | {text_head}",
                "http_status": status_code,
                "error_type": "http" if not resp.ok else None,
            }

        # Normalize common FastAPI error shape: {"detail": "..."}
        if isinstance(payload, dict) and "status" not in payload and "detail" in payload:
            return {
                "status": "error",
                "data": {},
                "message": str(payload.get("detail") or ""),
                "http_status": status_code,
                "error_type": "auth" if status_code in (401, 403) else "http",
            }

        # Ensure we always return the SDK's standard envelope.
        if not isinstance(payload, dict) or "status" not in payload:
            return {
                "status": "success" if resp.ok else "error",
                "data": payload if isinstance(payload, dict) else {"raw": payload},
                "message": "" if resp.ok else f"HTTP {status_code}",
                "http_status": status_code,
                "error_type": None if resp.ok else ("auth" if status_code in (401, 403) else "http"),
            }

        # Add metadata without breaking the server's existing shape.
        payload.setdefault("http_status", status_code)
        if not resp.ok:
            payload.setdefault("error_type", "auth" if status_code in (401, 403) else "http")
            payload["status"] = "error"
            if not payload.get("message"):
                payload["message"] = f"HTTP {status_code}"
            payload.setdefault("data", {})

        return payload

    def _request(self, method: str, path: str, *, json: JsonDict | None = None) -> JsonDict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json,
                timeout=self.config.timeout_seconds,
            )
            return self._normalize_response(resp=resp, exc=None)
        except Exception as exc:
            return self._normalize_response(resp=None, exc=exc)

    def _get(self, path: str) -> JsonDict:
        return self._request("GET", path)

    def _post(self, path: str, *, json: JsonDict | None = None) -> JsonDict:
        return self._request("POST", path, json=json)

    # -------------------------
    # Public API
    # -------------------------

    def _is_auth_error(self, payload: JsonDict) -> bool:
        http_status = payload.get("http_status")
        if http_status in (401, 403):
            return True
        message = str(payload.get("message") or "")
        return "Invalid agent credentials" in message or "Missing X-API-Key" in message

    def connect(self, *, start_heartbeat: bool = True, heartbeat_interval: float = 5.0) -> JsonDict:
        """POST /init.

        - Nếu đúng credential, server trả payload state, gồm `data.side` (X/O).
        - Nếu sai credential, server trả HTTP 401 (FastAPI error shape).
        """
        payload = self._post("/init")
        if payload.get("status") == "success":
            self.side = (payload.get("data") or {}).get("side")
            self._log(f"Connected. side={self.side}")
            if start_heartbeat:
                self.start_heartbeat(interval_seconds=heartbeat_interval)
        else:
            if self._is_auth_error(payload):
                self._log("Auth failed (team_id/api_key).")
            else:
                self._log(f"Connect failed: {payload.get('message')}")
        return payload

    def connect_with_retry(
        self,
        *,
        start_heartbeat: bool = True,
        heartbeat_interval_seconds: float = 5.0,
        retry_initial_delay_seconds: float = 1.0,
        retry_max_delay_seconds: float = 10.0,
        retry_jitter_seconds: float = 0.2,
        max_attempts: int | None = None,
    ) -> JsonDict:
        """Reconnect /init cho đến khi thành công.

        - Nếu sai team_id/api_key: báo lỗi và dừng (không retry vô hạn).
        - Nếu lỗi mạng/server: retry với backoff.
        """
        attempt = 0
        delay = max(0.2, float(retry_initial_delay_seconds))
        max_delay = max(delay, float(retry_max_delay_seconds))
        jitter = max(0.0, float(retry_jitter_seconds))

        while True:
            attempt += 1
            if attempt == 1:
                self._log("Connecting...")
            else:
                self._log(f"Reconnecting... attempt={attempt}")

            payload = self.connect(start_heartbeat=False)
            if payload.get("status") == "success":
                if start_heartbeat:
                    self.start_heartbeat(interval_seconds=heartbeat_interval_seconds)
                return payload

            if self._is_auth_error(payload):
                # Wrong credentials should be surfaced immediately.
                return payload

            if max_attempts is not None and attempt >= int(max_attempts):
                return payload

            sleep_s = min(max_delay, delay)
            if jitter:
                sleep_s += random.uniform(0.0, jitter)
            self._log(f"Retry in {sleep_s:.1f}s: {payload.get('message')}")
            time.sleep(sleep_s)
            delay = min(max_delay, delay * 1.5)

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
        next_move: NextMoveFunc,
        *,
        poll_interval_seconds: float = 0.5,
        connect_first: bool = True,
        start_heartbeat: bool = True,
        heartbeat_interval_seconds: float = 5.0,
        max_steps: int | None = None,
    ) -> None:
        """Vòng lặp tối giản: poll state; nếu đến lượt thì gọi next_move(board) và gửi move.

        - next_move(board) -> (x, y)
        - `board` là trạng thái bàn cờ hiện tại (ma trận 2D)
        - Dừng khi match finished, hoặc khi đạt max_steps (nếu set).
        """
        if connect_first:
            init = self.connect_with_retry(
                start_heartbeat=start_heartbeat,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
            if init.get("status") != "success":
                message = init.get("message") or f"Cannot connect: {init}"
                # If wrong credential, fail fast so user can fix config.
                raise RuntimeError(str(message))

        sleep_s = max(0.05, float(poll_interval_seconds))
        steps = 0

        try:
            while True:
                if max_steps is not None and steps >= max_steps:
                    return

                state = self.get_state()
                steps += 1

                if state.get("status") != "success":
                    if self._is_auth_error(state):
                        raise RuntimeError(str(state.get("message") or "Invalid agent credentials"))
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
                    board = data.get("board") or []
                    x, y = next_move(board)
                    self.send_move(x, y)

                time.sleep(sleep_s)
        finally:
            self.stop_heartbeat()

    def run_with_state(
        self,
        strategy: StrategyFunc,
        *,
        poll_interval_seconds: float = 0.5,
        connect_first: bool = True,
        start_heartbeat: bool = True,
        heartbeat_interval_seconds: float = 5.0,
        max_steps: int | None = None,
    ) -> None:
        """Phiên bản nâng cao: strategy nhận nguyên state_data (bao gồm board/turn/events...)."""
        if connect_first:
            init = self.connect_with_retry(
                start_heartbeat=start_heartbeat,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
            if init.get("status") != "success":
                message = init.get("message") or f"Cannot connect: {init}"
                raise RuntimeError(str(message))

        sleep_s = max(0.05, float(poll_interval_seconds))
        steps = 0
        try:
            while True:
                if max_steps is not None and steps >= max_steps:
                    return

                state = self.get_state()
                steps += 1

                if state.get("status") != "success":
                    if self._is_auth_error(state):
                        raise RuntimeError(str(state.get("message") or "Invalid agent credentials"))
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
