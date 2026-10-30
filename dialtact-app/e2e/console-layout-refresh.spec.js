import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile } from 'node:fs/promises';

async function verifyCategory(page, name, testid, evidenceName) {
  if (!process.env.RETICLE_VERIFY) return;
  const commands = [{ tool: 'reticle_act_and_wait', args: {
    target: { role: 'button', name }, action: 'click',
    until: { kind: 'element', query: { testid }, state: 'visible' },
    intent: `The ${name} category exposes its editor directly while retaining other draft fields.`
  } }];
  const { stdout } = await promisify(execFile)('python', [
    '../artifacts/call-quality-review/callback-farewell-20261026/reticle_rpc.py',
    JSON.stringify(commands), page.url()
  ], { timeout: 55_000 });
  await writeFile(`../artifacts/console-reticle-${evidenceName}.jsonl`, stdout);
  const last = JSON.parse(stdout.trim().split('\n').at(-1));
  const result = JSON.parse(last.result.content.find(item => item.type === 'text').text);
  expect(result.verdict?.verified ?? result.verified, JSON.stringify(result)).toBe('yes');
}

test('sidebar collapses, keeps navigation usable and persists across reload', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setupVoiceWorkspace(page);
  const sidebar = page.getByTestId('console-sidebar');
  await expect(sidebar).toHaveAttribute('data-collapsed', 'true');
  await page.getByRole('button', { name: 'Expand sidebar', exact: true }).click();
  await expect(sidebar).toHaveAttribute('data-collapsed', 'false');
  const before = (await sidebar.boundingBox()).width;
  if (process.env.RETICLE_VERIFY) {
    const commands = [{ tool: 'reticle_act_and_wait', args: {
      target: { testid: 'sidebar-collapse-toggle' }, action: 'click',
      until: { kind: 'element', query: { role: 'button', name: 'Expand sidebar' }, state: 'visible' },
      intent: 'Collapsing navigation frees workspace width while preserving accessible navigation.'
    } }];
    const { stdout } = await promisify(execFile)('python', [
      '../artifacts/call-quality-review/callback-farewell-20261026/reticle_rpc.py',
      JSON.stringify(commands), page.url()
    ], { timeout: 55_000 });
    await writeFile('../artifacts/console-layout-reticle.jsonl', stdout);
    const last = JSON.parse(stdout.trim().split('\n').at(-1));
    const result = JSON.parse(last.result.content.find(item => item.type === 'text').text);
    expect(result.verdict?.verified ?? result.verified, JSON.stringify(result)).toBe('yes');
  } else {
    await page.getByTestId('sidebar-collapse-toggle').click();
  }
  await expect(sidebar).toHaveAttribute('data-collapsed', 'true');
  expect((await sidebar.boundingBox()).width).toBeLessThan(before);
  await expect(page.getByTestId('nav-employees')).toHaveAccessibleName('AI employees');
  await expect(page.getByTestId('nav-employees').locator('svg')).toBeVisible();
  await expect(page.getByTestId('sidebar-collapse-toggle')).toHaveAttribute('title', 'Expand sidebar');
  await expect(page.getByTestId('sidebar-collapse-toggle').getByText('Expand', { exact: true })).toBeVisible();
  await page.reload();
  await expect(sidebar).toHaveAttribute('data-collapsed', 'true');
  await page.screenshot({ path: '../artifacts/console-collapsed-desktop.png' });
});

