const isHttpOrigin = window.location.origin && /^https?:/i.test(window.location.origin);
const isDevAdmin = window.location.pathname.startsWith('/dev-admin');

const API_BASE_URL = isHttpOrigin
  ? `${window.location.origin}${isDevAdmin ? '/dev-api/v1' : '/api/v1'}`
  : 'https://sydroo.top/api/v1';
