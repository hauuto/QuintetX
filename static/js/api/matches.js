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
    };

    window.QXApi.matches = matchesApi;
})();