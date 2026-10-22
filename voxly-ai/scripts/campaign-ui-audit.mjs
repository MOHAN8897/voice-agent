// Local UI verification with synthetic data. All API requests are intercepted.
import { chromium } from '@playwright/test';
import { setupCampaign } from '../e2e/fixtures/campaign.js';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, baseURL: 'http://127.0.0.1:5173' });
const dashboard = process.argv.includes('--dashboard');
await setupCampaign(page, dashboard ? {
  initialCampaigns: Array.from({ length: 9 }, (_, n) => ({ id: `audit-${n}`, name: `Batch ${n}`, status: 'running', agentId: 'campaign-agent' })),
  analyticsStatus: 'completed', analyticsDelay: 60,
} : {});
if (dashboard) {
  await page.getByText('completed', { exact: true }).first().waitFor();
} else {
  await page.getByRole('button', { name: 'New campaign', exact: true }).click();
  await page.getByLabel('Campaign name', { exact: true }).fill('Isolated UI audit');
  await page.getByRole('button', { name: 'Paste CSV', exact: true }).click();
  await page.getByLabel('CSV contacts', { exact: true }).fill('phone,full_name\n+12025550101,Example Contact');
}
console.log('ISOLATED_CAMPAIGN_READY: API requests use synthetic fixtures; no calls can be placed.');
const timer = setTimeout(async () => { await browser.close(); process.exit(0); }, 3 * 60 * 1000);
process.on('SIGINT', async () => { clearTimeout(timer); await browser.close(); process.exit(0); });
