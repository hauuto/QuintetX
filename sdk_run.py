from __future__ import annotations

import argparse
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional

from QuintetX_SDK import QuintetXClient


Board = list[list[int]]
NextMoveFunc = Callable[[Board], tuple[int, int]]
StrategyFunc = Callable[[dict], tuple[int, int]]


@dataclass
class LoadedSolution:
    name: str
    path: Path
    next_move: Optional[NextMoveFunc]
    strategy: Optional[StrategyFunc]


def _load_module_from_path(path: Path) -> ModuleType:
    module_name = f"quintetx_solution_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load solution: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def discover_solutions(solution_dir: Path) -> list[LoadedSolution]:
    solution_dir.mkdir(parents=True, exist_ok=True)

    solutions: list[LoadedSolution] = []
    for path in sorted(solution_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue

        module = _load_module_from_path(path)
        name = getattr(module, "SOLUTION_NAME", None) or path.stem
        next_move = getattr(module, "next_move", None)
        strategy = getattr(module, "strategy", None)

        if not callable(next_move) and not callable(strategy):
            continue

        solutions.append(
            LoadedSolution(
                name=str(name),
                path=path,
                next_move=next_move if callable(next_move) else None,
                strategy=strategy if callable(strategy) else None,
            )
        )

    return solutions


def pick_solution(solutions: list[LoadedSolution]) -> LoadedSolution:
    if not solutions:
        raise RuntimeError("No solutions found. Put .py files into ./solutions/")

    print("Available solutions:")
    for idx, sol in enumerate(solutions, start=1):
        kind = "strategy(state)" if sol.strategy else "next_move(board)"
        print(f"  {idx}. {sol.name} ({kind})")

    while True:
        raw = input("Choose solution number: ").strip()
        try:
            choice = int(raw)
        except ValueError:
            continue
        if 1 <= choice <= len(solutions):
            return solutions[choice - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description="QuintetX SDK runner (login + multi-solution)")
    parser.add_argument("--server-url", default=None)
    parser.add_argument("--poll", type=float, default=0.5, help="Polling interval (seconds)")
    parser.add_argument("--hb", type=float, default=5.0, help="Heartbeat interval (seconds)")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout (seconds)")
    args = parser.parse_args()

    server_url = (args.server_url or "").strip() or input("Server URL: ").strip()
    root_dir = Path(__file__).resolve().parent
    session_file = root_dir / ".quintetx_session.json"

    solutions_dir = root_dir / "solutions"
    solutions = discover_solutions(solutions_dir)
    sol = pick_solution(solutions)

    client = QuintetXClient.from_student_login(
        server_url=server_url,
        session_file=session_file,
        timeout_seconds=float(args.timeout),
        log=print,
    )

    if sol.strategy:
        client.run_with_state(
            sol.strategy,
            poll_interval_seconds=float(args.poll),
            heartbeat_interval_seconds=float(args.hb),
            connect_first=True,
            start_heartbeat=True,
        )
    else:
        assert sol.next_move is not None
        client.run(
            sol.next_move,
            poll_interval_seconds=float(args.poll),
            heartbeat_interval_seconds=float(args.hb),
            connect_first=True,
            start_heartbeat=True,
        )


if __name__ == "__main__":
    main()
