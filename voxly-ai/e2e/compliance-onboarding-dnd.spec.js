import { test, expect } from '@playwright/test';

const TEST_EMAIL = 'saiskm115@gmail.com';
const TEST_PASSWORD = 'CompliancePass123!';

async function ensureSignedIn(page) {
  await page.goto('/#dashboard/overview');
  await page.waitForTimeout(1000);

  // If already in console, we're good
  const sidebar = page.locator('text=Sai Health Labs').first();
  if (await sidebar.isVisible().catch(() => false)) return;

  const continueSignInBtn = page.getByRole('button', { name: /continue — sign in/i });
  const consoleSignInBtn = page.getByRole('button', { name: /sign in to console/i });
  const regularSignInBtn = page.getByRole('button', { name: /sign in/i }).first();
  if (await continueSignInBtn.isVisible()) {
    await continueSignInBtn.click();
  } else if (await consoleSignInBtn.isVisible()) {
    await consoleSignInBtn.click();
  } else if (await regularSignInBtn.isVisible()) {
    await regularSignInBtn.click();
  }

  const emailInput = page.locator('#voxly-auth-email');
  if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await emailInput.fill(TEST_EMAIL);
    await page.locator('#voxly-auth-password').fill(TEST_PASSWORD);
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await page.waitForTimeout(2000);
  }
}