test('script stays on one page and settings categories preserve edits on desktop and mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await setupVoiceWorkspace(page);
  await page.getByTestId('agent-tab-script').click();
  await expect(page.getByRole('navigation', { name: 'Script sections' })).toHaveCount(0);
  await expect(page.getByTestId('script-textarea')).toBeVisible();
  await expect(page.getByTestId('agent-studio-greeting')).toBeVisible();
  await expect(page.getByTestId('agent-studio-farewell')).toBeVisible();
  await expect(page.getByTestId('add-objection-btn')).toBeVisible();
  await page.getByTestId('agent-studio-farewell').fill('Thank you for your time. Goodbye.');
  await expect(page.getByTestId('agent-studio-farewell')).toHaveValue('Thank you for your time. Goodbye.');
  const script = await page.getByTestId('script-textarea').boundingBox();
  const farewell = await page.getByTestId('agent-studio-farewell').boundingBox();
  expect(farewell.x).toBeGreaterThan(script.x + script.width);
  const greeting = await page.getByTestId('agent-studio-greeting').boundingBox();
  expect(greeting.x).toBeGreaterThan(script.x + script.width);
  expect(Math.abs(script.width / (greeting.x + greeting.width - script.x) - 0.5)).toBeLessThan(0.08);
  await page.screenshot({ path: '../artifacts/console-script-desktop.png' });
  await page.getByTestId('agent-studio-discard').click();
  await page.getByTestId('agent-tab-settings').click();
  const nav = page.getByRole('navigation', { name: 'Settings sections' });
  await expect(nav.locator('button svg')).toHaveCount(5);
  expect(await nav.evaluate(element => getComputedStyle(element).display)).toBe('grid');
  await nav.scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../artifacts/console-settings-desktop.png' });
  await nav.getByRole('button', { name: 'Agent & phone', exact: true }).click();
  await page.getByTestId('agent-settings-name').fill('Preserved draft name');
  await verifyCategory(page, 'Recording & compliance', 'agent-recording-disclosure-toggle', 'settings');
  await nav.getByRole('button', { name: 'Recording & compliance', exact: true }).click();
  await expect(page.getByTestId('agent-settings-name')).not.toBeVisible();
  await expect(page.getByTestId('agent-recording-disclosure-toggle')).toBeVisible();
  await nav.getByRole('button', { name: 'Agent & phone', exact: true }).click();
  await expect(page.getByTestId('agent-settings-name')).toHaveValue('Preserved draft name');
  expect(await page.getByTestId('agent-studio-unsaved').evaluate(el => getComputedStyle(el).position)).toBe('fixed');
  await page.setViewportSize({ width: 390, height: 844 });
  await nav.getByRole('button', { name: 'All settings', exact: true }).click();
  const dock = await page.getByTestId('agent-studio-unsaved').boundingBox();
  expect(dock.y + dock.height).toBeLessThanOrEqual(844);
  expect(dock.x).toBeGreaterThanOrEqual(0);
  expect(dock.x + dock.width).toBeLessThanOrEqual(390);
  await page.locator('main').evaluate(element => { element.scrollTop = element.scrollHeight; });
  const lastSettingsCard = await page.locator('.settings-secondary > [data-section="compliance"]').last().boundingBox();
  const bottomDock = await page.getByTestId('agent-studio-unsaved').boundingBox();
  expect(lastSettingsCard.y + lastSettingsCard.height).toBeLessThanOrEqual(bottomDock.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page.getByTestId('sidebar-collapse-toggle')).not.toBeVisible();
  await page.screenshot({ path: '../artifacts/console-settings-mobile.png' });
});

test('backend profile changes refresh on focus without rewriting a script draft', async ({ page }) => {
  const state = await setupVoiceWorkspace(page);
  await expect(page.getByTestId('voice-stack-tier-medium')).toBeVisible();
  state.profiles[1].profileRevision += 1;
  state.profiles[1].engines[0].models[0].voices[0].label = 'Updated approved voice';
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByTestId('voice-select-btn-voice-medium')).toBeVisible();
  await expect(page.getByTestId('voice-stack-selector')).toContainText('Updated approved voice');
  // A profile revision bump keeps a saved voice that still exists valid (the backend accepts it).
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
  await page.getByTestId('voice-select-btn-voice-medium').click();
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
  expect(state.writes[0].voiceSettings.profileRevision).toBe(state.profiles[1].profileRevision);
  await page.getByTestId('agent-tab-script').click();
  const field = page.getByTestId('script-textarea');
  await field.fill('Keep this unsaved business script.');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(field).toHaveValue('Keep this unsaved business script.');
  await expect(page.getByTestId('agent-studio-unsaved')).toBeVisible();
});

test('catalog failure keeps current choices visible and supports retry', async ({ page }) => {
  await setupVoiceWorkspace(page);
  await expect(page.getByTestId('voice-stack-tier-medium')).toBeVisible();
  await page.route('**/api/voice-stacks/catalog?*', route => route.fulfill({ status: 503, json: { detail: 'Temporary failure' } }));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByTestId('voice-stack-catalog-retry')).toBeVisible();
  await expect(page.getByTestId('voice-stack-tier-medium')).toBeVisible();
  await page.unroute('**/api/voice-stacks/catalog?*');
  await page.getByTestId('voice-stack-catalog-retry').click();
  await expect(page.getByTestId('voice-stack-catalog-retry')).toHaveCount(0);
});

test('enabled but unverified economical tier remains visible and cannot be selected', async ({ page }) => {
  const state = await setupVoiceWorkspace(page);
  await expect(page.getByTestId('voice-stack-tier-low')).toBeVisible();
  state.profiles[0].ready = false;
  state.profiles[0].enabled = true;
  state.profiles[0].engines = [];
  state.profiles[0].blockers = [{ code: 'stt_unverified', message: 'Voice setup needs verification.' }];
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByTestId('voice-stack-tier-low')).toBeVisible();
  await expect(page.getByTestId('voice-stack-tier-low')).toBeDisabled();
  await expect(page.getByTestId('voice-stack-tier-medium')).toBeEnabled();
});

test('a stalled request times out without clearing the workspace session', async ({ page }) => {
  await setupVoiceWorkspace(page);
  await page.route('**/api/timeout-proof', async route => {
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({ json: { ok: true } }).catch(() => {});
  });
  const result = await page.evaluate(async () => {
    const { api } = await import('/src/services/api.js');
    try {
      await api.request('GET', '/api/timeout-proof', null, {}, { timeoutMs: 30 });
      return { rejected: false };
    } catch (error) {
      return { rejected: true, degraded: error.isServerDegraded,
        hasSession: Boolean(sessionStorage.getItem('dialtact_auth_token')) };
    }
  });
  expect(result).toEqual({ rejected: true, degraded: true, hasSession: true });
  await expect(page.getByTestId('agent-tab-voice')).toBeVisible();
});
