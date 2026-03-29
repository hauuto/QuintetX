from __future__ import annotations

import getpass
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests


JsonDict = dict
Board = list[list[int]]
NextMoveFunc = Callable[[Board], Tuple[int, int]]
StrategyFunc = Callable[[JsonDict], Tuple[int, int]]


@dataclass
class StudentSession:
    access_token: str
    token_type: str = "bearer"
    mssv: str | None = None
    saved_at_unix: float | None = None


def _session_default_path() -> Path:
    # "Cùng thư mục script" in practice maps best to the current working directory.
    return Path(os.getcwd()) / ".quintetx_session.json"


def _read_json_file(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _write_json_file(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_message(payload: JsonDict) -> str:
    return str(payload.get("message") or payload.get("detail") or payload.get("error") or "").strip()


def _auth_post(server_url: str, path: str, *, json_body: dict, timeout_seconds: float) -> JsonDict:
    url = f"{server_url.rstrip('/')}{path}"
    try:
        resp = requests.post(url, json=json_body, timeout=timeout_seconds)
        try:
            payload = resp.json()
        except Exception:
            return {
                "status": "error",
                "data": {},
                "message": f"Non-JSON response: HTTP {resp.status_code}",
                "http_status": int(resp.status_code),
            }

        if isinstance(payload, dict):
            payload.setdefault("http_status", int(resp.status_code))
            if not resp.ok and payload.get("status") != "error":
                payload["status"] = "error"
            return payload
        return {
            "status": "error" if not resp.ok else "success",
            "data": {"raw": payload},
            "message": "" if resp.ok else f"HTTP {resp.status_code}",
            "http_status": int(resp.status_code),
        }
    except Exception as exc:
        return {
            "status": "error",
            "data": {},
            "message": f"Network error: {exc}",
            "http_status": None,
        }


def _auth_get(server_url: str, path: str, *, access_token: str, timeout_seconds: float) -> JsonDict:
    url = f"{server_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout_seconds)
        try:
            payload = resp.json()
        except Exception:
            return {
                "status": "error",
                "data": {},
                "message": f"Non-JSON response: HTTP {resp.status_code}",
                "http_status": int(resp.status_code),
            }

        if isinstance(payload, dict):
            payload.setdefault("http_status", int(resp.status_code))
            if not resp.ok and payload.get("status") != "error":
                payload["status"] = "error"
                payload.setdefault("data", {})
                if not payload.get("message"):
                    payload["message"] = str(payload.get("detail") or f"HTTP {resp.status_code}")
            return payload
        return {
            "status": "error" if not resp.ok else "success",
            "data": {"raw": payload},
            "message": "" if resp.ok else f"HTTP {resp.status_code}",
            "http_status": int(resp.status_code),
        }
    except Exception as exc:
        return {
            "status": "error",
            "data": {},
            "message": f"Network error: {exc}",
            "http_status": None,
        }


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
    # Login-based bootstrap (Student)
    # -------------------------

    @staticmethod
    def _prompt_student_credentials() -> tuple[str, str]:
        mssv = input("MSSV: ").strip()
        password = getpass.getpass("Password: ").strip()
        return mssv, password

    @staticmethod
    def _load_session(session_file: Path) -> StudentSession | None:
        data = _read_json_file(session_file)
        token = str(data.get("access_token") or "").strip()
        if not token:
            return None
        return StudentSession(
            access_token=token,
            token_type=str(data.get("token_type") or "bearer"),
            mssv=str(data.get("mssv") or "").strip() or None,
            saved_at_unix=float(data.get("saved_at_unix")) if data.get("saved_at_unix") is not None else None,
        )

    @staticmethod
    def _save_session(session_file: Path, session: StudentSession) -> None:
        _write_json_file(
            session_file,
            {
                "access_token": session.access_token,
                "token_type": session.token_type,
                "mssv": session.mssv,
                "saved_at_unix": session.saved_at_unix or time.time(),
            },
        )

    @staticmethod
    def _login_student(
        server_url: str,
        *,
        mssv: str,
        password: str,
        timeout_seconds: float,
    ) -> tuple[StudentSession | None, JsonDict]:
        payload = _auth_post(
            server_url,
            "/api/v1/auth/login/student",
            json_body={"mssv": mssv, "password": password},
            timeout_seconds=timeout_seconds,
        )
        if payload.get("status") != "success":
            return None, payload

        data = payload.get("data") or {}
        token = str(data.get("access_token") or "").strip()
        token_type = str(data.get("token_type") or "bearer").strip() or "bearer"
        if not token:
            return None, {
                "status": "error",
                "data": {},
                "message": "Login succeeded but access_token is missing",
            }

        user = data.get("user") or {}
        session = StudentSession(access_token=token, token_type=token_type, mssv=str(user.get("mssv") or "").strip() or mssv)
        return session, payload

    @staticmethod
    def _resolve_my_team_credentials(
        server_url: str,
        *,
        access_token: str,
        timeout_seconds: float,
    ) -> tuple[tuple[str, str] | None, JsonDict]:
        payload = _auth_get(
            server_url,
            "/api/v1/matches/me",
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        if payload.get("status") != "success":
            return None, payload

        data = payload.get("data") or {}
        my_team = data.get("my_team")
        if not my_team:
            return None, {
                "status": "error",
                "data": {},
                "message": "No active match for your team (waiting/playing).",
            }

        team_id = str(my_team.get("id") or "").strip()
        api_key = str(my_team.get("api_key") or "").strip()
        if not team_id or not api_key:
            return None, {
                "status": "error",
                "data": {},
                "message": "Cannot resolve team_id/api_key from /matches/me",
            }

        return (team_id, api_key), payload

    @classmethod
    def from_student_login(
        cls,
        *,
        server_url: str,
        session_file: str | os.PathLike[str] | None = None,
        timeout_seconds: float = 5.0,
        log: Callable[[str], None] | None = print,
        prompt_login: bool = True,
        mssv: str | None = None,
        password: str | None = None,
    ) -> QuintetXClient:
        """Tạo client bằng cách đăng nhập student và tự lấy team_id/api_key.

        Flow:
        - Lần đầu: hỏi MSSV + password, login lấy JWT, lưu vào session file.
        - Lần sau: đọc JWT từ session file và dùng lại.
        - Dùng JWT gọi `GET /api/v1/matches/me` để lấy `my_team.id` + `my_team.api_key`.
        """
        normalized_server = (server_url or "").strip().rstrip("/")
        if not normalized_server:
            raise ValueError("server_url is required")

        session_path = Path(session_file) if session_file else _session_default_path()
        timeout_s = float(timeout_seconds)

        def _log_local(msg: str) -> None:
            if not log:
                return
            try:
                log(f"[QuintetX] {msg}")
            except Exception:
                pass

        session = cls._load_session(session_path)
        if session:
            _log_local(f"Session loaded: {session_path}")

        # Try resolve credentials using existing token first.
        if session:
            creds, creds_payload = cls._resolve_my_team_credentials(
                normalized_server,
                access_token=session.access_token,
                timeout_seconds=timeout_s,
            )
            if creds:
                team_id, api_key = creds
                _log_local("Team confirmed via /matches/me")
                return cls(
                    server_url=normalized_server,
                    team_id=team_id,
                    api_key=api_key,
                    timeout_seconds=timeout_s,
                    log=log,
                )

            # Token might be expired/invalid.
            msg = _extract_message(creds_payload)
            _log_local(f"Session token not usable: {msg or 'unknown error'}")

        if not prompt_login and (mssv is None or password is None):
            raise RuntimeError(f"Not authenticated. No valid session at {session_path}")

        # Login (non-interactive if credentials are provided).
        while True:
            if mssv is not None and password is not None:
                _log_local("Logging in (student)...")
                input_mssv, input_password = mssv, password
            else:
                _log_local("Please login (student)")
                input_mssv, input_password = cls._prompt_student_credentials()

            new_session, login_payload = cls._login_student(
                normalized_server,
                mssv=input_mssv,
                password=input_password,
                timeout_seconds=timeout_s,
            )

            if not new_session:
                msg = _extract_message(login_payload) or "Login failed"
                _log_local(msg)
                # If caller provided credentials explicitly, don't loop forever.
                if mssv is not None and password is not None:
                    raise RuntimeError(msg)
                continue

            new_session.saved_at_unix = time.time()
            cls._save_session(session_path, new_session)
            _log_local(f"Login success. Session saved: {session_path}")

            creds, creds_payload = cls._resolve_my_team_credentials(
                normalized_server,
                access_token=new_session.access_token,
                timeout_seconds=timeout_s,
            )
            if not creds:
                msg = _extract_message(creds_payload) or "Cannot resolve team credentials"
                raise RuntimeError(msg)

            team_id, api_key = creds
            _log_local("Team confirmed via /matches/me")
            return cls(
                server_url=normalized_server,
                team_id=team_id,
                api_key=api_key,
                timeout_seconds=timeout_s,
                log=log,
            )

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
        stop_event: threading.Event | None = None,
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
            if stop_event and stop_event.is_set():
                return {
                    "status": "error",
                    "data": {},
                    "message": "Cancelled",
                    "error_type": "cancelled",
                    "http_status": None,
                }
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
            if stop_event:
                stop_event.wait(sleep_s)
            else:
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
        stop_event: threading.Event | None = None,
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
                stop_event=stop_event,
            )
            if init.get("status") != "success":
                message = init.get("message") or f"Cannot connect: {init}"
                # If wrong credential, fail fast so user can fix config.
                raise RuntimeError(str(message))

        sleep_s = max(0.05, float(poll_interval_seconds))
        steps = 0

        try:
            while True:
                if stop_event and stop_event.is_set():
                    return
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
        stop_event: threading.Event | None = None,
    ) -> None:
        """Phiên bản nâng cao: strategy nhận nguyên state_data (bao gồm board/turn/events...)."""
        if connect_first:
            init = self.connect_with_retry(
                start_heartbeat=start_heartbeat,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                stop_event=stop_event,
            )
            if init.get("status") != "success":
                message = init.get("message") or f"Cannot connect: {init}"
                raise RuntimeError(str(message))

        sleep_s = max(0.05, float(poll_interval_seconds))
        steps = 0
        try:
            while True:
                if stop_event and stop_event.is_set():
                    return
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
