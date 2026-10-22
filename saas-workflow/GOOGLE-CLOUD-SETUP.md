# Google Cloud — sign-in + Cursor MCP

## 1. Install Google Cloud CLI (Windows)

```powershell
winget install Google.CloudSDK --accept-package-agreements
```

After install, **open a new terminal** (PATH updates), then:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Enable APIs used by Voxly Google sign-in:

```powershell
gcloud services enable iamcredentials.googleapis.com
```

OAuth consent screen + Web client (for **Voxly website login**) — [Google Auth Platform → Clients](https://console.cloud.google.com/apis/credentials):

| Field | Local dev value |
|--------|------------------|
| Application type | Web application |
| Authorized JavaScript origins | `http://localhost:5173` |
| Authorized redirect URIs | `http://localhost:5173/api/auth/google/callback` (Vite → API proxy; keeps refresh cookie on :5173) |

**CLI note:** `gcloud iam oauth-clients` creates **Workforce/IAM** clients (not the same as Auth Platform “Web application” clients for Google Sign-In). For Voxly login you need a **Web application** client from [Auth Platform → Clients](https://console.cloud.google.com/auth/clients).

Fastest automation after creating the client in Console:

1. Download the client JSON from Credentials.
2. Save as `data/google-oauth-client.json` (see `data/google-oauth-client.json.example`).
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import-google-oauth-json.ps1
powershell -ExecutionPolicy Bypass -File scripts/provision-voxly-google-oauth.ps1 -NonInteractive -SkipGcloud
```

Or bootstrap + open Console wizard:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/provision-voxly-google-oauth.ps1 -OpenConsole
```

Copy **Client ID** and **Client secret** into root `.env`:

```env
GOOGLE_OAUTH_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5173/api/auth/google/callback
VOXLY_FRONTEND_URL=http://localhost:5173
```

Optional Voxly one-tap GIS: same client ID in `voxly-ai/.env` as `VITE_GOOGLE_CLIENT_ID=...`.

**“Sign in to venuefinder” instead of Voxly:** That text comes from the **Google OAuth consent screen App name** in Cloud Console (project `gen-lang-client-0799442928`), not from Voxly code. Run `scripts/open-google-oauth-branding.ps1` and set **App name** to **Voxly AI**.

**“Sign in to venuefinder” instead of Voxly:** That label is set on the **Google OAuth consent screen** (App name) in Cloud Console, not in Voxly code. Run `scripts/open-google-oauth-branding.ps1` and set **App name** to **Voxly AI**.

**Voxly website vs Cursor MCP:** use one **Web** OAuth client for Voxly (`localhost:5173` + redirect above). Cursor’s Cloud MCP needs a **separate** desktop/Web client with redirect `http://localhost:8787/callback` (see `.cursor/mcp.google-cloud.example.json`). Do not reuse the same redirect URI for both.

## 2. Cursor — Google Cloud CLI remote MCP

Docs: [Use the Cloud CLI remote MCP server](https://cloud.google.com/sdk/use-gcloud-mcp)

1. Copy `.cursor/mcp.google-cloud.example.json` → merge into `.cursor/mcp.json` (or use Cursor **MCP: Add Server** → HTTP → `https://cloudcli.googleapis.com/mcp`).
2. For **Cursor desktop**, create a separate OAuth client with redirect `http://localhost:8787/callback` (see [Configure MCP in an AI application](https://cloud.google.com/mcp/configure-mcp-ai-application)).
3. On first use, Cursor prompts for OAuth client ID/secret and scope `https://www.googleapis.com/auth/cloud-platform`.

**ADC alternative** (token expires ~1h): after `gcloud auth application-default login`, you can pass headers documented in Google’s MCP auth guide (`Authorization: Bearer …`, `x-goog-user-project: PROJECT_ID`).

## 3. Verify backend

```powershell
curl http://localhost:8000/api/auth/session
# saas_auth_enabled should be true when configured

# Google start (should 302 to accounts.google.com when GOOGLE_OAUTH_CLIENT_ID is set)
curl -I http://localhost:8000/api/auth/google/start
```
