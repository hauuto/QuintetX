from __future__ import annotations

import argparse
import getpass
from typing import Tuple

from QuintetX_SDK import QuintetXClient


def next_move(board: list[list[int]]) -> Tuple[int, int]:
    """EDIT HERE: return (x, y) for the next move based on current board."""
    for x in range(len(board)):
        for y in range(len(board[x])):
            if board[x][y] == 0:
                return x, y
    return 0, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="QuintetX example agent (first empty strategy)")
    parser.add_argument("--server-url", default=None)
    parser.add_argument("--team-id", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--poll", type=float, default=0.5, help="Polling interval (seconds)")
    parser.add_argument("--hb", type=float, default=5.0, help="Heartbeat interval (seconds)")
    args = parser.parse_args()

    server_url = (args.server_url or "").strip() or input("Server URL: ").strip()
    team_id = (args.team_id or "").strip() or input("Team ID: ").strip()
    api_key = (args.api_key or "").strip() or getpass.getpass("API key: ").strip()

    client = QuintetXClient(
        server_url=server_url,
        team_id=team_id,
        api_key=api_key,
    )

    client.run(
        next_move,
        poll_interval_seconds=args.poll,
        heartbeat_interval_seconds=args.hb,
        connect_first=True,
        start_heartbeat=True,
    )


if __name__ == "__main__":
    main()


# Cách chạy agent này:
# 1. python filename.py --server-url <SERVER_URL> --team-id <TEAM_ID> --api-key <API_KEY>