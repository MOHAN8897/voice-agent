const API = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';

export async function getSessionMeta() {
  const res = await fetch(`${API}/api/auth/session`);
  if (!res.ok) throw new Error(`session ${res.status}`);
  return res.json();
}

export async function login(email, password) {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

export async function signup(email, password, fullName = 'E2E User', orgName = 'E2E Org') {
  const res = await fetch(`${API}/api/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, fullName, orgName }),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

export async function getMe(accessToken) {
  const res = await fetch(`${API}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, data };
}

export async function listAgents(accessToken) {
  const res = await fetch(`${API}/api/agents`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, data };
}

export async function createAgent(accessToken, name) {
  const res = await fetch(`${API}/api/agents`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ name, languages: ['en-IN'] }),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, data };
}

export async function googleConfig() {
  const res = await fetch(`${API}/api/auth/google/config`);
  return { ok: res.ok, data: await res.json() };
}

export async function googleStartRedirect() {
  const res = await fetch(`${API}/api/auth/google/start`, { redirect: 'manual' });
  return { status: res.status, location: res.headers.get('location') };
}
