import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

const OBLIGATIONS = [
  { key: 'consent_disclosure', label: 'I have documented consent or another lawful basis for these calls and can produce it on request.' },
  { key: 'do_not_call_registry', label: "I check the recipient's DND/consent preferences through an authorised process before calling and honour opt-outs." },
  { key: 'identify_sender', label: 'My agent identifies my business and the purpose of the call, and discloses that it is an AI assistant.' },
  { key: 'recording_disclosure', label: 'My agent tells the caller when the call is recorded or transcribed and provides the privacy notice.' },
  { key: 'commercial_registration', label: 'My business uses an approved commercial calling route and completes sender/KYC registration.' },
  { key: 'data_retention', label: 'I limit caller data to its stated purpose and maintain retention, deletion and grievance-handling processes.' },
];

function compliancePayload() {
  return {
    country: 'IN',
    countryName: 'India',
    regulation: 'TRAI TCCCPR · DPDP Act 2023',
    summary: 'Commercial calls need a documented consent basis, sender identity, recipient-preference checks and a privacy notice.',
    obligations: OBLIGATIONS,
    acknowledged: Object.fromEntries(OBLIGATIONS.map(({ key }) => [key, false])),
    notes: ['The DPDP Rules, 2025 were notified on 13 November 2025.'],
    sources: [{ label: 'TRAI commercial calling regulations', url: 'https://trai.gov.in/example' }],
  };
}

test('tenant agent settings present only the India compliance checklist and save acknowledgements', async ({ page }) => {
  await setupVoiceWorkspace(page);
  const writes = [];
  await page.route('**/api/agents/*/compliance', async (route) => {
    if (route.request().method() === 'PUT') writes.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, json: compliancePayload() });
  });

  await page.goto('/#dashboard/employees?step=settings&agent=voice-setup-agent');

  await expect(page.getByRole('heading', { name: 'India calling compliance' })).toBeVisible();
  await expect(page.getByTestId('agent-compliance-regulation')).toHaveText('India · TRAI TCCCPR · DPDP Act 2023');
  await expect(page.getByText('Advisory checklist for commercial calls placed from India.', { exact: false })).toBeVisible();

  for (const { key, label } of OBLIGATIONS) {
    await expect(page.getByTestId(`agent-compliance-${key}`)).toBeVisible();
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.getByTestId(`agent-compliance-${key}`)).not.toBeChecked();
  }

  const panelText = await page.locator('#agent-panel-settings').innerText();
  expect(panelText).not.toMatch(/United States|FCC|TCPA|GDPR|CASL|Ofcom|Singapore|Australia/i);

  await page.getByTestId('agent-compliance-consent_disclosure').check();
  // The dev-only Reticle overlay sits over the sticky save bar; activate it by keyboard.
  await page.getByTestId('agent-settings-save').focus();
  await page.keyboard.press('Enter');

  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ acknowledged: { ...compliancePayload().acknowledged, consent_disclosure: true } });
  await expect(page.getByTestId('agent-settings-save')).toHaveText('Saved!');
});
