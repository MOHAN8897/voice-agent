// Render public content and route metadata at build time. Never fetch account data.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const server = await createServer({ root, configFile: false, server: { middlewareMode: true }, appType: 'custom' });
const escape = (text) => String(text).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
try {
  const { render, PUBLIC_PAGES, PUBLIC_PATHS, SITE_URL } = await server.ssrLoadModule('/src/prerender.jsx');
  const template = await fs.readFile(path.join(root, 'dist/index.html'), 'utf8');
  for (const [view, route] of Object.entries(PUBLIC_PATHS)) {
    const meta = PUBLIC_PAGES[view];
    let html = template.replace(/<title>.*?<\/title>/, `<title>${escape(meta.title)}</title>`);
    html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(meta.description)}"`);
    const canonical = new URL(route, SITE_URL).href;
    html = html.replace(/(<link rel="canonical" href=")[^"]*/, `$1${canonical}`);
    for (const [attribute, key, value] of [['property', 'og:title', meta.title], ['property', 'og:description', meta.description], ['property', 'og:url', canonical], ['name', 'twitter:title', meta.title], ['name', 'twitter:description', meta.description], ['name', 'twitter:url', canonical]]) {
      html = html.replace(new RegExp(`(<meta ${attribute}="${key}" content=")[^"]*`), `$1${escape(value)}`);
    }
    html = html.replace('<div id="root"></div>', () => `<div id="root">${render(view)}</div>`);
    const folder = route === '/' ? path.join(root, 'dist') : path.join(root, 'dist', route.slice(1));
    await fs.mkdir(folder, { recursive: true });
    await fs.writeFile(path.join(folder, 'index.html'), html);
  }
  console.log(`Prerendered ${Object.keys(PUBLIC_PATHS).length} public pages with distinct metadata.`);
} finally { await server.close(); }
