from __future__ import annotations

SOLUTION_NAME = "Greedy (win/block + window scoring)"

BOARD_SIZE = 40
WIN_LEN = 5
A = 8

DIRECTIONS: list[tuple[int, int]] = [
    (1, 0),
    (0, 1),
    (1, 1),
    (1, -1),
]


def _other_side(side: str) -> str:
    return "O" if side == "X" else "X"


def _side_value(side: str) -> int:
    # Server encoding: X=1, O=2
    return 1 if side == "X" else 2


def _score_window(window: list[int], *, my_value: int, enemy_value: int) -> tuple[float, bool]:
    """Score a 4-cell window excluding the candidate cell.

    Returns: (score, instant_pick)
    - instant_pick True means candidate is immediate win/block.
    """
    my_count = sum(1 for v in window if v == my_value)
    enemy_count = sum(1 for v in window if v == enemy_value)

    if my_count > 0 and enemy_count > 0:
        return 0.0, False

    if my_count == WIN_LEN - 1:
        return 0.0, True

    if enemy_count == WIN_LEN - 1:
        return 0.0, True

    if my_count > 0:
        n = my_count
        return float((A**n) + n * A), False

    if enemy_count > 0:
        n = enemy_count
        return float(A**n), False

    return 0.0, False


def _score_cell(board: list[list[int]], x: int, y: int, *, my_value: int, enemy_value: int) -> tuple[float, bool]:
    score = 0.0

    for dx, dy in DIRECTIONS:
        for offset in range(WIN_LEN):
            x0 = x - offset * dx
            y0 = y - offset * dy
            x1 = x0 + (WIN_LEN - 1) * dx
            y1 = y0 + (WIN_LEN - 1) * dy

            if not (0 <= x0 < BOARD_SIZE and 0 <= y0 < BOARD_SIZE and 0 <= x1 < BOARD_SIZE and 0 <= y1 < BOARD_SIZE):
                continue

            window: list[int] = []
            for i in range(WIN_LEN):
                xi = x0 + i * dx
                yi = y0 + i * dy
                if xi == x and yi == y:
                    continue
                window.append(board[xi][yi])

            s, instant = _score_window(window, my_value=my_value, enemy_value=enemy_value)
            if instant:
                return score, True
            score += s

    return score, False


def _center_tiebreak(cells: list[tuple[int, int]]) -> tuple[int, int]:
    cx = (BOARD_SIZE - 1) / 2.0
    cy = (BOARD_SIZE - 1) / 2.0

    def key(pt: tuple[int, int]) -> tuple[float, int, int]:
        x, y = pt
        dist = (x - cx) ** 2 + (y - cy) ** 2
        return (dist, x, y)

    return sorted(cells, key=key)[0]


def strategy(state: dict) -> tuple[int, int]:
    """Greedy policy using the SDK runner.

    Expects state from `/api/v1/agent/state`:
    - state['board']: 40x40 int matrix (0 empty, 1 X, 2 O)
    - state['side']: 'X' or 'O'
    """
    side = str(state.get("side") or "").strip().upper() or "X"
    board = state.get("board") or []

    # Defensive normalization.
    if not isinstance(board, list) or not board:
        return 20, 20

    my_value = _side_value(side)
    enemy_value = _side_value(_other_side(side))

    best_score = -1.0
    best_cells: list[tuple[int, int]] = []

    # If board is empty -> center.
    has_any = False
    for row in board:
        for v in row:
            if v:
                has_any = True
                break
        if has_any:
            break
    if not has_any:
        return 20, 20

    for x in range(BOARD_SIZE):
        row = board[x]
        for y in range(BOARD_SIZE):
            if row[y] != 0:
                continue

            score, instant = _score_cell(board, x, y, my_value=my_value, enemy_value=enemy_value)
            if instant:
                return x, y

            if score > best_score:
                best_score = score
                best_cells = [(x, y)]
            elif score == best_score:
                best_cells.append((x, y))

    if not best_cells:
        return 0, 0

    return _center_tiebreak(best_cells)
