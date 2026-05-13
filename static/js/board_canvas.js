(function () {
    function create(canvas, options) {
        const opts = Object.assign({ boardSize: (window.CONFIG && CONFIG.BOARD_SIZE) || 40, cellSize: 20, interactive: false, onCellClick: null }, options || {});
        const ctx = canvas.getContext('2d');
        const state = { board: null, history: [], currentStep: null, hover: null, lastMove: null, winningCells: [], currentTurn: null, mySide: null, status: null };

        function resize() {
            const size = opts.boardSize * opts.cellSize;
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
            const size = opts.boardSize * opts.cellSize;
            ctx.clearRect(0, 0, size, size);
            const bg = ctx.createLinearGradient(0, 0, size, size);
            bg.addColorStop(0, '#fff7df');
            bg.addColorStop(1, '#f4d38a');
            ctx.fillStyle = bg;
            ctx.fillRect(0, 0, size, size);
            ctx.strokeStyle = '#d6b46d';
            ctx.lineWidth = 1;
            for (let i = 0; i <= opts.boardSize; i += 1) {
                const p = i * opts.cellSize + 0.5;
                ctx.lineWidth = i % 5 === 0 ? 1.4 : 0.7;
                ctx.beginPath(); ctx.moveTo(p, 0); ctx.lineTo(p, size); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(0, p); ctx.lineTo(size, p); ctx.stroke();
            }

            (state.winningCells || []).forEach((cell) => {
                ctx.fillStyle = 'rgba(134, 239, 172, 0.75)';
                ctx.fillRect(cell.x * opts.cellSize, cell.y * opts.cellSize, opts.cellSize, opts.cellSize);
            });

            const renderedMoves = moves();
            renderedMoves.forEach((move) => {
                const x = Number(move.x);
                const y = Number(move.y);
                const team = move.team || move.p;
                if (!Number.isFinite(x) || !Number.isFinite(y) || !team) return;
                const cx = x * opts.cellSize + opts.cellSize / 2;
                const cy = y * opts.cellSize + opts.cellSize / 2;
                const color = team === 'X' ? ((window.CONFIG && CONFIG.COLORS && CONFIG.COLORS.X) || '#3547E5') : ((window.CONFIG && CONFIG.COLORS && CONFIG.COLORS.O) || '#E53535');
                ctx.save();
                ctx.shadowColor = 'rgba(0,0,0,0.25)';
                ctx.shadowBlur = 4;
                ctx.shadowOffsetY = 1;
                ctx.beginPath();
                ctx.fillStyle = color;
                ctx.arc(cx, cy, opts.cellSize * 0.38, 0, Math.PI * 2);
                ctx.fill();
                ctx.shadowBlur = 0;
                ctx.fillStyle = 'rgba(255,255,255,0.9)';
                ctx.font = `800 ${Math.max(10, opts.cellSize - 9)}px Arial`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(team, cx, cy + 0.5);
                ctx.restore();
            });

            const last = state.lastMove || renderedMoves[renderedMoves.length - 1];
            if (last) {
                ctx.strokeStyle = '#facc15';
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.arc(last.x * opts.cellSize + opts.cellSize / 2, last.y * opts.cellSize + opts.cellSize / 2, opts.cellSize * 0.47, 0, Math.PI * 2);
                ctx.stroke();
            }

            if (opts.interactive && state.hover && state.status === 'playing' && state.currentTurn === state.mySide) {
                ctx.fillStyle = 'rgba(37, 99, 235, 0.16)';
                ctx.beginPath();
                ctx.arc(state.hover.x * opts.cellSize + opts.cellSize / 2, state.hover.y * opts.cellSize + opts.cellSize / 2, opts.cellSize * 0.34, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        function eventCell(event) {
            const rect = canvas.getBoundingClientRect();
            const scale = (opts.boardSize * opts.cellSize) / rect.width;
            const x = Math.floor((event.clientX - rect.left) * scale / opts.cellSize);
            const y = Math.floor((event.clientY - rect.top) * scale / opts.cellSize);
            if (x < 0 || y < 0 || x >= opts.boardSize || y >= opts.boardSize) return null;
            return { x, y };
        }

        function occupied(cell) {
            if (state.board && state.board[cell.x] && state.board[cell.x][cell.y]) return true;
            return moves().some((move) => Number(move.x) === cell.x && Number(move.y) === cell.y);
        }

        canvas.addEventListener('mousemove', (event) => {
            if (!opts.interactive) return;
            state.hover = eventCell(event);
            draw();
        });
        canvas.addEventListener('mouseleave', () => { state.hover = null; draw(); });
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
            destroy() {},
        };
    }

    window.QXBoardCanvas = { create };
})();
