from __future__ import annotations

SOLUTION_NAME = "First empty cell"


def next_move(board: list[list[int]]) -> tuple[int, int]:
    for x in range(len(board)):
        for y in range(len(board[x])):
            if board[x][y] == 0:
                return x, y
    return 0, 0
