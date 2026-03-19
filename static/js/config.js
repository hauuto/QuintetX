// Shared Frontend Configuration
const CONFIG = {
    API_BASE: "/api/v1",
    WS_URL: "/ws/match",
    BOARD_SIZE: 40,
    COLORS: {
        X: "#3547E5", // Blue
        O: "#E53535", // Red
        PRIMARY: '#3547E5',
        BG: '#F0F2F5',
    },
    LABELS: {
        STATUS_PLAYING: "Đang diễn ra",
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

