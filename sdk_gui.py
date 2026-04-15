from __future__ import annotations

import argparse
import os
import queue
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from QuintetX_SDK import QuintetXClient


Board = list[list[int]]
NextMoveFunc = Callable[[Board], tuple[int, int]]
StrategyFunc = Callable[[dict], tuple[int, int]]


@dataclass
class Solution:
    name: str
    path: Path
    next_move: Optional[NextMoveFunc]
    strategy: Optional[StrategyFunc]


_SOLUTION_NAME_RE = re.compile(r"^\s*SOLUTION_NAME\s*=\s*([\"'])(.*?)\1\s*$", re.MULTILINE)


def _infer_solution_name(path: Path, source: str) -> str:
    match = _SOLUTION_NAME_RE.search(source or "")
    if match:
        value = (match.group(2) or "").strip()
        if value:
            return value
    return path.stem


def _make_error_strategy(path: Path, exc: Exception) -> StrategyFunc:
    def _raise(_: dict) -> tuple[int, int]:
        raise RuntimeError(f"Solution failed to load: {path} | {exc}")

    return _raise


def _make_error_next_move(path: Path, exc: Exception) -> NextMoveFunc:
    def _raise(_: Board) -> tuple[int, int]:
        raise RuntimeError(f"Solution failed to load: {path} | {exc}")

    return _raise


def _load_solution(path: Path) -> Solution:
    code = path.read_text(encoding="utf-8")
    inferred_name = _infer_solution_name(path, code)

    namespace: dict = {
        "__file__": str(path),
        "__name__": f"quintetx_solution_{path.stem}",
    }

    try:
        exec(compile(code, str(path), "exec"), namespace, namespace)
        name = namespace.get("SOLUTION_NAME") or inferred_name
        next_move = namespace.get("next_move") if callable(namespace.get("next_move")) else None
        strategy = namespace.get("strategy") if callable(namespace.get("strategy")) else None

        if not next_move and not strategy:
            raise RuntimeError(f"Solution file must define next_move(board) or strategy(state): {path}")

        return Solution(name=str(name), path=path, next_move=next_move, strategy=strategy)
    except Exception as exc:
        # Per requirement: never skip solutions. Show it and fail only when executed.
        return Solution(
            name=f"{inferred_name} (error)",
            path=path,
            next_move=_make_error_next_move(path, exc),
            strategy=_make_error_strategy(path, exc),
        )


def discover_solutions(solution_dir: Path) -> list[Solution]:
    return discover_solutions_safe(solution_dir)


