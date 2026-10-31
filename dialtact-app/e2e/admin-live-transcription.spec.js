import { test, expect } from '@playwright/test';

test('admin saves and reloads each selected live recognizer and reports save failure', async ({ page }) => {
  let stack = {
    pipeline: 'realtime_voice', language: 'te-IN', llm: { provider: 'gemini', model: 'gemini-3.8-live' },
    realtime_voice: { voice: 'Zephyr' },
    transcription: { live_enabled: true, post_call_enabled: false, live_model: 'gpt-4o-mini-transcribe' },
  };
  const saved = [];
  let rejectSave = false;
  const credentials = { openai: { configured: true }, sarvam: { configured: true }, gemini: { enabled: true, configured: true, ready: true } };
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let data = { ok: true, authenticated: true, subject: 'isolated-admin', csrf_token: 'isolated-csrf', providers: [], tiers: [] };
    if (path === '/api/dev/stack/saas-phone') {
      if (request.method() === 'PUT') {
        if (rejectSave) return route.fulfill({ status: 503, json: { ok: false } });
        stack = request.postDataJSON().stackOverride;
        saved.push(structuredClone(stack));
      }
      data = { ok: true, saved: { stack_override: stack }, resolved: stack, credentials, warnings: [], adjustments: [], voices: [] };
    } else if (path === '/api/dev/telephony/status') data = { active_provider: 'vobiz', active_ready: true, providers: [] };
    await route.fulfill({ json: data });
  });
  await page.goto(`${process.env.ADMIN_BASE_URL || 'http://127.0.0.1:3012'}/dev/saas-phone-stack`);
  const selector = page.getByRole('combobox', { name: 'Live transcription model' });
  await expect(selector).toBeVisible({ timeout: 45000 });
  for (const model of ['saaras:v3-realtime', 'gpt-transcribe']) {
    await selector.selectOption(model);
    await page.getByRole('button', { name: 'Save universal stack', exact: true }).click();
    await expect(page.getByText('Saved — applies to all subscriber PSTN and web practice calls.', { exact: true })).toBeVisible();
    expect(saved.at(-1).transcription).toMatchObject({ live_enabled: true, post_call_enabled: false, live_model: model });
    expect(saved.at(-1).llm).toMatchObject({ provider: 'gemini', model: 'gemini-3.8-live' });
    await page.reload();
    await expect(selector).toHaveValue(model);
  }
  await page.screenshot({ path: '../artifacts/admin-live-transcription.png', fullPage: true });
  rejectSave = true;
  await selector.selectOption('saaras:v3-realtime');
  await page.getByRole('button', { name: 'Save universal stack', exact: true }).click();
  await expect(page.getByText('Save failed (503)', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save universal stack', exact: true })).toBeEnabled();
  await page.reload();
  await expect(selector).toHaveValue('gpt-transcribe');
  expect(errors).toEqual([]);
  if (process.env.RETICLE_ADMIN_HOLD === '1') {
    test.setTimeout(180000);
    await page.waitForTimeout(90000);
  }
});
