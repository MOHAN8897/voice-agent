import { test, expect } from '@playwright/test';

test.describe('Mobile Responsiveness & Viewport Optimization', () => {
  test.use({
    viewport: { width: 375, height: 667 }, // iPhone SE / standard mobile viewport
    isMobile: true,
    hasTouch: true,
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('landing page has zero horizontal overflow at 375px viewport', async ({ page }) => {
    // Check initial load
    const noOverflowInitial = await page.evaluate(() => {
      return document.documentElement.scrollWidth <= window.innerWidth;
    });
    expect(noOverflowInitial).toBe(true);

    // Scroll through the entire page in increments to trigger all lazy sections & scroll animations
    const pageHeight = await page.evaluate(() => document.body.scrollHeight);
    for (let scrollY = 0; scrollY < pageHeight; scrollY += 600) {
      await page.evaluate((y) => window.scrollTo(0, y), scrollY);
      await page.waitForTimeout(40);
      const isWide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (isWide) {
        const offending = await page.evaluate(() => {
          const docW = document.documentElement.clientWidth;
          const bad = [];
          document.querySelectorAll('*').forEach((el) => {
            const r = el.getBoundingClientRect();
            if (r.right > docW + 2) {
              bad.push({
                tag: el.tagName,
                cls: (el.className || '').toString().slice(0, 80),
                right: r.right,
                docW,
              });
            }
          });
          return bad.slice(0, 5);
        });
        expect(offending).toEqual([]);
      }
    }
  });

  test('landing page has zero horizontal overflow at ultra-narrow 320px viewport', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(100);

    const noOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth <= window.innerWidth;
    });
    expect(noOverflow).toBe(true);
  });

  test('mobile navigation hamburger opens drawer and links have accessible touch targets', async ({ page }) => {
    const hamburgerBtn = page.locator('button[aria-label="Toggle navigation"]');
    await expect(hamburgerBtn).toBeVisible();

    // Verify initial aria state
    expect(await hamburgerBtn.getAttribute('aria-expanded')).toBe('false');

    // Click hamburger to open mobile menu
    await hamburgerBtn.click();
    await expect(hamburgerBtn).toHaveAttribute('aria-expanded', 'true');

    // Check that mobile navigation drawer links are visible and meet >= 44px touch targets
    const navLinks = page.locator('[data-testid="mobile-nav-link"]');
    const count = await navLinks.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const link = navLinks.nth(i);
      await expect(link).toBeVisible();
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box.height).toBeGreaterThanOrEqual(44);
    }

    // Verify mobile drawer console action button
    const consoleBtn = page.locator('[data-testid="mobile-console-btn"]');
    await expect(consoleBtn).toBeVisible();
    const btnBox = await consoleBtn.boundingBox();
    expect(btnBox.height).toBeGreaterThanOrEqual(44);

    // Close menu
    await hamburgerBtn.click();
    await expect(hamburgerBtn).toHaveAttribute('aria-expanded', 'false');
  });

  test('AuthModal renders within mobile viewport without clipping and has >=16px font inputs', async ({ page }) => {
    // Open modal via Hero CTA
    const buildBtn = page.locator('button:has-text("Build your agent")').first();
    await expect(buildBtn).toBeVisible();
    await buildBtn.click();

    // Modal dialog is present
    const modalDialog = page.locator('div[role="dialog"]');
    await expect(modalDialog).toBeVisible();

    // Check modal bounds fit in viewport
    const modalBox = await modalDialog.boundingBox();
    expect(modalBox).not.toBeNull();
    const viewport = page.viewportSize();
    expect(modalBox.height).toBeLessThanOrEqual(viewport.height);
    expect(modalBox.width).toBeLessThanOrEqual(viewport.width);

    // Verify input font size >= 16px to prevent iOS Safari auto-zoom
    const emailInput = modalDialog.locator('input[type="email"]').first();
    if (await emailInput.isVisible()) {
      const fontSize = await emailInput.evaluate((el) => {
        return parseFloat(window.getComputedStyle(el).fontSize);
      });
      expect(fontSize).toBeGreaterThanOrEqual(16);
    }

    // Verify close button is accessible
    const closeBtn = modalDialog.locator('button[aria-label="Close dialog"]');
    await expect(closeBtn).toBeVisible();
    const closeBox = await closeBtn.boundingBox();
    expect(closeBox.width).toBeGreaterThanOrEqual(32);
    expect(closeBox.height).toBeGreaterThanOrEqual(32);

    await closeBtn.click();
    await expect(modalDialog).not.toBeVisible();
  });

  test('TalkToMeModal renders properly and closes on mobile', async ({ page }) => {
    // Click "Hear it first" in Hero
    const hearBtn = page.locator('button:has-text("Hear it first")').first();
    await expect(hearBtn).toBeVisible();
    await hearBtn.click();

    const modal = page.locator('div[role="dialog"][aria-label="Audio sample player"]');
    await expect(modal).toBeVisible();

    // Check modal fits within viewport
    const box = await modal.boundingBox();
    const vp = page.viewportSize();
    expect(box.width).toBeLessThanOrEqual(vp.width);

    // Close modal
    const closeBtn = modal.locator('button[aria-label="Close"]');
    await expect(closeBtn).toBeVisible();
    await closeBtn.click();
    await expect(modal).not.toBeVisible();
  });

  test('Dashboard modules on mobile display without horizontal page overflow', async ({ page }) => {
    // Inject mock authenticated session so dashboard routes render immediately
    await page.evaluate(() => {
      const mockSession = {
        authenticated: true,
        user: { id: 'usr_test_mobile', email: 'e2e@voxly.ai', full_name: 'Mobile Tester' },
        org: { id: 'org_test_mobile', name: 'Mobile Org', plan: 'enterprise', balance_cents: 25000 },
      };
      localStorage.setItem('voxly_session_v2', JSON.stringify(mockSession));
      localStorage.setItem('voxly_token', 'mock_token_mobile');
    });

    const routes = [
      '#dashboard/overview',
      '#dashboard/employees',
      '#dashboard/integrations',
      '#dashboard/phone-numbers',
      '#dashboard/billing',
      '#dashboard/campaigns',
      '#dashboard/leads',
      '#dashboard/settings',
      '#dashboard/admin',
    ];

    for (const route of routes) {
      await page.goto('/' + route);
      await page.waitForTimeout(200);

      // Verify page does not horizontally blow out
      const fitsViewport = await page.evaluate(() => {
        return document.documentElement.scrollWidth <= window.innerWidth;
      });
      expect(fitsViewport).toBe(true);

      // Verify header/topbar is visible
      const topbar = page.locator('header').first();
      await expect(topbar).toBeVisible();
    }
  });

  test('AddFundsModal on billing module renders within viewport with >=16px font inputs', async ({ page }) => {
    await page.evaluate(() => {
      const mockSession = {
        authenticated: true,
        user: { id: 'usr_test_mobile', email: 'e2e@voxly.ai', full_name: 'Mobile Tester' },
        org: { id: 'org_test_mobile', name: 'Mobile Org', plan: 'enterprise', balance_cents: 25000 },
      };
      localStorage.setItem('voxly_session_v2', JSON.stringify(mockSession));
      localStorage.setItem('voxly_token', 'mock_token_mobile');
    });

    await page.goto('/#dashboard/billing');
    await page.waitForTimeout(200);

    // Click "Add funds" or top-up button
    const addFundsBtn = page.locator('button:has-text("Add credit"), button:has-text("Add funds")').first();
    if (await addFundsBtn.isVisible()) {
      await addFundsBtn.click();
      const modal = page.locator('div[role="dialog"]').first();
      await expect(modal).toBeVisible();

      // Check modal fits in mobile viewport
      const box = await modal.boundingBox();
      const vp = page.viewportSize();
      expect(box.height).toBeLessThanOrEqual(vp.height);
      expect(box.width).toBeLessThanOrEqual(vp.width);

      // Check input font size
      const input = modal.locator('input[type="number"]').first();
      if (await input.isVisible()) {
        const fontSize = await input.evaluate((el) => parseFloat(window.getComputedStyle(el).fontSize));
        expect(fontSize).toBeGreaterThanOrEqual(16);
      }

      // Close modal
      const closeBtn = modal.locator('button[aria-label="Close dialog"]').first();
      await closeBtn.click();
      await expect(modal).not.toBeVisible();
    }
  });

  test('Tablet (768px) and Desktop (1280px) viewports render with zero horizontal overflow', async ({ page }) => {
    // 1. Tablet Portrait (iPad Mini / Air standard)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    await page.waitForTimeout(150);
    const tabletFits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(tabletFits).toBe(true);

    // 2. Desktop Standard (1280px)
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForTimeout(150);
    const desktopFits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(desktopFits).toBe(true);
  });
});
