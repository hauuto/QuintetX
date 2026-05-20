// Shared Frontend Configuration
const CONFIG = {
    API_BASE: "/api/v1",
    WS_URL: "/ws/match",
    BOARD_SIZE: 40,
    MATCH_STEP_DELAY_MS: (window.QX_RUNTIME && window.QX_RUNTIME.MATCH_STEP_DELAY_MS) ? window.QX_RUNTIME.MATCH_STEP_DELAY_MS : 750,
    MOVE_TIMEOUT_SECONDS: (window.QX_RUNTIME && window.QX_RUNTIME.MOVE_TIMEOUT_SECONDS) ? window.QX_RUNTIME.MOVE_TIMEOUT_SECONDS : 10,
    COLORS: {
        X: "#2563EB", // Blue
        O: "#DC2626", // Red
        PRIMARY: '#2563EB',
        INDIGO: '#4F46E5',
        BG: '#F8FAFC',
        BORDER: '#E5E7EB',
        SUCCESS: '#059669',
        WARNING: '#D97706',
        DANGER: '#DC2626',
        ERROR: '#991B1B',
        BOARD_BG: '#FFFFFF',
        BOARD_GRID: '#E0F2FE',
        BOARD_GRID_MAJOR: '#BFDBFE',
        BOARD_BORDER: '#60A5FA',
        BOARD_HOVER: 'rgba(37, 99, 235, 0.10)',
        BOARD_LAST_MOVE: 'rgba(250, 204, 21, 0.34)',
        BOARD_WIN: 'rgba(250, 204, 21, 0.18)',
        BOARD_WIN_BORDER: 'rgba(245, 158, 11, 0.55)',
    },
    LABELS: {
        STATUS_PLAYING: "Đang diễn ra",
        STATUS_WAITING: "Chờ người chơi",
        STATUS_FINISHED: "Kết thúc",
    }
};

// Tailwind Configuration (for Play CDN)
// This must run before the Tailwind script processes the page
window.tailwindConfig = {
    theme: {
        extend: {
            colors: {
                quintet: {
                    blue: CONFIG.COLORS.PRIMARY,
                    bg: CONFIG.COLORS.BG,
                    red: CONFIG.COLORS.O,
                    indigo: CONFIG.COLORS.INDIGO,
                    success: CONFIG.COLORS.SUCCESS,
                    warning: CONFIG.COLORS.WARNING,
                    danger: CONFIG.COLORS.DANGER,
                    border: CONFIG.COLORS.BORDER,
                }
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            }
        }
    }
};

