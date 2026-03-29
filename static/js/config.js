// Shared Frontend Configuration
const CONFIG = {
    API_BASE: "/api/v1",
    WS_URL: "/ws/match",
    BOARD_SIZE: 40,
    MATCH_STEP_DELAY_MS: (window.QX_RUNTIME && window.QX_RUNTIME.MATCH_STEP_DELAY_MS) ? window.QX_RUNTIME.MATCH_STEP_DELAY_MS : 750,
    MOVE_TIMEOUT_SECONDS: (window.QX_RUNTIME && window.QX_RUNTIME.MOVE_TIMEOUT_SECONDS) ? window.QX_RUNTIME.MOVE_TIMEOUT_SECONDS : 10,
    COLORS: {
        X: "#3547E5", // Blue
        O: "#E53535", // Red
        PRIMARY: '#3547E5',
        BG: '#F0F2F5',
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
                }
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            }
        }
    }
};

