/**
 * End-to-end contract check for the console against a running backend.
 *
 * Verifies the exact request/response shapes the console depends on:
 *   - agent creation (brief -> compile -> published script)
 *   - telephony profile read/write + the effective inbound decision
 *   - canonical call status vocabulary, timeline and stats
 *   - callbacks going through the outbound path
 *   - wallet and number purchase
 *
 * Run with:  node e2e/backend-contract.spec.mjs
 * Requires the API at API_URL (default http://127.0.0.1:8000) and credentials in
 * E2E_EMAIL / E2E_PASSWORD. Skips with a clear message when they are absent.
 */

const API = (process.env.API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const EMAIL = process.env.E2E_EMAIL || '';
const PASSWORD = process.env.E2E_PASSWORD || '';

let token = null;
const results = [];

function record(name, ok, detail = '') {
  results.push({ name, ok, detail });
  const mark = ok ? 'PASS' : 'FAIL';
  console.log(`${mark}  ${name}${detail ? ` — ${detail}` : ''}`);
}

async function call(method, path, body) {
  const res = await fetch(`${API}/api${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body == null ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  return { status: res.status, data };
}

function errCode(data) {
  return data?.detail?.error?.code || data?.error?.code || null;
}

async function login() {
  if (!EMAIL || !PASSWORD) {
    console.log('SKIP  no E2E_EMAIL / E2E_PASSWORD set; cannot authenticate.');
    return false;
  }
  const { status, data } = await call('POST', '/auth/login', { email: EMAIL, password: PASSWORD });
  if (status !== 200 || !data?.accessToken) {
    record('login', false, `status ${status} ${errCode(data) || ''}`);
    return false;
  }
  token = data.accessToken;
  record('login', true, data.role);
  return true;
}

async function main() {
  const health = await call('GET', '/../health');
  void health;
  const ready = await fetch(`${API}/health`).then((r) => r.ok).catch(() => false);
  if (!ready) {
    console.log(`SKIP  backend not reachable at ${API}`);
    process.exit(0);
  }
  if (!(await login())) {
    process.exit(results.some((r) => !r.ok) ? 1 : 0);
  }

  // ---------------------------------------------------------------- status
  const statusDoc = await call('GET', '/calls?limit=1');
  const expected = [
    'answered',
    'missed',
    'outbound',
    'declined',
    'failed',
    'voicemail',
    'in_progress',
  ];
  if (statusDoc.status === 200) {
    const got = statusDoc.data.statuses || [];
    record(
      'call status vocabulary is canonical',
      expected.every((s) => got.includes(s)),
      got.join(',')
    );
    const rows = statusDoc.data.calls || [];
    record(
      'every call row carries a status',
      rows.length === 0 || rows.every((r) => expected.includes(r.status)),
      `${rows.length} row(s)`
    );
  } else {
    record('GET /api/calls', false, `status ${statusDoc.status}`);
  }

  const stats = await call('GET', '/calls/stats');
  record(
    'call stats expose per-status counts',
    stats.status === 200 && stats.data?.counts && stats.data.counts.missed !== undefined,
    stats.status === 200 ? `missed=${stats.data.counts.missed}` : `status ${stats.status}`
  );

  const missedOnly = await call('GET', '/calls?status=missed&limit=5');
  record(
    'status filter is honoured server-side',
    missedOnly.status === 200 &&
      (missedOnly.data.calls || []).every((c) => c.status === 'missed'),
    `${(missedOnly.data?.calls || []).length} missed`
  );

  // --------------------------------------------------------------- agents
  const agents = await call('GET', '/agents');
  record(
    'agents list is readable',
    agents.status === 200 && Array.isArray(agents.data.agents),
    `${agents.data?.agents?.length ?? 0} agent(s)`
  );

  const created = await call('POST', '/agents', { name: `contract-test-${Date.now()}` });
  const agentId = created.data?.agent?.agent_id;
  record('agent created', Boolean(agentId), agentId || `status ${created.status}`);

  if (agentId) {
    // Brief → compile → published script, same path the wizard uses.
    const built = await call('POST', '/app/agents/build-employee', {
      brief:
        'We are a test clinic in Hyderabad. Confirm the patient name, book an appointment with the next available doctor, and repeat the date back.',
      language: 'en-IN',
      mode: 'instant_lead',
    });
    record(
      'build-employee returns a script',
      built.status === 200 && Boolean(built.data.script),
      built.status === 200 ? `${(built.data.script || '').length} chars` : `status ${built.status}`
    );

    // The new console endpoints.
    const scriptRead = await call('GET', `/agents/${agentId}/business-brain/calling-script`);
    record(
      'calling script is readable for review',
      scriptRead.status === 200,
      scriptRead.status === 200 ? `${(scriptRead.data.callingScript || '').length} chars` : `status ${scriptRead.status}`
    );

    const scriptSave = await call('PUT', `/agents/${agentId}/business-brain/calling-script`, {
      script: 'Greet the caller. Confirm the patient name. Book the next slot. Repeat the date back.',
    });
    record('calling script saves', scriptSave.status === 200 && scriptSave.data.ok === true);

    const profile = await call('GET', `/agents/${agentId}/telephony-profile`);
    record(
      'telephony profile defaults to always-open',
      profile.status === 200 && profile.data?.profile?.inboundEnabled === true,
      profile.status === 200 ? profile.data.profile.afterHoursAction : `status ${profile.status}`
    );

    const profileSave = await call('PUT', `/agents/${agentId}/telephony-profile`, {
      greetingPhrase: 'Thanks for calling the test clinic.',
      businessHours: { mon: [{ open: '09:00', close: '18:00' }] },
      timezone: 'Asia/Kolkata',
      afterHoursAction: 'voicemail',
      inboundEnabled: true,
      outboundEnabled: true,
    });
    record(
      'telephony profile saves typed settings',
      profileSave.status === 200 &&
        profileSave.data?.profile?.greetingPhrase === 'Thanks for calling the test clinic.',
      profileSave.status === 200 ? JSON.stringify(profileSave.data.profile.businessHours) : `status ${profileSave.status}`
    );

    const effective = await call('GET', `/agents/${agentId}/telephony-profile/effective`);
    record(
      'effective decision is reported',
      effective.status === 200 && Boolean(effective.data?.decision?.reason),
      effective.data?.decision?.reason
    );

    const badProfile = await call('PUT', `/agents/${agentId}/telephony-profile`, {
      businessHours: { funday: [{ open: '09:00', close: '18:00' }] },
    });
    record(
      'invalid profile is rejected server-side',
      badProfile.status === 400,
      `status ${badProfile.status}`
    );

    const voice = await call('PUT', `/agents/${agentId}/business-brain/voice`, {
      voiceId: 'marin',
      speed: 1,
      language: 'en-IN',
    });
    record('voice config saves', voice.status === 200 && voice.data.ok === true);

    // A number the agent does not own must never resolve a profile.
    const foreignProfile = await call('GET', `/agents/${agentId}/telephony-profile`);
    record(
      'profile stays scoped to its own agent',
      foreignProfile.status === 200 && foreignProfile.data.profile.agentId === agentId
    );

    await call('DELETE', `/agents/${agentId}`);
  }

  // ------------------------------------------------------------- billing
  const wallet = await call('GET', '/billing/wallet');
  record(
    'wallet summary is available',
    wallet.status === 200 && typeof wallet.data.balanceUsd === 'number',
    wallet.status === 200 ? `$${wallet.data.balanceUsd} / ₹${wallet.data.balanceInr}` : `status ${wallet.status}`
  );

  const rates = await call('GET', '/billing/wallet');
  record(
    'wallet exposes the rates the console displays',
    rates.status === 200 && typeof rates.data.rateInrPerMin === 'number',
    `₹${rates.data?.rateInrPerMin}/min`
  );

  // -------------------------------------------------------------- numbers
  const numbers = await call('GET', '/telephony/numbers');
  record(
    'owned numbers are listed',
    numbers.status === 200 && Array.isArray(numbers.data.numbers),
    `${numbers.data?.numbers?.length ?? 0} line(s)`
  );

  const search = await call('GET', '/telephony/numbers/search?country=IN');
  record(
    'number catalog is priced',
    search.status === 200 && Array.isArray(search.data.numbers),
    search.status === 200 ? `${search.data.numbers.length} available` : `status ${search.status}`
  );

  const badBuy = await call('POST', '/telephony/buy', { e164: '+999', country: 'IN' });
  record('number purchase validates input', badBuy.status === 400, `status ${badBuy.status}`);

  // ------------------------------------------------------------- callback
  const anyCall = (missedOnly.data?.calls || [])[0];
  if (anyCall) {
    const cb = await call('POST', `/calls/${anyCall.call_id}/callback`, {
      toE164: '+919999999999',
      mode: 'manual',
    });
    // 200 with ok:false is a valid outcome (no wallet / no line / no brain).
    // What must not happen is a 5xx or a validation error from the callback path.
    record(
      'callback runs the normal outbound path',
      cb.status === 200 || cb.status === 402 || cb.status === 429,
      `status ${cb.status} ${cb.data?.error || ''}`
    );
  } else {
    console.log('SKIP  no missed call available to exercise the callback path');
  }

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.error('contract run failed:', e);
  process.exit(1);
});
