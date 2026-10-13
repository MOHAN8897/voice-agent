import { test, expect } from '@playwright/test';

test.describe('SEO and search indexing', () => {
  test('landing page exposes consistent, factual metadata', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Dialtact — AI Voice Agents for Customer Calls');

    const description = await page.locator('meta[name="description"]').getAttribute('content');
    expect(description).toContain('AI voice agents');
    expect(description.length).toBeGreaterThan(50);
    expect(await page.locator('meta[name="keywords"]').count()).toBe(0);
    expect(await page.locator('link[rel="canonical"]').getAttribute('href')).toBe('https://www.dialtact.com/');
    expect(await page.locator('meta[name="robots"]').getAttribute('content')).toContain('index');

    expect(await page.locator('meta[property="og:type"]').getAttribute('content')).toBe('website');
    expect(await page.locator('meta[property="og:url"]').getAttribute('content')).toBe('https://www.dialtact.com/');
    expect(await page.locator('meta[property="og:site_name"]').getAttribute('content')).toBe('Dialtact');
    expect(await page.locator('meta[property="og:image"]').getAttribute('content')).toContain('VoxlyBot_preview.png');
    expect(await page.locator('meta[name="twitter:card"]').getAttribute('content')).toBe('summary_large_image');
  });

  test('structured data contains only supported, substantiated entities', async ({ page }) => {
    await page.goto('/');
    const script = await page.locator('script[type="application/ld+json"]').textContent();
    const parsed = JSON.parse(script);
    expect(parsed['@context']).toBe('https://schema.org');
    const graph = parsed['@graph'];
    expect(graph.map((item) => item['@type'])).toEqual(['Organization', 'WebSite', 'SoftwareApplication']);
    expect(graph.every((item) => item.url === 'https://www.dialtact.com/')).toBe(true);
    expect(JSON.stringify(graph)).not.toMatch(/AggregateRating|ratingCount|priceValidUntil/);
  });

  test('page views update their title and description while keeping the single-page canonical', async ({ page }) => {
    const routes = [
      ['support', 'Customer Support & Contact — Dialtact', 'Contact Dialtact'],
      ['company', 'About Dialtact — AI Voice Agent Platform', 'Learn about Dialtact'],
      ['privacy', 'Privacy Policy — Dialtact', 'Read how Dialtact handles'],
      ['terms', 'Terms of Service — Dialtact', 'Review the terms'],
      ['security', 'Security — Dialtact', 'Learn about Dialtact security'],
    ];
    for (const [route, title, description] of routes) {
      await page.goto(`/#${route}`);
      await expect(page).toHaveTitle(title);
      await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', new RegExp(description));
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://www.dialtact.com/');
    }
  });

  test('robots and sitemap point to the canonical public domain', async ({ request }) => {
    const robotsResponse = await request.get('/robots.txt');
    expect(robotsResponse.status()).toBe(200);
    const robots = await robotsResponse.text();
    expect(robots).toContain('User-agent: *');
    expect(robots).toContain('Disallow: /api/');
    expect(robots).toContain('Sitemap: https://www.dialtact.com/sitemap.xml');
    expect(robots).not.toContain('voxly.ai');

    const sitemapResponse = await request.get('/sitemap.xml');
    expect(sitemapResponse.status()).toBe(200);
    const sitemap = await sitemapResponse.text();
    expect(sitemap).toContain('<loc>https://www.dialtact.com/</loc>');
    expect(sitemap).not.toContain('voxly.ai');
    expect(sitemap).not.toContain('<changefreq>');
  });

  test('dashboard views remain noindex and landing removes the private-view directive', async ({ page }) => {
    await page.goto('/#dashboard/overview');
    await expect(page).toHaveTitle('Workspace Overview — Dialtact Console');
    await expect(page.locator('meta[name="robots"][data-voxly-console]')).toHaveAttribute('content', 'noindex, nofollow');

    await page.goto('/#dashboard/integrations');
    await expect(page).toHaveTitle('Integrations — Dialtact Console');

    await page.goto('/');
    await expect(page).toHaveTitle('Dialtact — AI Voice Agents for Customer Calls');
    await expect(page.locator('meta[name="robots"][data-voxly-console]')).toHaveCount(0);
  });
});
