import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionPath = path.resolve(__dirname, '../../data/e2e_session.json');

test.describe('Integrations & Voice Tools Marketplace', () => {
  test('renders 170+ integrations catalog, search, and category filters with zero vendor leak', async ({ page }) => {
    test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');

    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
    const u = sess.user;
    const sessionUser = {
      id: u.userId,
      name: u.fullName || u.email,
      email: u.email,
      tenantId: sess.tenant?.tenantId,
      hasCompletedOnboarding: true,
    };

    await page.addInitScript(
      ({ token, sessionUser }) => {
        sessionStorage.setItem('voxly_auth_token', token);
        localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
      },
      { token: sess.token, sessionUser }
    );

    await page.goto('/#dashboard/integrations');

    await expect(page.getByRole('heading', { name: /integrations/i }).first()).toBeVisible({
      timeout: 20000,
    });

    // 1. Verify tenant UI does not leak backend vendor names (no "Composio")
    const bodyText = await page.textContent('body');
    expect(bodyText).not.toContain('Composio');

    // 2. Verify catalog apps are visible
    await expect(page.getByText('Google Calendar')).toBeVisible();
    await expect(page.getByText('HubSpot CRM')).toBeVisible();
    await expect(page.getByText('Slack Alerts')).toBeVisible();
    await expect(page.getByText('Gmail Follow-Up')).toBeVisible();

    // 3. Test dynamic search filtering
    const searchInput = page.getByTestId('integration-search-input');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('shopify');
    await expect(page.getByText('Shopify')).toBeVisible();
    await expect(page.getByText('Google Calendar')).not.toBeVisible();

    // Clear search
    await searchInput.fill('');
    await expect(page.getByText('Google Calendar')).toBeVisible();

    // 4. Test category filter pills
    const financePill = page.getByTestId('category-pill-finance');
    await expect(financePill).toBeVisible();
    await financePill.click();
    await expect(page.getByText('Stripe')).toBeVisible();
    await expect(page.getByText('HubSpot CRM')).not.toBeVisible();

    // Reset to All
    const allPill = page.getByTestId('category-pill-all');
    await allPill.click();
    await expect(page.getByText('Google Calendar')).toBeVisible();

    // 5. Test Actions modal
    const actionsBtn = page.getByRole('button', { name: /\d+ actions/i }).first();
    await actionsBtn.click();
    await expect(page.getByTestId('action-modal-close-btn')).toBeVisible();
    await page.getByTestId('action-modal-close-btn').click();

    // 6. Test Section Tabs: All, Connected, Not Connected
    const tabConnected = page.getByTestId('tab-connected');
    await expect(tabConnected).toBeVisible();
    await tabConnected.click();

    const tabNotConnected = page.getByTestId('tab-not-connected');
    await expect(tabNotConnected).toBeVisible();
    await tabNotConnected.click();
    await expect(page.getByText('Available Integrations Ready to Connect')).toBeVisible();

    const tabAll = page.getByTestId('tab-all-integrations');
    await expect(tabAll).toBeVisible();
    await tabAll.click();

    // 7. Test Request App dialog
    const requestBtn = page.getByTestId('request-app-btn');
    await requestBtn.click();
    await expect(page.getByRole('heading', { name: /request custom integration/i })).toBeVisible();
    await page.getByPlaceholder(/netsuite, workday/i).fill('NetSuite');
    await page.getByRole('button', { name: /submit request/i }).click();
  });

  test('backend integrations API responds correctly with bearer token', async () => {
    test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');
    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));

    const res = await fetch('http://127.0.0.1:8000/api/integrations', {
      headers: {
        Authorization: `Bearer ${sess.token}`,
      },
    });

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('items');
    expect(Array.isArray(body.items)).toBeTruthy();

    // Test catalog endpoint
    const catRes = await fetch('http://127.0.0.1:8000/api/integrations/catalog');
    expect(catRes.status).toBe(200);
    const catBody = await catRes.json();
    expect(catBody).toHaveProperty('items');
    expect(catBody.items.length).toBeGreaterThanOrEqual(150);
  });

  test('interactive connect modal explains OAuth vs sandbox flow and guide tab renders cleanly', async ({ page }) => {

    test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');

    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
    const u = sess.user;
    const sessionUser = {
      id: u.userId,
      name: u.fullName || u.email,
      email: u.email,
      tenantId: sess.tenant?.tenantId,
      hasCompletedOnboarding: true,
    };

    await page.addInitScript(
      ({ token, sessionUser }) => {
        sessionStorage.setItem('voxly_auth_token', token);
        localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
      },
      { token: sess.token, sessionUser }
    );

    await page.goto('/#dashboard/integrations');
    await expect(page.getByRole('heading', { name: /integrations/i }).first()).toBeVisible({ timeout: 20000 });

    // 1. Click "How Connections Work" tab
    const guideTab = page.getByRole('button', { name: /how connections work/i });
    await expect(guideTab).toBeVisible();
    await guideTab.click();
    await expect(page.getByRole('heading', { name: /how app connections & tenant sign-in work/i })).toBeVisible();
    await expect(page.getByText(/personal \/ workspace sign-in/i)).toBeVisible();
    await expect(page.getByText(/encrypted tenant vault/i)).toBeVisible();
    await expect(page.getByText(/sub-second in-call dispatch/i)).toBeVisible();

    // 2. Return to All Integrations tab
    const allTab = page.getByRole('button', { name: /all integrations/i });
    await allTab.click();
    await expect(page.getByText('Google Calendar')).toBeVisible();

    // 3. Open Connect Modal on Google Calendar
    const connectBtn = page.getByTestId('connect-btn-googlecalendar');
    await expect(connectBtn).toBeVisible();
    await connectBtn.click();

    // Verify Connect modal displays OAuth Sign-In and clear security explanation
    await expect(page.getByRole('heading', { name: /connect google calendar/i })).toBeVisible();
    await expect(page.getByText(/oauth 2\.0 sign-in/i)).toBeVisible();
    await expect(page.getByText(/how this connection works/i)).toBeVisible();
    await expect(page.getByText(/account label \/ alias/i)).toBeVisible();
    await expect(page.getByTestId('confirm-connect-btn')).toBeVisible();

    // Close modal
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: /connect google calendar/i })).not.toBeVisible();
  });

  test('initiates integration connection and verifies Nango redirect session token', async () => {
    test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');
    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));

    // 1. Call connect endpoint
    const connectRes = await fetch('http://127.0.0.1:8000/api/integrations/github/connect', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${sess.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        base_redirect_uri: 'http://127.0.0.1:8000/api/integrations/callback',
      }),
    });

    expect(connectRes.status).toBe(200);
    const connectData = await connectRes.json();
    expect(connectData).toHaveProperty('redirect_url');
    expect(connectData).toHaveProperty('state');
    expect(connectData.status).toBe('INITIATED');

    // 2. Simulate callback authorization
    const callbackRes = await fetch(
      `http://127.0.0.1:8000/api/integrations/callback?state=${connectData.state}&app_name=GITHUB&code=test_ok`
    );
    expect(callbackRes.status).toBe(200);

    // 3. Verify it appears in active integrations
    const listRes = await fetch('http://127.0.0.1:8000/api/integrations', {
      headers: {
        'Authorization': `Bearer ${sess.token}`,
      },
    });
    expect(listRes.status).toBe(200);
    const listData = await listRes.json();
    expect(listData.items.some(item => item.app_name.toUpperCase() === 'GITHUB')).toBeTruthy();
  });

  test('activates integration directly via Nango connect callback endpoint and verifies disconnect', async () => {
    test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');
    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));

    // 1. Direct activation (as emitted by Nango Connect UI modal)
    const actRes = await fetch('http://127.0.0.1:8000/api/integrations/SLACK/activate', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${sess.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        connection_id: 'nango_slack_test_conn',
        account_identifier: 'workspace-slack-team',
      }),
    });
    expect(actRes.status).toBe(200);
    const actData = await actRes.json();
    expect(actData.status).toBe('ACTIVE');
    expect(actData.app_name).toBe('SLACK');

    // 2. Verify in list
    const listRes = await fetch('http://127.0.0.1:8000/api/integrations', {
      headers: {
        'Authorization': `Bearer ${sess.token}`,
      },
    });
    expect(listRes.status).toBe(200);
    const listData = await listRes.json();
    expect(listData.items.some(item => item.app_name.toUpperCase() === 'SLACK')).toBeTruthy();

    // 3. Disconnect
    const delRes = await fetch('http://127.0.0.1:8000/api/integrations/SLACK', {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${sess.token}`,
      },
    });
    expect(delRes.status).toBe(200);

    // 4. Verify disconnected
    const listAfterRes = await fetch('http://127.0.0.1:8000/api/integrations', {
      headers: {
        'Authorization': `Bearer ${sess.token}`,
      },
    });
    const listAfterData = await listAfterRes.json();
    expect(listAfterData.items.some(item => item.app_name.toUpperCase() === 'SLACK')).toBeFalsy();
  });
});


