(function () {
    if (!window.QXApi) {
        window.QXApi = {};
    }

    const groupsApi = {
        async getDashboard() {
            return window.QXApi.request('/api/v1/groups/me/dashboard');
        },

        async getMyGroup() {
            return window.QXApi.request('/api/v1/groups/me');
        },

        async listOpenGroups(params) {
            const query = new URLSearchParams({
                q: params.q || '',
                page: String(params.page || 1),
                page_size: String(params.pageSize || 10),
            });
            return window.QXApi.request(`/api/v1/groups/open-missing?${query.toString()}`);
        },

        async createGroup(payload) {
            return window.QXApi.request('/api/v1/groups', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
        },

        async requestJoin(groupId, message) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/join`, {
                method: 'POST',
                body: JSON.stringify({ message: message || '' }),
            });
        },

        async renameGroup(groupId, name) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/name`, {
                method: 'PATCH',
                body: JSON.stringify({ name }),
            });
        },

        async kickMember(groupId, userId) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/members/${userId}`, {
                method: 'DELETE',
            });
        },

        async approveJoinRequest(groupId, userId) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/join-requests/${userId}/approve`, {
                method: 'POST',
            });
        },

        async rejectJoinRequest(groupId, userId) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/join-requests/${userId}/reject`, {
                method: 'POST',
            });
        },

        async inviteByMssv(groupId, mssv) {
            return window.QXApi.request(`/api/v1/groups/${groupId}/invite`, {
                method: 'POST',
                body: JSON.stringify({ mssv }),
            });
        },

        async getMyNotifications(unreadOnly) {
            const query = unreadOnly ? '?unread_only=true' : '';
            return window.QXApi.request(`/api/v1/groups/notifications/me${query}`);
        },

        async markNotificationRead(notificationId) {
            return window.QXApi.request(`/api/v1/groups/notifications/${notificationId}/read`, {
                method: 'PATCH',
            });
        },

        async markAllNotificationsRead() {
            return window.QXApi.request('/api/v1/groups/notifications/read-all', {
                method: 'PATCH',
            });
        },

        async acceptInvite(notificationId) {
            return window.QXApi.request(`/api/v1/groups/invites/${notificationId}/accept`, {
                method: 'POST',
            });
        },

        async rejectInvite(notificationId) {
            return window.QXApi.request(`/api/v1/groups/invites/${notificationId}/reject`, {
                method: 'POST',
            });
        },
    };

    window.QXApi.groups = groupsApi;
})();
