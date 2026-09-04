/**
 * Build a static home-page-only export for Hostinger static hosting.
 * Temporarily hides app/dev/api routes, then restores them after build.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.join(root, "..", "app");
const stashDir = path.join(root, "..", ".landing-stash");

const HIDE = [
  "app",
  "dev",
  "login",
  "api",
  "(marketing)/pricing",
  "(marketing)/docs",
];

function moveIntoStash(rel) {
  const from = path.join(appDir, rel);
  if (!fs.existsSync(from)) return;
  const to = path.join(stashDir, rel);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.cpSync(from, to, { recursive: true });
  fs.rmSync(from, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}

function restoreFromStash(rel) {
  const from = path.join(stashDir, rel);
  if (!fs.existsSync(from)) return;
  const to = path.join(appDir, rel);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.cpSync(from, to, { recursive: true });
  fs.rmSync(from, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}

function stashRoutes() {
  if (fs.existsSync(stashDir)) {
    throw new Error(".landing-stash already exists — previous build may have failed mid-run");
  }
  fs.mkdirSync(stashDir, { recursive: true });
  for (const rel of HIDE) moveIntoStash(rel);
}

function unstashRoutes() {
  for (const rel of [...HIDE].reverse()) restoreFromStash(rel);
  if (fs.existsSync(stashDir)) {
    fs.rmSync(stashDir, { recursive: true, force: true });
  }
}

function run(cmd, args, env = {}) {
  const result = spawnSync(cmd, args, {
    cwd: path.join(root, ".."),
    stdio: "inherit",
    shell: process.platform === "win32",
    env: { ...process.env, ...env },
  });
  if (result.status !== 0) {
    throw new Error(`${cmd} ${args.join(" ")} failed with code ${result.status}`);
  }
}

try {
  console.log("[landing] Stashing non-home routes…");
  stashRoutes();

  const configPath = path.join(root, "..", "next.config.mjs");
  const landingPath = path.join(root, "..", "next.config.landing.mjs");
  const backupPath = path.join(root, "..", "next.config.mjs.bak");
  const hadConfig = fs.existsSync(configPath);
  if (hadConfig) fs.copyFileSync(configPath, backupPath);
  fs.copyFileSync(landingPath, configPath);

  try {
    console.log("[landing] Building static export…");
    run("npx", ["next", "build"]);
  } finally {
    if (hadConfig && fs.existsSync(backupPath)) {
      fs.copyFileSync(backupPath, configPath);
      fs.rmSync(backupPath, { force: true });
    }
  }

  const outDir = path.join(root, "..", "out-landing");
  if (!fs.existsSync(path.join(outDir, "index.html"))) {
    throw new Error("Build finished but out-landing/index.html is missing");
  }
  console.log(`[landing] Done → ${outDir}`);
} finally {
  console.log("[landing] Restoring routes…");
  unstashRoutes();
}
