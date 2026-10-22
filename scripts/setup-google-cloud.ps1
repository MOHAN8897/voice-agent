# Google Cloud CLI bootstrap for Voxly (run in elevated shell if winget prompts).
$ErrorActionPreference = "Stop"

function Ensure-Gcloud {
    $gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
    if (-not $gcloud) {
        Write-Host "Installing Google Cloud SDK via winget..."
        winget install Google.CloudSDK --accept-package-agreements --accept-source-agreements
        Write-Host "Re-open PowerShell after install, then run this script again."
        exit 0
    }
    & gcloud version
}

Ensure-Gcloud

Write-Host "`nSign in (browser)..."
& gcloud auth login

Write-Host "`nApplication Default Credentials (for MCP / local tools)..."
& gcloud auth application-default login

$project = Read-Host "GCP project ID to set as default (or Enter to skip)"
if ($project) {
    & gcloud config set project $project
    Write-Host "Enabling common APIs..."
    & gcloud services enable iamcredentials.googleapis.com --quiet
}

Write-Host @"

Next steps (manual in Cloud Console):
  1. APIs & Services -> OAuth consent screen (External, add test users if needed)
  2. Credentials -> Create OAuth client -> Web application
     - JS origin: http://localhost:5173
     - Redirect:  http://localhost:5173/api/auth/google/callback
  3. Run: scripts/provision-voxly-google-oauth.ps1 (merges SAAS_AUTH_ENABLED, JWT_SECRET, redirect URI into .env)
  4. Cursor MCP: see saas-workflow/GOOGLE-CLOUD-SETUP.md

"@
