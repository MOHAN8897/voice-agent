# Voxly `api.js` — Bearer JWT (Phase 5)

Apply in [voxly-ai](https://github.com/saiskm115/voxly-ai) `src/services/api.js` after backend PRD-12 A–D pass.

## Storage

```javascript
let accessToken = null;
let refreshToken = null;

export function setSession({ accessToken: a, refreshToken: r }) {
  accessToken = a;
  refreshToken = r;
}
```

## Fetch wrapper

```javascript
const API = import.meta.env.VITE_API_URL || '';

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 401 && refreshToken) {
    const r = await fetch(`${API}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken }),
    });
    if (r.ok) {
      const data = await r.json();
      accessToken = data.accessToken;
      refreshToken = data.refreshToken ?? refreshToken;
      headers.Authorization = `Bearer ${accessToken}`;
      res = await fetch(`${API}${path}`, { ...options, headers });
    }
  }
  return res;
}
```

## Auth endpoints

| Action | Path |
|--------|------|
| Signup | `POST /auth/signup` |
| Login | `POST /auth/login` |
| Logout | `POST /auth/logout` body `{ refreshToken }` |

Backend base URL should include `/api` if `VITE_API_URL=http://localhost:8000/api`.
