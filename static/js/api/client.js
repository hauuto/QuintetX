(function () {
    function getToken() {
        return localStorage.getItem('qx_access_token') || '';
    }

    async function request(path, options) {
        const opts = options || {};
        const method = opts.method || 'GET';
        const headers = {
            ...(opts.headers || {}),
            Authorization: `Bearer ${getToken()}`,
        };

        if (opts.body && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }

        const response = await fetch(path, {
            method,
            headers,
            body: opts.body,
        });

        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }

        if (!response.ok || !payload || payload.status !== 'success') {
            const message = payload?.message || 'Không thể xử lý yêu cầu.';
            throw new Error(message);
        }

        return payload;
    }

    window.QXApi = {
        request,
    };
})();
