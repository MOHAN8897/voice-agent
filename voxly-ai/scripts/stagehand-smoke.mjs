/**
 * Optional AI-driven browser smoke (Stagehand). Requires OPENAI_API_KEY or ANTHROPIC_API_KEY.
 * Run: npm run test:stagehand (with API + Vite up, or set VOXLY_WEB_URL).
 */
import { Stagehand } from '@browserbasehq/stagehand';

const baseUrl = process.env.VOXLY_WEB_URL || 'http://127.0.0.1:5173';

async function main() {
  const stagehand = new Stagehand({
    env: 'LOCAL',
    verbose: 1,
    modelName: process.env.STAGEHAND_MODEL || 'gpt-4o',
  });
  await stagehand.init();
  const page = stagehand.page;
  await page.goto(baseUrl);
  await page.waitForLoadState('networkidle');
  const title = await page.title();
  if (!/voxly/i.test(title)) {
    throw new Error(`Unexpected page title: ${title}`);
  }
  console.log('Stagehand smoke OK:', title);
  await stagehand.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
