import { test as setup } from "@playwright/test";
import { E2E_USER } from "./helpers";

setup("authenticate", async ({ request }) => {
  const session = await request.get("/api/auth/session");
  const { app_configured } = await session.json();
  if (!app_configured) return;

  const login = await request.post("/api/app/login", { data: E2E_USER });
  if (!login.ok()) {
    throw new Error(`E2E setup login failed: ${await login.text()}`);
  }

  await request.storageState({ path: "e2e/.auth/user.json" });
});
