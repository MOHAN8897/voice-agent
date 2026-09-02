import { test as setup, expect } from "@playwright/test";
import { DEV_USER, E2E_USER } from "./helpers";

setup("authenticate", async ({ request }) => {
  const session = await request.get("/api/auth/session");
  const { app_configured } = await session.json();

  if (app_configured) {
    const login = await request.post("/api/app/login", { data: E2E_USER });
    if (!login.ok()) {
      throw new Error(`E2E setup login failed: ${await login.text()}`);
    }
    const body = await login.json();
    expect(body.ok, JSON.stringify(body)).toBe(true);
  }

  const devLogin = await request.post("/api/dev/login", { data: DEV_USER });
  if (!devLogin.ok()) {
    throw new Error(`Dev setup login failed: ${await devLogin.text()}`);
  }
  const devBody = await devLogin.json();
  expect(devBody.ok, JSON.stringify(devBody)).toBe(true);

  await request.storageState({ path: "e2e/.auth/user.json" });
});