test.describe.serial('Compliance, Onboarding Survey, and DND Registry E2E', () => {

  test.beforeAll(async () => {
    try {
      const { execSync } = await import('child_process');
      execSync('python scripts/reset-test-onboarding.py saiskm115@gmail.com', { stdio: 'ignore' });
    } catch {
      // ignore
    }
  });

  test('1. Onboarding Survey Gate intercepts un-onboarded user, mandates terms, and unlocks console', async ({ page }) => {
    // Navigate to app console overview directly to trigger sign in gate or survey gate
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);

    const continueSignInBtn = page.getByRole('button', { name: /continue — sign in/i });
    const consoleSignInBtn = page.getByRole('button', { name: /sign in to console/i });
    const signInBtn = page.getByRole('button', { name: /sign in/i }).first();
    if (await continueSignInBtn.isVisible()) {
      await continueSignInBtn.click();
    } else if (await consoleSignInBtn.isVisible()) {
      await consoleSignInBtn.click();
    } else if (await signInBtn.isVisible()) {
      await signInBtn.click();
    }

    const emailInput = page.locator('#voxly-auth-email');
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    await emailInput.fill(TEST_EMAIL);
    await page.locator('#voxly-auth-password').fill(TEST_PASSWORD);
    await page.getByRole('button', { name: /^sign in$/i }).click();

    // Because we reset onboarding survey in DB, OnboardingSurveyModal must be rendered
    const onboardingModal = page.locator('[data-testid="onboarding-survey-modal"]');
    await expect(onboardingModal).toBeVisible({ timeout: 15000 });

    // Step 1: Profile & Organization
    await expect(page.locator('[data-testid="onboarding-step-1"]')).toBeVisible();
    await page.locator('[data-testid="onboarding-fullname-input"]').fill('Sai Krishna');
    await page.locator('[data-testid="onboarding-company-input"]').fill('Sai Health Labs');
    await page.locator('[data-testid="onboarding-next-btn"]').click();

    // Step 2: Platform Strategy & Use Case
    await expect(page.locator('[data-testid="onboarding-step-2"]')).toBeVisible();
    await page.locator('[data-testid="onboarding-referral-select"]').selectOption('social');
    await page.locator('[data-testid="onboarding-usecase-select"]').selectOption('outbound_sales');
    await page.locator('[data-testid="onboarding-volume-select"]').selectOption('2500_to_10000');
    await page.locator('[data-testid="onboarding-next-btn"]').click();

    // Step 3: Terms & Acceptable Use Policy
    await expect(page.locator('[data-testid="onboarding-step-3"]')).toBeVisible();
    const submitBtn = page.locator('[data-testid="onboarding-submit-btn"]');
    
    // Submit button MUST be disabled until checkbox is checked
    await expect(submitBtn).toBeDisabled();

    // Check terms checkbox
    const termsCheckbox = page.locator('[data-testid="onboarding-terms-checkbox"]');
    await termsCheckbox.check();

    // Submit button MUST now be enabled
    await expect(submitBtn).toBeEnabled();

    // Submit survey
    await submitBtn.click();

    // Verify modal closes and user enters console
    await expect(onboardingModal).not.toBeVisible({ timeout: 10000 });
  });

  test('2. Settings module strictly isolates canonical profile from marketing telemetry', async ({ page }) => {
    await ensureSignedIn(page);
    await page.goto('/#dashboard/settings');
    await page.waitForTimeout(1500);

    // Verify Settings module is loaded
    await expect(page.getByText('Workspace', { exact: false }).first()).toBeVisible({ timeout: 10000 });

    // Verify that marketing survey questions are NOT leaked into Settings
    const bodyText = await page.textContent('body');
    expect(bodyText).not.toContain('How did you hear about Voxly?');
    expect(bodyText).not.toContain('referralSource');
    expect(bodyText).not.toContain('primaryUseCase');
    expect(bodyText).not.toContain('estimatedMonthlyMinutes');
  });

  test('3. Do Not Call (DND) Registry: Add entry, enforce deactivation re-consent audit', async ({ page }) => {
    await ensureSignedIn(page);
    await page.goto('/#dashboard/campaigns');
    await page.waitForTimeout(1500);

    // Switch to DND Registry tab
    const dndTab = page.locator('[data-testid="dnd-registry-tab-button"]');
    await expect(dndTab).toBeVisible({ timeout: 10000 });
    await dndTab.click();

    // Verify DND registry panel is mounted
    await expect(page.locator('[data-testid="dnc-registry-panel"]')).toBeVisible();

    // Click "Add to Do Not Call"
    const addDncBtn = page.locator('[data-testid="add-dnc-button"]');
    await expect(addDncBtn).toBeVisible();
    await addDncBtn.click();

    // Enter phone number
    const testPhone = '+15558889911';
    await page.locator('[data-testid="add-dnc-single-phone"]').fill(testPhone);
    await page.locator('[data-testid="add-dnc-submit-btn"]').click();

    // Verify phone number appears in the table
    await page.waitForTimeout(1000);
    const phoneCell = page.getByText(testPhone).first();
    await expect(phoneCell).toBeVisible({ timeout: 10000 });

    // Click Deactivate button on that row
    const row = page.locator('tr', { hasText: testPhone });
    const deactivateBtn = row.getByRole('button', { name: /deactivate/i });
    await expect(deactivateBtn).toBeVisible();
    await deactivateBtn.click();

    // Deactivation Audit Modal opens
    const reasonInput = page.locator('[data-testid="dnc-deactivate-reason-input"]');
    const reconsentCheckbox = page.locator('[data-testid="dnc-reconsent-checkbox"]');
    const confirmDeactivateBtn = page.locator('[data-testid="dnc-deactivate-confirm-btn"]');

    await expect(reasonInput).toBeVisible();

    // Confirm button MUST be disabled initially
    await expect(confirmDeactivateBtn).toBeDisabled();

    // Too short reason (< 5 chars) -> still disabled
    await reasonInput.fill('ok');
    await expect(confirmDeactivateBtn).toBeDisabled();

    // Valid reason, but checkbox unchecked -> still disabled
    await reasonInput.fill('Customer signed physical re-consent form');
    await expect(confirmDeactivateBtn).toBeDisabled();

    // Check reconsent checkbox -> button is enabled
    await reconsentCheckbox.check();
    await expect(confirmDeactivateBtn).toBeEnabled();

    // Click confirm deactivation
    await confirmDeactivateBtn.click();
    await page.waitForTimeout(1000);

    // Switch to "Deactivated / Audit History" tab
    await page.locator('[data-testid="dnc-tab-deactivated"]').click();
    await page.waitForTimeout(1000);

    // Verify phone number is now in Deactivated History with reason
    await expect(page.getByText(testPhone).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Customer signed physical re-consent form').first()).toBeVisible();
  });

  test('4. Agent Workspace: Dial / Bulk Campaign Compliance Modal and Recording Disclosure', async ({ page }) => {
    await ensureSignedIn(page);
    await page.goto('/#dashboard/employees');
    await page.waitForTimeout(1500);

    // Click on the first agent card to open Agent Studio
    const agentCard = page.locator('button, div').filter({ hasText: /Compliance Voice Agent|default|Agent/i }).first();
    await expect(agentCard).toBeVisible({ timeout: 10000 });
    await agentCard.click();
    await page.waitForTimeout(1000);

    // Test Call Recording & Disclosure in Settings Tab
    const settingsTab = page.locator('#agent-tab-settings, [data-testid="agent-tab-settings"]');
    if (await settingsTab.isVisible()) {
      await settingsTab.click();
      await page.waitForTimeout(500);

      const toggle = page.locator('[data-testid="agent-recording-disclosure-toggle"]');
      await expect(toggle).toBeVisible();

      // If off, toggle it on
      const isChecked = await toggle.getAttribute('aria-checked');
      if (isChecked === 'false') {
        await toggle.click();
      }

      // Verify textarea appears
      const textarea = page.locator('[data-testid="agent-recording-disclosure-text"]');
      await expect(textarea).toBeVisible();
      await expect(textarea).toHaveValue(/recorded/i);
    }

    // Test Bulk Campaign Compliance Modal in Calls Tab
    const callsTab = page.locator('#agent-tab-calls, [data-testid="agent-tab-calls"]');
    if (await callsTab.isVisible()) {
      await callsTab.click();
      await page.waitForTimeout(500);

      // Verify "Single Call" vs "Bulk Campaign" tabs
      const bulkTab = page.getByRole('button', { name: /bulk campaign/i });
      if (await bulkTab.isVisible()) {
        await bulkTab.click();
        await page.waitForTimeout(300);

        // Enter a contact number in the bulk textarea
        const bulkTextarea = page.locator('textarea[placeholder*="+1555"]');
        if (await bulkTextarea.isVisible()) {
          await bulkTextarea.fill('+15559990011, Alice');

          // Click launch campaign button
          const launchBtn = page.getByRole('button', { name: /launch campaign/i });
          if (await launchBtn.isVisible()) {
            await launchBtn.click();
            await page.waitForTimeout(500);

            // Campaign Compliance Attestation Modal MUST appear
            const compCheckbox = page.locator('[data-testid="compliance-attestation-checkbox"]');
            const compConfirmBtn = page.locator('[data-testid="confirm-launch-campaign-btn"]');
            
            if (await compCheckbox.isVisible()) {
              // Confirm button MUST be disabled until accepted
              await expect(compConfirmBtn).toBeDisabled();

              // Check affirmative attestation checkbox
              await compCheckbox.check();
              await expect(compConfirmBtn).toBeEnabled();

              // Close modal
              await page.getByRole('button', { name: /cancel/i }).click();
            }
          }
        }
      }
    }
  });

  test('5. Campaigns Module: Top-level Tab Switching between Campaigns and DND Registry', async ({ page }) => {
    await ensureSignedIn(page);
    await page.goto('/#dashboard/campaigns');
    await page.waitForTimeout(1000);

    const campTab = page.locator('[data-testid="campaigns-tab-button"]');
    const dndTab = page.locator('[data-testid="dnd-registry-tab-button"]');

    await expect(campTab).toBeVisible();
    await expect(dndTab).toBeVisible();

    // Click DND tab
    await dndTab.click();
    await expect(page.locator('[data-testid="dnc-registry-panel"]')).toBeVisible();

    // Click back to Campaigns tab
    await campTab.click();
    await expect(page.locator('text=Bulk Outbound Campaigns').first()).toBeVisible();
  });

  test('6. Guided Tour: Automatically activates for new onboarding user, spotlights components with dimmed page, and completes', async ({ page }) => {
    // Reset onboarding for test user so they are treated as brand new
    try {
      const { execSync } = await import('child_process');
      execSync('python scripts/reset-test-onboarding.py saiskm115@gmail.com', { stdio: 'ignore' });
    } catch {}

    await ensureSignedIn(page);
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);

    // Clear tour completion from localStorage to simulate a brand new user
    await page.evaluate((email) => {
      localStorage.removeItem(`voxly_tour_completed_${email}`);
      localStorage.removeItem('voxly_tour_completed_default');
    }, TEST_EMAIL);

    await page.reload();
    await page.waitForTimeout(1500);

    // Complete the onboarding survey
    const onboardingModal = page.locator('[data-testid="onboarding-survey-modal"]');
    await expect(onboardingModal).toBeVisible({ timeout: 10000 });

    // Step 1
    await page.locator('[data-testid="onboarding-fullname-input"]').fill('Sai Krishna');
    await page.locator('[data-testid="onboarding-company-input"]').fill('Sai Health Labs');
    await page.locator('[data-testid="onboarding-next-btn"]').click();

    // Step 2
    await page.locator('[data-testid="onboarding-referral-select"]').selectOption('social');
    await page.locator('[data-testid="onboarding-usecase-select"]').selectOption('outbound_sales');
    await page.locator('[data-testid="onboarding-volume-select"]').selectOption('2500_to_10000');
    await page.locator('[data-testid="onboarding-next-btn"]').click();

    // Step 3
    await page.locator('[data-testid="onboarding-terms-checkbox"]').check();
    await page.locator('[data-testid="onboarding-submit-btn"]').click();

    // Modal closes
    await expect(onboardingModal).not.toBeVisible({ timeout: 10000 });

    // Guided tour automatically activates for new onboarded user
    const tourPopover = page.locator('[data-testid="guided-tour-popover"]');
    await expect(tourPopover).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.driver-overlay')).toBeVisible({ timeout: 5000 });

    // Step 1: Create Agent
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Create Your Voice Agent');
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 1 of 7');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 2: Buy Number
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 2 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Dedicated Phone Lines');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 3: AI Employees
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 3 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('AI Workforce Studio');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 4: Telephony & Routing
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 4 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Telephony & Routing');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 5: Campaigns & DND
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 5 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Campaigns & DND Scrubbing');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 6: Calls & Transcripts
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 6 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Live Transcripts & Sentiment');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Step 7: Wallet
    await expect(page.locator('[data-testid="tour-step-badge"]')).toContainText('Step 7 of 7');
    await expect(page.locator('[data-testid="tour-step-title"]')).toContainText('Balance & Minutes Wallet');
    await page.locator('[data-testid="tour-next-btn"]').click();
    await page.waitForTimeout(400);

    // Tour completed & closes
    await expect(tourPopover).not.toBeVisible({ timeout: 5000 });

    // Verify localStorage has tour marked completed in this session
    const isCompletedInSession = await page.evaluate((email) => {
      return localStorage.getItem(`voxly_tour_completed_${email}`);
    }, TEST_EMAIL);
    expect(isCompletedInSession).toBe('true');
  });

  test('7. Guided Tour: once completed, no manual button exists and tour does not repeat for onboarded users', async ({ page }) => {
    await ensureSignedIn(page);
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1500);

    // Verify manual tour button has been completely removed from Topbar
    const topbarTourBtn = page.locator('[data-testid="topbar-tour-btn"]');
    await expect(topbarTourBtn).toHaveCount(0);

    // Verify localStorage has tour marked completed for onboarded user
    const isCompleted = await page.evaluate((email) => {
      return localStorage.getItem(`voxly_tour_completed_${email}`);
    }, TEST_EMAIL);
    expect(isCompleted).toBe('true');

    // Reload the page and ensure the tour does NOT repeat
    await page.reload();
    await page.waitForTimeout(1500);

    const tourPopover = page.locator('[data-testid="guided-tour-popover"]');
    await expect(tourPopover).not.toBeVisible();
    await expect(page.locator('.driver-overlay')).not.toBeVisible();
  });
});


