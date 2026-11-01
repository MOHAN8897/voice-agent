// Render public content and route metadata at build time. Never fetch account data.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const server = await createServer({ root, configFile: false, resolve: { alias: { '@': path.join(root, 'src') } }, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true }, appType: 'custom' });
const escape = (text) => String(text).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
try {
  const { render, PUBLIC_PAGES, PUBLIC_PATHS, INDEXABLE_VIEWS, SITE_URL } = await server.ssrLoadModule('/src/prerender.jsx');
  const template = await fs.readFile(path.join(root, 'dist/index.html'), 'utf8');
  for (const [view, route] of Object.entries(PUBLIC_PATHS)) {
    const meta = PUBLIC_PAGES[view];
    let html = template.replace(/<title>.*?<\/title>/, `<title>${escape(meta.title)}</title>`);
    html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(meta.description)}"`);
    const canonical = new URL(meta.canonicalPath || route, SITE_URL).href;
    if (meta.robots) html = html.replace(/(<meta name="robots" content=")[^"]*/, `$1${escape(meta.robots)}`);
    html = html.replace(/(<link rel="canonical" href=")[^"]*/, `$1${canonical}`);
    for (const [attribute, key, value] of [['property', 'og:title', meta.title], ['property', 'og:description', meta.description], ['property', 'og:url', canonical], ['name', 'twitter:title', meta.title], ['name', 'twitter:description', meta.description], ['name', 'twitter:url', canonical]]) {
      html = html.replace(new RegExp(`(<meta ${attribute}="${key}" content=")[^"]*`), `$1${escape(value)}`);
    }
    html = html.replace('<div id="root"></div>', () => `<div id="root">${render(view)}</div>`);
    const folder = route === '/' ? path.join(root, 'dist') : path.join(root, 'dist', route.slice(1));
    await fs.mkdir(folder, { recursive: true });
    await fs.writeFile(path.join(folder, 'index.html'), html);
  }
  // The sitemap is generated from the same route table, so it can never list a page
  // that does not exist or omit one that does.
  const today = new Date().toISOString().slice(0, 10);
  const urls = INDEXABLE_VIEWS.map((view) => `  <url><loc>${new URL(PUBLIC_PATHS[view], SITE_URL).href}</loc><lastmod>${today}</lastmod></url>`);
  const sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ...urls, '</urlset>', ''].join('\n');
  await fs.writeFile(path.join(root, 'dist/sitemap.xml'), sitemap);
  console.log(`Prerendered ${Object.keys(PUBLIC_PATHS).length} public pages with distinct metadata.`);
} finally { await server.close(); }
