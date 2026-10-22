import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import { buildEmployee } from './helpers/api.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionPath = path.resolve(__dirname, '../../data/e2e_session.json');

test.describe('Comprehensive Verification of All Pages and Console Tabs', () => {
  let consoleErrors = [];

  test('Check marketing landing page', async ({ page }) => {
    consoleErrors = [];
    page.on('pageerror', (err) => {
      consoleErrors.push(err.message);
    });

    await page.goto('/');
    await expect(page).toHaveTitle(/Voxly/i, { timeout: 15000 });
    await expect(page.locator('body')).not.toBeEmpty();

    // Verify key landing page components exist
    await expect(page.getByRole('button', { name: /sign in/i }).first()).toBeVisible();
    
    // Check no uncaught react crashes
    const reactCrashed = consoleErrors.some(e => e.includes('Minified React error') || e.includes('is not a function'));
    expect(reactCrashed).toBeFalsy();
  });

  test('Check all agent console pages, tabs, and agent studio subpanels', async ({ page }) => {
    test.skip(!fs.existsSync(sessionPath), 'Missing data/e2e_session.json');

    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
    const u = sess.user;
    const sessionUser = {
      id: u.userId,
      name: u.fullName || u.email,
      email: u.email,
      tenantId: sess.tenant?.tenantId,
      hasCompletedOnboarding: true,
    };

    consoleErrors = [];
    page.on('pageerror', (err) => {
      console.log('BROWSER PAGE ERROR:', err.message);
      consoleErrors.push(err.message);
    });

    // Inject session into sessionStorage and localStorage
    await page.addInitScript(
      ({ token, sessionUser }) => {
        sessionStorage.setItem('voxly_auth_token', token);
        localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
        localStorage.setItem('voxly_tour_completed', 'true');
      },
      { token: sess.token, sessionUser }
    );

    // 1. OVERVIEW TAB
    console.log('Testing #dashboard/overview...');
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(2000);
    // Ensure no blank screen
    const overviewContent = await page.locator('main').innerText();
    expect(overviewContent.length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 2. EMPLOYEES FLEET TAB
    console.log('Testing #dashboard/employees...');
    await page.goto('/#dashboard/employees');
    await page.waitForTimeout(2000);
    const employeesContent = await page.locator('main').innerText();
    expect(employeesContent.length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // Find first agent card if available, or create one
    let agentCard = page.locator('[data-testid="agent-card"]').first();
    let hasAgent = (await agentCard.count()) > 0;

    if (!hasAgent) {
      console.log('No agents in fleet, creating one via API...');
      try {
        await buildEmployee(sess.token, {
          brief: 'Test agent for customer support in Hyderabad. Greet customers and take appointments.',
          language: 'en-IN',
          mode: 'instant_lead',
          employeeName: 'Priya E2E Support',
        });
        await page.goto('/#dashboard/employees');
        await page.waitForTimeout(2500);
        agentCard = page.locator('[data-testid="agent-card"]').first();
        hasAgent = (await agentCard.count()) > 0;
      } catch (err) {
        console.warn('Could not auto-create agent via helper:', err);
      }
    }

    if (hasAgent) {
      console.log('Found agent in fleet, opening workbench studio...');
      const openBtn = page.locator('[data-testid="agent-open-builder"]').first();
      if (await openBtn.isVisible()) {
        await openBtn.click();
      } else {
        await agentCard.click();
      }
      await page.waitForTimeout(2000);

      // Verify AgentStudioModule mounted
      const studioContent = await page.locator('main').innerText();
      expect(studioContent.length).toBeGreaterThan(20);

      // Check Tabs inside Agent Studio:
      // a. Overview
      console.log('Testing agent studio tab: overview');
      const overviewTab = page.locator('#agent-tab-overview');
      if (await overviewTab.isVisible()) {
        await overviewTab.click();
        await page.waitForTimeout(1000);
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
      }

      // b. Script
      console.log('Testing agent studio tab: script');
      const scriptTab = page.locator('#agent-tab-script');
      if (await scriptTab.isVisible()) {
        await scriptTab.click();
        await page.waitForTimeout(1000);
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
      }

      // c. Calls (WHERE PREVIOUS CRASH HAPPENED)
      console.log('Testing agent studio tab: calls (AgentCallsPanel & AgentInboundPanel)...');
      const callsTab = page.locator('#agent-tab-calls');
      if (await callsTab.isVisible()) {
        await callsTab.click();
        await page.waitForTimeout(1500);

        // Verify AgentCallsPanel is visible and NOT blank
        const callsPanel = page.locator('[data-testid="agent-calls-panel"]');
        await expect(callsPanel).toBeVisible({ timeout: 10000 });
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

        // Click inbound subtab to test AgentInboundPanel
        console.log('Testing agent studio calls subtab: inbound');
        await page.locator('#agent-calls-tab-inbound').click();
        await page.waitForTimeout(1000);

        // Verify AgentInboundPanel loaded properly without blanking
        const inboundPanel = page.locator('[data-testid="agent-inbound-panel"]');
        await expect(inboundPanel).toBeVisible({ timeout: 10000 });
        const inboundText = await inboundPanel.innerText();
        expect(inboundText.toUpperCase()).toContain('ASSIGNED PHONE LINE');

        // Test outbound subpanel
        console.log('Testing agent studio calls subtab: outbound');
        await page.locator('#agent-calls-tab-outbound').click();
        await page.waitForTimeout(1000);
        expect(await page.locator('#agent-calls-panel-outbound').isVisible()).toBeTruthy();
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

        // Test history subpanel
        console.log('Testing agent studio calls subtab: history');
        await page.locator('#agent-calls-tab-history').click();
        await page.waitForTimeout(1000);
        expect(await page.locator('#agent-calls-panel-history').isVisible()).toBeTruthy();
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

        // Test leads subpanel
        console.log('Testing agent studio calls subtab: leads');
        await page.locator('#agent-calls-tab-leads').click();
        await page.waitForTimeout(1000);
        expect(await page.locator('#agent-calls-panel-leads').isVisible()).toBeTruthy();
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
      }

      // d. Settings tab
      console.log('Testing agent studio tab: settings');
      const settingsTab = page.locator('#agent-tab-settings');
      if (await settingsTab.isVisible()) {
        await settingsTab.click();
        await page.waitForTimeout(1500);
        expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
        const settingsText = await page.locator('#agent-panel-settings').innerText();
        expect(settingsText.length).toBeGreaterThan(20);
      }
    }

    // 3. PHONE NUMBERS TAB
    console.log('Testing #dashboard/phone-numbers...');
    await page.goto('/#dashboard/phone-numbers');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 4. CALLS TAB
    console.log('Testing #dashboard/calls...');
    await page.goto('/#dashboard/calls');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 5. LEADS TAB
    console.log('Testing #dashboard/leads...');
    await page.goto('/#dashboard/leads');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 6. CAMPAIGNS TAB
    console.log('Testing #dashboard/campaigns...');
    await page.goto('/#dashboard/campaigns');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // DND tab inside campaigns
    const dndTabBtn = page.locator('[data-testid="dnd-registry-tab-button"]');
    if (await dndTabBtn.isVisible()) {
      console.log('Testing campaigns DND registry subtab...');
      await dndTabBtn.click();
      await page.waitForTimeout(1000);
      expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
      expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
    }

    // 7. BILLING TAB
    console.log('Testing #dashboard/billing...');
    await page.goto('/#dashboard/billing');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 8. INTEGRATIONS TAB
    console.log('Testing #dashboard/integrations...');
    await page.goto('/#dashboard/integrations');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // 9. SETTINGS TAB
    console.log('Testing #dashboard/settings...');
    await page.goto('/#dashboard/settings');
    await page.waitForTimeout(2000);
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(20);
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);

    // Check that there were NO "is not a function" or React fatal crashes
    const fatalErrors = consoleErrors.filter(e => 
      e.includes('is not a function') || 
      e.includes('Minified React error') ||
      e.includes('Cannot read properties of undefined')
    );
    expect(fatalErrors).toEqual([]);
    console.log('ALL PAGES AND CONSOLE MODULES TESTED SUCCESSFULLY WITH ZERO BLANK PAGES OR FATAL ERRORS!');
  });

  test('Verify Agent Studio Calls & Inbound Panel (Regression Test for blank page)', async ({ page }) => {
    test.skip(!fs.existsSync(sessionPath), 'Missing data/e2e_session.json');

    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
    const u = sess.user;
    const sessionUser = {
      id: u.userId,
      name: u.fullName || u.email,
      email: u.email,
      tenantId: sess.tenant?.tenantId,
      hasCompletedOnboarding: true,
    };

    const errors = [];
    page.on('pageerror', (err) => {
      console.log('BROWSER PAGE ERROR in Studio Calls test:', err.message);
      errors.push(err.message);
    });

    await page.addInitScript(
      ({ token, sessionUser }) => {
        sessionStorage.setItem('voxly_auth_token', token);
        localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
        localStorage.setItem('voxly_tour_completed', 'true');
      },
      { token: sess.token, sessionUser }
    );

    await page.goto('/#dashboard/employees');
    await page.waitForTimeout(2000);

    // If no agent, create one via UI wizard
    let agentCard = page.locator('[data-testid="agent-card"]').first();
    if ((await agentCard.count()) === 0) {
      console.log('Creating an employee via wizard to test workbench...');
      const createBtn = page.getByRole('button', { name: /create ai employee/i }).first();
      await createBtn.click();
      await expect(page.getByTestId('create-employee-modal')).toBeVisible({ timeout: 10000 });
      await page.getByTestId('employee-brief-input').fill('E2E Verification Doctor Appointment Assistant in Hyderabad');
      await page.getByTestId('employee-language-select').selectOption('en-IN');
      await page.getByTestId('create-next').click();
      await expect(page.getByTestId('create-employee-modal')).toBeHidden({ timeout: 60000 });
      await page.waitForTimeout(2000);
    } else {
      const openBtn = page.locator('[data-testid="agent-open-calls"]').first();
      if (await openBtn.isVisible()) {
        await openBtn.click();
      } else {
        await agentCard.click();
      }
      await page.waitForTimeout(1500);
    }

    // Now navigate to calls tab
    const callsTab = page.locator('#agent-tab-calls');
    if (await callsTab.isVisible()) {
      await callsTab.click();
    }
    await page.waitForTimeout(1500);

    // Switch to inbound subtab
    const inboundTab = page.locator('#agent-calls-tab-inbound');
    if (await inboundTab.isVisible()) {
      await inboundTab.click();
      await page.waitForTimeout(1000);
    }

    // Assert Calls Panel and Inbound Panel are visible and rendered without blank screen
    await expect(page.locator('[data-testid="agent-calls-panel"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="agent-inbound-panel"]')).toBeVisible({ timeout: 15000 });

    // Assert key content inside Inbound Panel
    await expect(page.getByText('Assigned Phone Line')).toBeVisible();
    await expect(page.getByText('Reception Status')).toBeVisible();
    await expect(page.getByText('Verify Voice Line')).toBeVisible();

    // Check no fatal error was thrown
    const hasFatal = errors.some(e => e.includes('is not a function'));
    expect(hasFatal).toBeFalsy();
    expect(await page.locator('[data-testid="error-boundary-fallback"]').count()).toBe(0);
    console.log('Agent Inbound Panel rendered perfectly with no blank page!');
  });
});
