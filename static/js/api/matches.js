(function () {
    if (!window.QXApi) {
        window.QXApi = {};
    }

    const matchesApi = {
        async getTeamOptions() {
            return window.QXApi.request('/api/v1/matches/teams/options');
        },

        async getOverview() {
            return window.QXApi.request('/api/v1/matches/overview');
        },

        async getMyMatch() {
            return window.QXApi.request('/api/v1/matches/me');
        },

        async getMyMatchSummary(sinceRev) {
            const v = Number(sinceRev);
            const qs = Number.isFinite(v) ? `?since_rev=${encodeURIComponent(String(v))}` : '';
            return window.QXApi.request(`/api/v1/matches/me/summary${qs}`);
        },

        async createMatch(payload) {
            return window.QXApi.request('/api/v1/matches', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
        },

        async createGreedyBotMatch(payload) {
            return window.QXApi.request('/api/v1/matches/bot', {
                method: 'POST',
                body: JSON.stringify(payload || {}),
            });
        },

        async createPlayerRoom(payload) {
            return window.QXApi.request('/api/v1/matches/player-room', {
                method: 'POST',
                body: JSON.stringify(payload || {}),
            });
        },

        async joinPlayerRoom(matchId) {
            const normalizedId = encodeURIComponent(String(matchId || ''));
            return window.QXApi.request(`/api/v1/matches/${normalizedId}/join`, {
                method: 'POST',
            });
        },

        async getMatchEvents(matchId, limit) {
            const capped = Math.max(1, Math.min(Number(limit || 100), 300));
            return window.QXApi.request(`/api/v1/matches/${matchId}/events?limit=${capped}`);
        },

        async getMatch(matchId) {
            return window.QXApi.request(`/api/v1/matches/${encodeURIComponent(String(matchId || ''))}`);
        },

        async submitMove(matchId, payload) {
            const normalizedId = encodeURIComponent(String(matchId || ""));
            return window.QXApi.request(`/api/v1/matches/${normalizedId}/move`, {
                method: "POST",
                body: JSON.stringify(payload || {}),
            });
        },

        async deleteMatch(matchId) {
            const normalizedId = encodeURIComponent(String(matchId || ''));
            return window.QXApi.request(`/api/v1/matches/${normalizedId}`, {
                method: 'DELETE',
            });
        },

        async getMyHistory(limit) {
            const capped = Math.max(1, Math.min(Number(limit || 50), 200));
            return window.QXApi.request(`/api/v1/matches/my/history?limit=${capped}`);
        },
    };

    window.QXApi.matches = matchesApi;
})();



