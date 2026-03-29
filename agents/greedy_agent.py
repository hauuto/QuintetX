from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

from QuintetX_SDK import QuintetXClient


def _load_solution(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"quintetx_solution_{path.stem}", str(path))
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load solution: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="QuintetX greedy agent (SDK + solutions)")
    parser.add_argument("--server-url", default=None)
    parser.add_argument("--poll", type=float, default=0.5, help="Polling interval (seconds)")
    parser.add_argument("--hb", type=float, default=5.0, help="Heartbeat interval (seconds)")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout (seconds)")
    args = parser.parse_args()

    server_url = (args.server_url or "").strip() or input("Server URL: ").strip()
    root_dir = Path(__file__).resolve().parents[1]
    session_file = root_dir / ".quintetx_session.json"

    solution_path = root_dir / "solutions" / "solution_greedy.py"
    if not solution_path.exists():
        raise RuntimeError(f"Missing solution file: {solution_path}")

    sol = _load_solution(solution_path)
    strategy = getattr(sol, "strategy", None)
    if not callable(strategy):
        raise RuntimeError("solution_greedy.py must export strategy(state)->(x,y)")

    client = QuintetXClient.from_student_login(
        server_url=server_url,
        session_file=session_file,
        timeout_seconds=float(args.timeout),
        log=print,
    )

    client.run_with_state(
        strategy,
        poll_interval_seconds=float(args.poll),
        heartbeat_interval_seconds=float(args.hb),
        connect_first=True,
        start_heartbeat=True,
    )


if __name__ == "__main__":
    main()
