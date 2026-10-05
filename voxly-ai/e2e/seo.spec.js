import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

test.describe('SEO & Search Indexing Requirements Verification', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('page has proper title, meta description, and canonical tags', async ({ page }) => {
    // 1. Title tag
    await expect(page).toHaveTitle(/Voxly — The AI Employee for Every Conversation/i);

    // 2. Meta description
    const desc = await page.locator('meta[name="description"]').getAttribute('content');
    expect(desc).toBeTruthy();
    expect(desc.length).toBeGreaterThan(50);
    expect(desc.toLowerCase()).toContain('ai voice');

    // 3. Keywords
    const keywords = await page.locator('meta[name="keywords"]').getAttribute('content');
    expect(keywords).toBeTruthy();
    expect(keywords).toContain('voice');

    // 4. Canonical URL
    const canonical = await page.locator('link[rel="canonical"]').getAttribute('href');
    expect(canonical).toBe('https://voxly.ai/');

    // 5. Robots directives
    const robots = await page.locator('meta[name="robots"]').getAttribute('content');
    expect(robots).toContain('index');
    expect(robots).toContain('follow');

    const googlebot = await page.locator('meta[name="googlebot"]').getAttribute('content');
    expect(googlebot).toContain('index');
  });

  test('page satisfies single H1 requirement and semantic heading hierarchy', async ({ page }) => {
    const h1Elements = page.locator('h1');
    const h1Count = await h1Elements.count();
    expect(h1Count).toBe(1);

    const h1Text = await h1Elements.first().textContent();
    expect(h1Text).toMatch(/your ai employee/i);

    // Verify main tag exists
    const mainCount = await page.locator('main').count();
    expect(mainCount).toBe(1);
  });

  test('OpenGraph and Twitter card metadata are properly configured', async ({ page }) => {
    expect(await page.locator('meta[property="og:type"]').getAttribute('content')).toBe('website');
    expect(await page.locator('meta[property="og:url"]').getAttribute('content')).toBe('https://voxly.ai/');
    expect(await page.locator('meta[property="og:site_name"]').getAttribute('content')).toBe('Voxly AI');
    expect(await page.locator('meta[property="og:locale"]').getAttribute('content')).toBe('en_US');
    expect(await page.locator('meta[property="og:title"]').getAttribute('content')).toBeTruthy();
    expect(await page.locator('meta[property="og:description"]').getAttribute('content')).toBeTruthy();
    expect(await page.locator('meta[property="og:image"]').getAttribute('content')).toContain('VoxlyBot_preview.png');

    expect(await page.locator('meta[name="twitter:card"]').getAttribute('content')).toBe('summary_large_image');
    expect(await page.locator('meta[name="twitter:title"]').getAttribute('content')).toBeTruthy();
    expect(await page.locator('meta[name="twitter:image"]').getAttribute('content')).toContain('VoxlyBot_preview.png');
  });

  test('JSON-LD structured data contains Organization, WebSite, SoftwareApplication, Breadcrumbs, and FAQPage', async ({ page }) => {
    const jsonLdScript = await page.locator('script[type="application/ld+json"]').textContent();
    expect(jsonLdScript).toBeTruthy();

    const parsed = JSON.parse(jsonLdScript);
    expect(parsed['@context']).toBe('https://schema.org');
    expect(Array.isArray(parsed['@graph'])).toBeTruthy();

    const types = parsed['@graph'].map(item => item['@type']);
    expect(types).toContain('Organization');
    expect(types).toContain('WebSite');
    expect(types).toContain('SoftwareApplication');
    expect(types).toContain('BreadcrumbList');
    expect(types).toContain('FAQPage');

    // Verify FAQ schema matches page FAQ
    const faqNode = parsed['@graph'].find(item => item['@type'] === 'FAQPage');
    expect(faqNode.mainEntity.length).toBeGreaterThanOrEqual(5);
    expect(faqNode.mainEntity[0].name).toContain('Voxly');
  });

  test('robots.txt and sitemap.xml files are accessible and valid', async ({ request }) => {
    // 1. Robots.txt
    const robotsRes = await request.get('/robots.txt');
    expect(robotsRes.status()).toBe(200);
    const robotsText = await robotsRes.text();
    expect(robotsText).toContain('User-agent: *');
    expect(robotsText).toContain('Allow: /');
    expect(robotsText).toContain('Disallow: /api/');
    expect(robotsText).toContain('Sitemap: https://voxly.ai/sitemap.xml');

    // 2. Sitemap.xml
    const sitemapRes = await request.get('/sitemap.xml');
    expect(sitemapRes.status()).toBe(200);
    const sitemapText = await sitemapRes.text();
    expect(sitemapText).toContain('<loc>https://voxly.ai/</loc>');
    expect(sitemapText).toContain('<changefreq>');
    expect(sitemapText).toContain('<priority>');
  });

  test('dynamic document.title updates when entering dashboard tabs and resets on landing', async ({ page }) => {
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(300);
    expect(await page.title()).toBe('Workspace Overview — Voxly Console');

    // Check noindex tag added on dashboard
    const robotsConsole = await page.locator('meta[name="robots"][data-voxly-console]').getAttribute('content');
    expect(robotsConsole).toBe('noindex, nofollow');

    // Navigate to integrations tab
    await page.goto('/#dashboard/integrations');
    await page.waitForTimeout(300);
    expect(await page.title()).toBe('Tool Integrations (177+ Tools) — Voxly Console');

    // Return to landing page
    await page.goto('/');
    await page.waitForTimeout(300);
    expect(await page.title()).toBe('Voxly — The AI Employee for Every Conversation');

    // Check noindex tag removed
    const noindexExists = await page.locator('meta[name="robots"][data-voxly-console]').count();
    expect(noindexExists).toBe(0);
  });
});
