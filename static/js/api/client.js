(function () {
    let isRedirectingToLogin = false;

    function getToken() {
        return localStorage.getItem('qx_access_token') || '';
    }

    function getLoginPath() {
        const currentPath = window.location.pathname || '';
        if (currentPath.startsWith('/admin')) {
            return '/admin/login';
        }
        return '/login';
    }

    function redirectToLoginImmediately() {
        if (isRedirectingToLogin) {
            return;
        }
        isRedirectingToLogin = true;
        localStorage.removeItem('qx_access_token');
        localStorage.removeItem('qx_user');
        const loginPath = getLoginPath();
        const fromPath = window.location.pathname || '/';
        const unauthorizedUrl = `/401?next=${encodeURIComponent(loginPath)}&from=${encodeURIComponent(fromPath)}`;
        window.location.replace(unauthorizedUrl);
    }

    const originalFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        const response = await originalFetch(input, init);

        const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
        const isApiCall = url.includes('/api/v1/');

        if (isApiCall && response.status === 401) {
            redirectToLoginImmediately();
        }

        return response;
    };

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

        const response = await window.fetch(path, {
            method,
            headers,
            body: opts.body,
        });

        if (response.status === 401) {
            redirectToLoginImmediately();
            throw new Error('Unauthorized');
        }

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
