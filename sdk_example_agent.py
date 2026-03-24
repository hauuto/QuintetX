"""Example agent using QuintetX_SDK.py

Run:

  python sdk_example_agent.py --server-url http://127.0.0.1:8000 --team-id T0001padjsl92 --api-key YOUR_API_KEY

This script:
- connects to QuintetX (/api/v1/agent/init)
- keeps heartbeat running in background
- polls state and plays when it's the agent's turn
"""

from __future__ import annotations

import argparse
from typing import Tuple

from QuintetX_SDK import QuintetXClient


def first_empty_strategy(state_data: dict) -> Tuple[int, int]:
    board = state_data["board"]
    for x in range(len(board)):
        for y in range(len(board[x])):
            if board[x][y] == 0:
                return x, y
    return 0, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="QuintetX example agent (first empty strategy)")
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--poll", type=float, default=0.5, help="Polling interval (seconds)")
    parser.add_argument("--hb", type=float, default=5.0, help="Heartbeat interval (seconds)")
    args = parser.parse_args()

    client = QuintetXClient(
        server_url=args.server_url,
        team_id=args.team_id,
        api_key=args.api_key,
    )

    client.run(
        first_empty_strategy,
        poll_interval_seconds=args.poll,
        heartbeat_interval_seconds=args.hb,
        connect_first=True,
        start_heartbeat=True,
    )


if __name__ == "__main__":
    main()
