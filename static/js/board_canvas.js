(function () {
    function themeValue(key, fallback) {
        return (window.CONFIG && CONFIG.COLORS && CONFIG.COLORS[key]) || fallback;
    }

    function create(canvas, options) {
        const opts = Object.assign({ boardSize: (window.CONFIG && CONFIG.BOARD_SIZE) || 40, cellSize: 20, minCellSize: 12, maxCellSize: 36, coordMargin: 26, interactive: false, onCellClick: null, onHoverCell: null }, options || {});
        const ctx = canvas.getContext('2d');
        const state = { board: null, history: [], currentStep: null, hover: null, highlightedCell: null, lastMove: null, winningCells: [], currentTurn: null, mySide: null, status: null };

        function setCellSize(size) {
            const next = Math.max(opts.minCellSize, Math.min(opts.maxCellSize, Number(size) || opts.cellSize));
            opts.cellSize = next;
            resize();
            draw();
            return next;
        }

        function resize() {
            const boardSizePx = opts.boardSize * opts.cellSize;
            const size = boardSizePx + opts.coordMargin;
            const ratio = window.devicePixelRatio || 1;
            canvas.style.width = `${size}px`;
            canvas.style.height = `${size}px`;
            canvas.width = Math.floor(size * ratio);
            canvas.height = Math.floor(size * ratio);
            ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        }

        function moves() {
            const list = Array.isArray(state.history) ? state.history : [];
            if (state.currentStep === null || state.currentStep === undefined) return list;
            return list.slice(0, Math.max(0, Math.min(Number(state.currentStep) || 0, list.length)));
        }

        function draw() {
            const margin = opts.coordMargin;
            const boardSizePx = opts.boardSize * opts.cellSize;
            const size = boardSizePx + margin;
            ctx.clearRect(0, 0, size, size);
            ctx.fillStyle = '#F8FAFC';
            ctx.fillRect(0, 0, size, size);
            ctx.fillStyle = themeValue('BOARD_BG', '#FFFFFF');
            ctx.fillRect(margin, margin, boardSizePx, boardSizePx);
            for (let i = 0; i <= opts.boardSize; i += 1) {
                const p = margin + i * opts.cellSize + 0.5;
                const major = i % 5 === 0;
                ctx.strokeStyle = major ? themeValue('BOARD_GRID_MAJOR', '#BFDBFE') : themeValue('BOARD_GRID', '#E0F2FE');
                ctx.lineWidth = major ? 1.05 : 0.45;
                ctx.beginPath(); ctx.moveTo(p, margin); ctx.lineTo(p, margin + boardSizePx); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(margin, p); ctx.lineTo(margin + boardSizePx, p); ctx.stroke();
            }
            ctx.strokeStyle = themeValue('BOARD_BORDER', '#60A5FA');
            ctx.lineWidth = 1.3;
            ctx.strokeRect(margin + 0.5, margin + 0.5, boardSizePx - 1, boardSizePx - 1);

            ctx.fillStyle = '#64748B';
            ctx.font = '10px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            for (let i = 0; i < opts.boardSize; i += 5) {
                const center = margin + i * opts.cellSize + opts.cellSize / 2;
                ctx.fillText(String(i), center, margin / 2);
                ctx.fillText(String(i), margin / 2, center);
            }

            (state.winningCells || []).forEach((cell) => {
                const x = margin + cell.x * opts.cellSize;
                const y = margin + cell.y * opts.cellSize;
                ctx.fillStyle = themeValue('BOARD_WIN', 'rgba(250, 204, 21, 0.18)');
                ctx.fillRect(x, y, opts.cellSize, opts.cellSize);
                ctx.strokeStyle = themeValue('BOARD_WIN_BORDER', 'rgba(245, 158, 11, 0.55)');
                ctx.lineWidth = 1.5;
                ctx.strokeRect(x + 3, y + 3, opts.cellSize - 6, opts.cellSize - 6);
            });

            const renderedMoves = moves();
            const last = state.lastMove || renderedMoves[renderedMoves.length - 1];
            if (last) {
                ctx.fillStyle = themeValue('BOARD_LAST_MOVE', 'rgba(245, 158, 11, 0.22)');
                ctx.fillRect(margin + last.x * opts.cellSize, margin + last.y * opts.cellSize, opts.cellSize, opts.cellSize);
            }
            if (state.highlightedCell) {
                ctx.fillStyle = 'rgba(14, 165, 233, 0.18)';
                ctx.fillRect(margin + state.highlightedCell.x * opts.cellSize, margin + state.highlightedCell.y * opts.cellSize, opts.cellSize, opts.cellSize);
                ctx.strokeStyle = 'rgba(14, 165, 233, 0.8)';
                ctx.lineWidth = 1.5;
                ctx.strokeRect(margin + state.highlightedCell.x * opts.cellSize + 2, margin + state.highlightedCell.y * opts.cellSize + 2, opts.cellSize - 4, opts.cellSize - 4);
            }
            renderedMoves.forEach((move) => {
                const x = Number(move.x);
                const y = Number(move.y);
                const team = move.team || move.p;
                if (!Number.isFinite(x) || !Number.isFinite(y) || !team) return;
                const cx = margin + x * opts.cellSize + opts.cellSize / 2;
                const cy = margin + y * opts.cellSize + opts.cellSize / 2;
                const color = team === 'X' ? themeValue('X', '#2563EB') : themeValue('O', '#DC2626');
                ctx.save();
                ctx.fillStyle = color;
                ctx.font = `${Math.max(12, opts.cellSize - 6)}px Arial`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(team, cx, cy + 0.25);
                ctx.restore();
            });

            if (state.hover) {
                const hx = margin + state.hover.x * opts.cellSize;
                const hy = margin + state.hover.y * opts.cellSize;
                ctx.fillStyle = themeValue('BOARD_HOVER', 'rgba(37, 99, 235, 0.10)');
                ctx.fillRect(hx, hy, opts.cellSize, opts.cellSize);
            }
        }

        function eventCell(event) {
            const rect = canvas.getBoundingClientRect();
            const fullSize = opts.boardSize * opts.cellSize + opts.coordMargin;
            const scale = fullSize / rect.width;
            const x = Math.floor(((event.clientX - rect.left) * scale - opts.coordMargin) / opts.cellSize);
            const y = Math.floor(((event.clientY - rect.top) * scale - opts.coordMargin) / opts.cellSize);
            if (x < 0 || y < 0 || x >= opts.boardSize || y >= opts.boardSize) return null;
            return { x, y };
        }

        function occupied(cell) {
            if (state.board && state.board[cell.x] && state.board[cell.x][cell.y]) return true;
            return moves().some((move) => Number(move.x) === cell.x && Number(move.y) === cell.y);
        }

        canvas.addEventListener('mousemove', (event) => {
            state.hover = eventCell(event);
            if (typeof opts.onHoverCell === 'function') opts.onHoverCell(state.hover);
            draw();
        });
        canvas.addEventListener('mouseleave', () => { state.hover = null; if (typeof opts.onHoverCell === 'function') opts.onHoverCell(null); draw(); });
        canvas.addEventListener('click', (event) => {
            if (!opts.interactive || typeof opts.onCellClick !== 'function') return;
            const cell = eventCell(event);
            if (!cell || occupied(cell)) return;
            opts.onCellClick(cell.x, cell.y);
        });

        resize();
        draw();
        return {
            setState(next) {
                Object.assign(state, next || {});
                draw();
            },
            setCellSize,
            getCellSize() { return opts.cellSize; },
            zoomIn() { return setCellSize(opts.cellSize + 2); },
            zoomOut() { return setCellSize(opts.cellSize - 2); },
            resetZoom() { return setCellSize(20); },
            destroy() {},
        };
    }

    window.QXBoardCanvas = { create };
})();
