import { test, expect } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile } from 'node:fs/promises';

const folder = '../artifacts/call-quality-review/capabilities-memory-integrations-20261026';

async function setup(page, failActivation = false, failureStatus = 503) {
  const state = { initiations: 0, activations: [], active: false };
  const user = { id: 'integration-test', userId: 'integration-test', fullName: 'Integration Tester', name: 'Integration Tester', email: 'integration-test@example.invalid', hasCompletedOnboarding: true, role: 'subscriber', tenantId: 'integration-test-tenant' };
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  await page.route('**/@nangohq_frontend.js*', (route) => route.fulfill({ contentType: 'text/javascript', body: `
    export default class TestConnect {
      openConnectUI({onEvent}) {
        const form = document.createElement('div');
        form.setAttribute('role', 'dialog'); form.setAttribute('aria-label', 'Test authorization');
        form.style = 'position:fixed;inset:20%;z-index:999999;background:white;padding:40px';
        for (const [label, event] of [['Complete test authorization', {type:'connect',payload:{connectionId:'synthetic-owned-connection'}}],['Fail test authorization',{type:'error'}]]) {
          const button = document.createElement('button'); button.textContent = label;
          button.onclick = () => onEvent(event); form.appendChild(button);
        }
        document.body.appendChild(form);
        return { close() { form.remove(); onEvent({type:'close'}); } };
      }
    }` }));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data = { ok: true, items: [] }, status = 200;
    if (path === '/api/auth/me') data = { user, tenant: { tenantId: user.tenantId }, role: 'subscriber' };
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/integrations') data = { items: state.active ? [{ app_name: 'GOOGLECALENDAR', status: 'ACTIVE' }] : [] };
    else if (path === '/api/integrations/catalog') data = { items: [{ id: 'GOOGLECALENDAR', name: 'Google Calendar', category: 'Scheduling', auth_type: 'oauth', timing: 'in_call', actions: ['Find Free Slots'] }] };
    else if (path.endsWith('/GOOGLECALENDAR/connect')) { state.initiations++; data = { status: 'INITIATED', session_token: 'synthetic-session' }; }
    else if (path.endsWith('/GOOGLECALENDAR/activate')) {
      state.activations.push(request.postDataJSON());
      status = failActivation && state.activations.length === 1 ? failureStatus : 200;
      state.active = status === 200;
      data = status === 200 ? { status: 'ACTIVE' } : { detail: 'Verification temporarily unavailable' };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.addInitScript(({ token, user }) => {
    for (const prefix of ['voxly', 'dialtact']) {
      sessionStorage.setItem(`${prefix}_auth_token`, token);
      localStorage.setItem(`${prefix}_auth_session`, JSON.stringify(user));
      localStorage.setItem(`${prefix}_tour_completed`, 'true');
      localStorage.setItem(`${prefix}_tour_completed_default`, 'true');
      localStorage.setItem(`${prefix}_tour_completed_${user.email}`, 'true');
    }
  }, { token, user });
  await page.goto('/#dashboard/integrations');
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  await page.getByRole('button', { name: 'Continue securely' }).click();
  await expect(page.getByRole('dialog', { name: 'Test authorization' })).toBeVisible();
  return state;
}

test('failed backend verification retries the same authorization without duplicate OAuth', async ({ page }) => {
  const state = await setup(page, true);
  await page.getByRole('button', { name: 'Complete test authorization' }).click();
  await expect(page.getByText('Connection could not be verified.', { exact: false })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Test authorization' })).toBeHidden();
  await page.getByRole('button', { name: 'Continue securely' }).click();
  await expect(page.getByRole('button', { name: 'Disconnect', exact: true })).toBeVisible();
  expect(state.initiations).toBe(1);
  expect(state.activations).toHaveLength(2);
  expect(state.activations[1].connection_id).toBe(state.activations[0].connection_id);
  if (process.env.RETICLE_VERIFY) {
    const commands = [{ tool: 'reticle_act_and_wait', args: {
      target: { role: 'button', name: 'Refresh Catalog' }, action: 'click',
      until: { kind: 'allOf', predicates: [{ kind: 'net', method: 'GET', urlContains: '/api/integrations', status: 200 }, { kind: 'text', contains: 'Active' }] },
      intent: 'An authorized integration survives activation retry and catalog refresh without a second authorization.',
    } }];
    const { stdout } = await promisify(execFile)('python', ['../artifacts/call-quality-review/callback-farewell-20261026/reticle_rpc.py', JSON.stringify(commands), page.url()], { timeout: 55_000 });
    await writeFile(`${folder}/reticle-recovery.jsonl`, stdout);
    const evidence = JSON.parse(stdout.trim().split('\n').at(-1)).result.structuredContent;
    expect(evidence.verified).toBe('yes');
  }
});

test('provider authorization error closes the form and makes retry available', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('button', { name: 'Fail test authorization' }).click();
  await expect(page.getByText('Authorization did not complete.', { exact: false })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Test authorization' })).toBeHidden();
  await expect(page.getByRole('button', { name: 'Continue securely' })).toBeEnabled();
  expect(state.activations).toHaveLength(0);
  await page.getByRole('button', { name: 'Continue securely' }).click();
  await page.getByRole('button', { name: 'Complete test authorization' }).click();
  await expect(page.getByRole('button', { name: 'Disconnect', exact: true })).toBeVisible();
  expect(state.initiations).toBe(2);
});

test('permanent connection rejection allows fresh authorization', async ({ page }) => {
  const state = await setup(page, true, 403);
  await page.getByRole('button', { name: 'Complete test authorization' }).click();
  await expect(page.getByText('Connection could not be verified.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Continue securely' }).click();
  await expect(page.getByRole('dialog', { name: 'Test authorization' })).toBeVisible();
  expect(state.initiations).toBe(2);
  await page.getByRole('button', { name: 'Complete test authorization' }).click();
  await expect(page.getByRole('button', { name: 'Disconnect', exact: true })).toBeVisible();
});
