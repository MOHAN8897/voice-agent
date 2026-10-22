import { chromium } from '../../../voxly-ai/node_modules/@playwright/test/index.mjs';
import { setupCampaign } from '../../../voxly-ai/e2e/fixtures/campaign.js';
import path from 'node:path';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
await setupCampaign(page, { variableReport: { previews: [{
  contactIndex: 0, name: 'Example Contact', values: { 'contact.full_name': 'Example Contact' },
  missingVariables: [], renderedText: 'Hello Example Contact. Is this a convenient time to speak?',
}] } });
await page.route('**/api/telephony/countries', route => route.fulfill({ json: { countries: [{ code: 'US', name: 'United States', dial: '+1' }], default: 'US' } }));
await page.route('**/api/telephony/numbers/search?*', route => route.fulfill({ json: { numbers: [{ e164: '+12025550101', country: 'US', monthlyUsd: 4 }] } }));
await page.route('**/api/billing/catalog', route => route.fulfill({ json: { rates: { numberMonthlyUsd: 4 } } }));
await page.route('**/api/kyc/voice/status*', route => route.fulfill({ json: { required: true, configured: true, approved: false, status: 'not_started', callsBlocked: true } }));
await page.route('**/api/kyc/voice/session', route => route.fulfill({ status: 503, json: { detail: { error: { code: 'voice_kyc_session_failed', message: 'Could not start verification. Please try again.' } } } }));
console.log('Isolated campaign and number onboarding browser ready for Reticle. All API requests use test doubles.');
process.stdin.setEncoding('utf8');
for await (const input of process.stdin) {
  const command = input.trim();
  if (command === 'exit') break;
  if (command === 'mobile') await page.setViewportSize({ width: 390, height: 844 });
  if (command === 'desktop') await page.setViewportSize({ width: 1440, height: 1000 });
  if (['capture', 'mobile', 'desktop'].includes(command)) {
    const target = path.resolve('.gravitas/sessions/campaign-kyc-alignment', `verified-${page.viewportSize().width}.png`);
    await page.screenshot({ path: target, fullPage: true });
    console.log(target);
  }
}
await browser.close();