def discover_solutions_safe(solution_dir: Path, *, on_error: Callable[[Path, Exception], None] | None = None) -> list[Solution]:
    solution_dir.mkdir(parents=True, exist_ok=True)
    solutions: list[Solution] = []
    for path in sorted(solution_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            solutions.append(_load_solution(path))
        except Exception as exc:
            if on_error:
                on_error(path, exc)
            continue
    return solutions


def _resolve_solutions_dirs(*, root_dir: Path, explicit_dir: str | None) -> list[Path]:
    dirs: list[Path] = []

    def _add(p: Path) -> None:
        try:
            resolved = p.expanduser().resolve()
        except Exception:
            resolved = p
        if resolved not in dirs:
            dirs.append(resolved)

    if explicit_dir:
        _add(Path(explicit_dir))
        return dirs

    env_dir = (os.getenv("QUINTETX_SOLUTIONS_DIR") or os.getenv("QX_SOLUTIONS_DIR") or "").strip()
    if env_dir:
        _add(Path(env_dir))
        return dirs

    cwd_solutions = Path.cwd() / "solutions"
    if cwd_solutions.exists() and cwd_solutions.is_dir():
        _add(cwd_solutions)

    repo_solutions = root_dir / "solutions"
    if repo_solutions.exists() and repo_solutions.is_dir():
        _add(repo_solutions)

    if not dirs:
        _add(repo_solutions)

    return dirs


class GuiApp:
    def __init__(self, root: tk.Tk, *, root_dir: Path, solutions_dirs: list[Path]) -> None:
        self.root = root
        self.root_dir = root_dir
        self.session_file = self.root_dir / ".quintetx_session.json"
        self.solutions_dirs = solutions_dirs

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.client: QuintetXClient | None = None
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        self._build_ui()
        self._refresh_solutions()
        self._pump_logs()

    def _log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _build_ui(self) -> None:
        self.root.title("QuintetX SDK GUI")

        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Server URL").grid(row=0, column=0, sticky="w")
        self.server_var = tk.StringVar(value="http://127.0.0.1:8000")
        ttk.Entry(main, textvariable=self.server_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(main, text="MSSV").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.mssv_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.mssv_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(main, text="Password").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.password_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.password_var, show="*").grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(main, text="Solution").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.solution_var = tk.StringVar()
        self.solution_combo = ttk.Combobox(main, textvariable=self.solution_var, state="readonly")
        self.solution_combo.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        config_row = ttk.Frame(main)
        config_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for i in range(6):
            config_row.columnconfigure(i, weight=1)

        self.poll_var = tk.DoubleVar(value=0.5)
        self.hb_var = tk.DoubleVar(value=5.0)
        self.timeout_var = tk.DoubleVar(value=5.0)

        ttk.Label(config_row, text="poll(s)").grid(row=0, column=0, sticky="w")
        ttk.Entry(config_row, textvariable=self.poll_var, width=7).grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(config_row, text="hb(s)").grid(row=0, column=2, sticky="w")
        ttk.Entry(config_row, textvariable=self.hb_var, width=7).grid(row=0, column=3, sticky="w", padx=(4, 12))

        ttk.Label(config_row, text="timeout(s)").grid(row=0, column=4, sticky="w")
        ttk.Entry(config_row, textvariable=self.timeout_var, width=7).grid(row=0, column=5, sticky="w", padx=(4, 0))

        buttons = ttk.Frame(main)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        self.login_btn = ttk.Button(buttons, text="Login/Load Session", command=self.on_login)
        self.login_btn.pack(side="left")

        self.start_btn = ttk.Button(buttons, text="Start", command=self.on_start)
        self.start_btn.pack(side="left", padx=(8, 0))

        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.on_stop)
        self.stop_btn.pack(side="left", padx=(8, 0))

        self.refresh_btn = ttk.Button(buttons, text="Refresh Solutions", command=self._refresh_solutions)
        self.refresh_btn.pack(side="left", padx=(8, 0))

        self.clear_btn = ttk.Button(buttons, text="Clear Log", command=self._clear_log)
        self.clear_btn.pack(side="right")

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.log_text = tk.Text(main, height=18, wrap="word")
        self.log_text.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        main.rowconfigure(7, weight=1)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _append_log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {line}\n")
        self.log_text.see("end")

    def _pump_logs(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(100, self._pump_logs)

    def _refresh_solutions(self) -> None:
        solutions: list[Solution] = []
        for sol_dir in self.solutions_dirs:
            try:
                sols = discover_solutions_safe(sol_dir)
            except Exception as exc:
                self._log(f"Cannot scan solutions dir {sol_dir}: {exc}")
                continue
            solutions.extend(sols)

        # Ensure unique display names.
        seen: set[str] = set()
        final: list[Solution] = []
        for sol in solutions:
            display = sol.name
            if display in seen:
                display = f"{sol.name} [{sol.path.parent.name}/{sol.path.name}]"
            seen.add(display)
            final.append(Solution(name=display, path=sol.path, next_move=sol.next_move, strategy=sol.strategy))

        self.solutions = {sol.name: sol for sol in final}
        names = list(self.solutions.keys())
        self.solution_combo["values"] = names
        if names and not self.solution_var.get():
            self.solution_var.set(names[0])
        self._log("Solutions dirs:")
        for d in self.solutions_dirs:
            self._log(f"- {d}")

    def on_login(self) -> None:
        server = self.server_var.get().strip()
        timeout = float(self.timeout_var.get())
        mssv = self.mssv_var.get().strip() or None
        password = self.password_var.get().strip() or None

        try:
            self.status_var.set("Authenticating...")

            # If user did not enter credentials, try session-only.
            if not mssv or not password:
                try:
                    self.client = QuintetXClient.from_student_login(
                        server_url=server,
                        session_file=self.session_file,
                        timeout_seconds=timeout,
                        log=self._log,
                        prompt_login=False,
                    )
                except Exception:
                    raise RuntimeError("Please enter MSSV and Password (or create a session first).")
            else:
                # Non-interactive login attempt using provided credentials.
                self.client = QuintetXClient.from_student_login(
                    server_url=server,
                    session_file=self.session_file,
                    timeout_seconds=timeout,
                    log=self._log,
                    prompt_login=False,
                    mssv=mssv,
                    password=password,
                )

            self.status_var.set("Authenticated")
            self._log("Client ready")
        except Exception as exc:
            self.status_var.set("Auth failed")
            messagebox.showerror("Login failed", str(exc))

    def on_start(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Running", "Agent is already running")
            return

        if not self.client:
            self.on_login()
            if not self.client:
                return

        sol_name = self.solution_var.get().strip()
        sol = self.solutions.get(sol_name)
        if not sol:
            messagebox.showerror("No solution", "Please choose a solution")
            return

        poll_s = float(self.poll_var.get())
        hb_s = float(self.hb_var.get())

        self.stop_event.clear()
        self.status_var.set("Running")

        def worker() -> None:
            assert self.client is not None
            try:
                if sol.strategy:
                    self.client.run_with_state(
                        sol.strategy,
                        poll_interval_seconds=poll_s,
                        heartbeat_interval_seconds=hb_s,
                        connect_first=True,
                        start_heartbeat=True,
                        stop_event=self.stop_event,
                    )
                else:
                    assert sol.next_move
                    self.client.run(
                        sol.next_move,
                        poll_interval_seconds=poll_s,
                        heartbeat_interval_seconds=hb_s,
                        connect_first=True,
                        start_heartbeat=True,
                        stop_event=self.stop_event,
                    )
                self._log("Stopped")
            except Exception as exc:
                self._log(f"Error: {exc}")
            finally:
                self.status_var.set("Idle")

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def on_stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping...")


def main() -> None:
    parser = argparse.ArgumentParser(description="QuintetX SDK GUI")
    parser.add_argument("--server-url", default=None)
    parser.add_argument("--solutions-dir", default=None, help="Folder containing *.py solutions")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    solutions_dirs = _resolve_solutions_dirs(
        root_dir=root_dir,
        explicit_dir=str(args.solutions_dir).strip() if args.solutions_dir else None,
    )

    root = tk.Tk()
    app = GuiApp(root, root_dir=root_dir, solutions_dirs=solutions_dirs)
    if args.server_url:
        app.server_var.set(args.server_url)
    root.mainloop()


if __name__ == "__main__":
    main()
