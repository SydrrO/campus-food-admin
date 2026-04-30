const ADMIN_TOKEN_KEY = 'admin_token';
let authCheckPromise = null;

function getLoginRedirectTarget() {
  const fileName = window.location.pathname.split('/').pop() || 'index.html';
  return `${fileName}${window.location.search}${window.location.hash}`;
}

function redirectToLogin() {
  const target = getLoginRedirectTarget();
  window.location.href = `login.html?redirect=${encodeURIComponent(target)}`;
}

function getToken() {
  const sessionToken = sessionStorage.getItem(ADMIN_TOKEN_KEY) || '';
  if (sessionToken) {
    return sessionToken;
  }

  const legacyToken = localStorage.getItem(ADMIN_TOKEN_KEY) || '';
  if (legacyToken) {
    sessionStorage.setItem(ADMIN_TOKEN_KEY, legacyToken);
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  }
  return legacyToken;
}

function setToken(token) {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

function clearToken() {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  authCheckPromise = null;
}

function isLoggedIn() {
  return !!getToken();
}

function buildHeaders(extraHeaders = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...extraHeaders
  };

  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

const REQUEST_TIMEOUT_MS = 15000;

async function request(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${url}`, {
      method: options.method || 'GET',
      headers: buildHeaders(options.headers),
      body: options.body || undefined,
      credentials: 'omit',
      signal: controller.signal
    });

    if (response.status === 401) {
      clearToken();
      if (!window.location.pathname.endsWith('login.html')) {
        redirectToLogin();
      }
      throw new Error('未授权，请重新登录');
    }

    const rawText = await response.text();
    let payload = null;

    if (rawText) {
      try {
        payload = JSON.parse(rawText);
      } catch (error) {
        throw new Error('服务返回异常，请稍后重试');
      }
    }

    if (response.ok && payload.code === 200) {
      return payload.data;
    }

    throw new Error((payload && (payload.message || payload.detail)) || '请求失败');
  } catch (error) {
    if (error && error.name === 'AbortError') {
      throw new Error('请求超时，请稍后重试');
    }

    if (error instanceof Error) {
      throw error;
    }
    throw new Error('网络错误');
  } finally {
    clearTimeout(timeoutId);
  }
}

async function login(username, password) {
  const response = await request('/admin/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });

  setToken(response.token);
  return response;
}

function logout() {
  clearToken();
  window.location.href = 'login.html';
}

async function validateAdminSession() {
  return request('/admin/auth/me');
}

function checkAuth() {
  const isLoginPage = window.location.pathname.endsWith('login.html');
  if (!isLoggedIn() && !isLoginPage) {
    redirectToLogin();
    return Promise.resolve(false);
  }

  if (isLoginPage || !isLoggedIn()) {
    return Promise.resolve(true);
  }

  if (!authCheckPromise) {
    authCheckPromise = validateAdminSession()
      .then(() => true)
      .catch(() => false);
  }
  return authCheckPromise;
}
