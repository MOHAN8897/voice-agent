import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.

const days = ['2026-10-25', '2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31'];

const analytics = {
  range: { key: '7d', since: days[0], until: days[6], days: 7, timezone: 'Asia/Kolkata', agentId: null },
  calls: {
    total: 42, connectRate: 61.9, avgDurationSec: 95, minutes: 41.2,
    outcomes: { answered: 26, no_answer: 8, busy: 3, declined: 1, unreachable: 2, failed: 1, voicemail: 1, in_progress: 0 },
    perDay: days.map((date, i) => ({ date, calls: i * 2, answered: i, minutes: i })),
  },
  leads: { total: 12, converted: 3, conversionRate: 25, byStage: { new: 5, qualified: 4, converted: 3 }, bySource: { inbound_call: 7, manual: 5 } },
  callbacks: { requested: 6, completed: 4, pending: 2, dismissed: 0, byStatus: {} },
  languageCallbacks: { requested: 3, completed: 1, pending: 2, dismissed: 0, byLanguage: [{ language: 'hi', requested: 2, completed: 1, pending: 1 }, { language: 'ta', requested: 1, completed: 0, pending: 1 }] },
  followups: { scheduled: 5, done: 7, failed: 2, cancelled: 1, total: 15, byKind: {} },
  dnc: { active: 9, added: 2, bySource: { live_call_opt_out: 2 }, perDay: days.map((date, i) => ({ date, added: i === 3 ? 2 : 0 })) },
  spend: { currency: 'INR', total: 1234.5, perDay: days.map((date, i) => ({ date, amount: i * 10 })), byAgent: [{ agentId: 'voice-setup-agent', name: 'Hima', amount: 1234.5 }] },
  topTags: [{ tag: 'intent:pricing', count: 9 }, { tag: 'custom:solar_panels', count: 4 }],
};

async function setup(page) {
  const seen = { analytics: [], counts: [], downloads: [] };
  await setupVoiceWorkspace(page);
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/app/analytics') {
      seen.analytics.push(Object.fromEntries(url.searchParams));
      return route.fulfill({ json: analytics });
    }
    if (path.startsWith('/api/app/exports/') && path.endsWith('/count')) {
      seen.counts.push({ path, query: Object.fromEntries(url.searchParams) });
      return route.fulfill({ json: { dataset: 'calls', count: url.searchParams.get('tags') ? 7 : 42, limit: 50000, capped: false } });
    }
    if (path.startsWith('/api/app/exports/')) {
      seen.downloads.push({ path, query: Object.fromEntries(url.searchParams) });
      const xlsx = url.searchParams.get('format') === 'xlsx';
      return route.fulfill({
        status: 200,
        headers: {
          'Content-Type': xlsx ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' : 'text/csv',
          'Content-Disposition': `attachment; filename="dialtact-calls-test.${xlsx ? 'xlsx' : 'csv'}"`,
        },
        body: 'Started (IST),Outcome\n2026-10-31 10:00,Answered\n',
      });
    }
    if (path === '/api/calls/tags') return route.fulfill({ json: { tags: [{ tag: 'intent:pricing', count: 9 }, { tag: 'custom:solar_panels', count: 4 }] } });
    if (path === '/api/calls') {
      return route.fulfill({ json: { calls: [{ call_id: 'c1', connected: true, agent_id: 'voice-setup-agent', direction: 'inbound', status: 'answered', started_at: '2026-10-31T07:40:02Z', ended_at: '2026-10-31T07:41:02Z', duration_sec: 60 }], total: 1 } });
    }
    return route.fallback();
  });
  return seen;
}

test('home links to analytics, which renders every section', async ({ page }) => {
  const seen = await setup(page);
  await page.goto('/#dashboard/overview');
  await page.getByTestId('home-analytics-link').click();
  await expect(page).toHaveURL(/#dashboard\/analytics/);

  const view = page.getByTestId('analytics-page');
  await expect(view.getByRole('heading', { name: 'Workspace analytics' })).toBeVisible();
  await expect(page.getByTestId('analytics-kpis')).toContainText('42');
  await expect(page.getByTestId('analytics-kpis')).toContainText('61.9%');
  await expect(page.getByTestId('analytics-kpis')).toContainText('₹1,234.50');
  await expect(page.getByTestId('analytics-outcomes')).toContainText('No answer');
  await expect(page.getByTestId('analytics-outcomes')).toContainText('Unreachable');
  await expect(page.getByTestId('analytics-lead-stages')).toContainText('Qualified');
  await expect(page.getByTestId('analytics-tags')).toContainText('Solar panels');
  await expect(page.getByTestId('analytics-followups')).toContainText('Failed');
  await expect(view).toContainText('Hindi');
  await expect(view).toContainText('9 numbers on the list');

  // The day chart has a table view with the same numbers.
  const perDay = page.getByTestId('analytics-calls-per-day');
  await perDay.getByRole('button', { name: 'Show table' }).click();
  await expect(perDay.getByRole('table')).toContainText('12');

  // Changing the period asks the server again for that period.
  await view.getByRole('tab', { name: '30 days' }).click();
  await expect.poll(() => seen.analytics.at(-1)?.range).toBe('30d');
  await view.getByRole('tab', { name: 'Custom' }).click();
  await page.getByTestId('analytics-since').fill('2026-10-01');
  await expect.poll(() => seen.analytics.at(-1)?.since).toBe('2026-10-01');
  expect(seen.analytics.at(-1).range).toBe('custom');
});

test('export dialog previews the row count and downloads with filters', async ({ page }) => {
  const seen = await setup(page);
  await page.goto('/#dashboard/analytics');
  await page.getByTestId('analytics-export').click();

  const dialog = page.getByTestId('export-dialog');
  await expect(dialog.getByTestId('export-count')).toContainText('42 rows match');
  await expect(dialog).toContainText('up to 50,000 rows');

  await dialog.getByLabel('Outcome').selectOption('busy');
  await dialog.getByRole('button', { name: 'Solar panels' }).click();
  await dialog.getByRole('button', { name: 'Pricing' }).click();
  await dialog.getByRole('tab', { name: 'All of these tags' }).click();
  await expect(dialog.getByTestId('export-count')).toContainText('7 rows match');
  await expect.poll(() => seen.counts.at(-1)?.query.tagMatch).toBe('all');

  const download = page.waitForEvent('download');
  await dialog.getByTestId('export-xlsx').click();
  expect((await download).suggestedFilename()).toBe('dialtact-calls-test.xlsx');
  const sent = seen.downloads.at(-1);
  expect(sent.path).toBe('/api/app/exports/calls');
  expect(sent.query).toMatchObject({ format: 'xlsx', outcome: 'busy', tagMatch: 'all', range: '7d' });
  expect(sent.query.tags.split(',').sort()).toEqual(['custom:solar_panels', 'intent:pricing']);

  // Switching dataset clears filters that do not apply to it.
  await dialog.getByTestId('export-dataset').selectOption('wallet');
  const csv = page.waitForEvent('download');
  await dialog.getByTestId('export-csv').click();
  await csv;
  expect(seen.downloads.at(-1).path).toBe('/api/app/exports/wallet');
  expect(seen.downloads.at(-1).query.outcome).toBeUndefined();
});

test('the calls page opens the export dialog pre-filtered', async ({ page }) => {
  const seen = await setup(page);
  await page.goto('/#dashboard/calls');
  await page.getByTestId('export-open-calls').click();
  await expect(page.getByTestId('export-dialog')).toBeVisible();
  await expect.poll(() => seen.counts.at(-1)?.path).toBe('/api/app/exports/calls/count');
});
