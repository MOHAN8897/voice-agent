import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.

const AGENT = 'voice-setup-agent';
const OTHER = 'second-agent';

async function setup(page, { step = 'overview' } = {}) {
  const base = await setupVoiceWorkspace(page);
  const other = { ...base.agent, id: OTHER, agent_id: OTHER, name: 'Meera' };
  const state = { leadQueries: [], callQueries: [] };
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/agents') return route.fulfill({ json: { agents: [base.agent, other] } });
    if (path === `/api/agents/${OTHER}`) return route.fulfill({ json: { agent: other } });
    if (path === '/api/calls/stats') {
      return route.fulfill({ json: {
        total: 5, connected: 3, missed: 2, avgDurationSec: 90, completedConnected: 3,
        leadCount: 3, convertedLeads: 0, conversionRate: 0, leadStageCounts: { contacted: 1, qualified: 2 },
        cost: { settledSpend: 42, currency: 'INR', complete: true, costPerLead: 14 },
      } });
    }
    if (path === '/api/calls') {
      state.callQueries.push(Object.fromEntries(url.searchParams));
      return route.fulfill({ json: { calls: [], total: 0, limit: 100, offset: 0 } });
    }
    if (path === '/api/calls/tags') return route.fulfill({ json: { tags: [] } });
    if (path === '/api/leads') {
      state.leadQueries.push(Object.fromEntries(url.searchParams));
      return route.fulfill({ json: { leads: [], total: 0 } });
    }
    return route.fallback();
  });
  await page.goto(`/#dashboard/employees?step=${step}&agent=${AGENT}`);
  await expect(page.getByTestId('agent-studio-switcher')).toHaveValue(AGENT);
  return state;
}

// Flags any moment the workspace left the page (the fleet list replaced it).
async function watchForListFlash(page) {
  await page.evaluate(() => {
    window.__leftWorkspace = false;
    new MutationObserver(() => {
      if (!document.querySelector('[data-testid="agent-studio-switcher"]')) window.__leftWorkspace = true;
    }).observe(document.body, { childList: true, subtree: true });
  });
}

test.describe('agent switcher', () => {
  for (const tab of ['overview', 'script', 'calls', 'voice', 'settings']) {
    test(`switching agent keeps the ${tab} tab open`, async ({ page }) => {
      await setup(page, { step: tab });
      await expect(page.getByTestId(`agent-tab-${tab}`)).toHaveAttribute('aria-selected', 'true');
      await watchForListFlash(page);

      await page.getByTestId('agent-studio-switcher').selectOption(OTHER);

      await expect(page).toHaveURL(new RegExp(`#dashboard/employees\\?step=${tab}&agent=${OTHER}$`));
      await expect(page.getByTestId('agent-studio-switcher')).toHaveValue(OTHER);
      await expect(page.getByTestId(`agent-tab-${tab}`)).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByRole('heading', { name: /AI employees \(/ })).toHaveCount(0);
      expect(await page.evaluate(() => window.__leftWorkspace)).toBe(false);

      // Back goes to the previous agent, still on the same tab.
      await page.goBack();
      await expect(page.getByTestId('agent-studio-switcher')).toHaveValue(AGENT);
      await expect(page.getByTestId(`agent-tab-${tab}`)).toHaveAttribute('aria-selected', 'true');
    });
  }
});

test.describe('agent overview links', () => {
  test('a lead stage chip opens this agent’s leads at that stage', async ({ page }) => {
    const state = await setup(page);
    const chip = page.getByTestId('agent-overview-stage-qualified');
    await expect(chip).toHaveText(/Qualified · 2/);
    await expect(chip).toHaveAccessibleName(/Show 2 Qualified leads from Hima/);
    await chip.focus();
    await page.keyboard.press('Enter');

    await expect(page.getByTestId('agent-tab-calls')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('agent-calls-panel-tab-leads')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByLabel('Stage')).toHaveValue('Qualified');
    await expect(page.getByLabel('Last updated')).toHaveValue('7');
    await expect.poll(() => state.leadQueries.at(-1)).toMatchObject({ agentId: AGENT, stage: 'qualified' });
    expect(state.leadQueries.at(-1).updatedSince).toBeTruthy();
  });

  test('KPI cards open the matching filtered lists', async ({ page }) => {
    const state = await setup(page);

    // Missed → this agent's history, filtered to missed calls.
    await page.getByTestId('agent-kpi-missed').getByRole('button').click();
    await expect(page.getByTestId('agent-calls-panel-tab-history')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByTestId('calls-status-filter')).toHaveValue('missed');
    await expect.poll(() => state.callQueries.at(-1)).toMatchObject({ agentId: AGENT, status: 'missed' });

    // A plain tab click afterwards does not keep the one-shot filter.
    await page.getByTestId('agent-tab-overview').click();
    await page.getByTestId('agent-kpi-calls').getByRole('button').click();
    await expect(page.getByTestId('calls-status-filter')).toHaveValue('all');

    // New leads → this agent's leads in the selected period.
    await page.getByTestId('agent-tab-overview').click();
    await page.getByTestId('agent-overview-range-30days').click();
    await page.getByTestId('agent-kpi-leads').getByRole('button').click();
    await expect(page.getByTestId('agent-calls-panel-tab-leads')).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByLabel('Stage')).toHaveValue('');
    await expect(page.getByLabel('Last updated')).toHaveValue('30');

    // Spent on calls → this agent's call history (where each call's charge is shown).
    await page.getByTestId('agent-tab-overview').click();
    const spend = page.getByTestId('agent-kpi-spend').getByRole('button');
    await spend.focus();
    await expect(spend).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('agent-calls-panel-tab-history')).toHaveAttribute('aria-selected', 'true');
  });
});
