import config from '../../../voxly-ai/vite.config.js';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Separate optimizer cache avoids invalidating the user's existing dev server.
export default { ...config, cacheDir: join(tmpdir(), 'voxly-console-verification-vite') };
