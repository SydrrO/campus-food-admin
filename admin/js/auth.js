const ADMIN_TOKEN_KEY = 'admin_token';
const ADMIN_CREDS_KEY = 'admin_remembered_creds';
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
  return sessionStorage.getItem(ADMIN_TOKEN_KEY) || localStorage.getItem(ADMIN_TOKEN_KEY) || '';
}

function setToken(token, persist) {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
  if (persist) {
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  }
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

function getRememberedCreds() {
  try {
    const raw = localStorage.getItem(ADMIN_CREDS_KEY);
    if (raw) {
      return JSON.parse(raw);
    }
  } catch (e) { /* corrupted */ }
  return null;
}

function saveRememberedCreds(username, password) {
  localStorage.setItem(ADMIN_CREDS_KEY, JSON.stringify({ username, password }));
}

function clearRememberedCreds() {
  localStorage.removeItem(ADMIN_CREDS_KEY);
}

async function login(username, password, persist) {
  const response = await request('/admin/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });

  setToken(response.token, persist);
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
