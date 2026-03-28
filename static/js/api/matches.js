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

        async createMatch(payload) {
            return window.QXApi.request('/api/v1/matches', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
        },

        async getMatchEvents(matchId, limit) {
            const capped = Math.max(1, Math.min(Number(limit || 100), 300));
            return window.QXApi.request(`/api/v1/matches/${matchId}/events?limit=${capped}`);
        },
    };

    window.QXApi.matches = matchesApi;
})();