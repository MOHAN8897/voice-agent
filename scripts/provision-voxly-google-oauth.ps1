# Provision Google OAuth for Voxly + merge SaaS auth keys into root .env
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/provision-voxly-google-oauth.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/provision-voxly-google-oauth.ps1 -ProjectId gen-lang-client-0799442928 -OpenConsole

param(
    [string]$ProjectId = "gen-lang-client-0799442928",
    [string]$ClientId = "",
    [string]$ClientSecret = "",
    [switch]$OpenConsole,
    [switch]$SkipGcloud,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$Example = Join-Path $RepoRoot "saas-workflow\ENV-SaaS.example"

$VoxlyOrigin = "http://localhost:5173"
$RedirectUri = "$VoxlyOrigin/api/auth/google/callback"

function Ensure-EnvLine {
    param([hashtable]$Lines, [string]$Key, [string]$Value)
    if (-not $Lines.ContainsKey($Key)) {
        $Lines[$Key] = $Value
    }
}

if (-not $SkipGcloud) {
    $gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($gcloud) {
        Write-Host "Setting gcloud project to $ProjectId ..."
        & gcloud config set project $ProjectId | Out-Null
        Write-Host "Enabling APIs ..."
        & gcloud services enable iamcredentials.googleapis.com cloudresourcemanager.googleapis.com --project=$ProjectId --quiet
    } else {
        Write-Warning "gcloud not found; run scripts/setup-google-cloud.ps1 first."
    }
}

$consoleUrl = "https://console.cloud.google.com/auth/clients/create?project=$ProjectId"
Write-Host @"

=== Voxly Google OAuth (Web client) ===
Project: $ProjectId

In Google Cloud Console create an OAuth client (Web application):

  Authorized JavaScript origins:
    $VoxlyOrigin

  Authorized redirect URIs:
    $RedirectUri

Console link:
  $consoleUrl

Copy Client ID and Client secret into .env (this script can prompt below).

"@

if ($OpenConsole) {
    Start-Process $consoleUrl
}

$lines = @{}
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $lines[$matches[1].Trim()] = $matches[2]
        }
    }
}

$jwt = $lines["JWT_SECRET"]
if (-not $jwt -or $jwt -eq "change-me-long-random-string") {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $jwt = [Convert]::ToBase64String($bytes) -replace '[+/=]', 'a'
    $lines["JWT_SECRET"] = $jwt
    Write-Host "Generated JWT_SECRET."
}

Ensure-EnvLine $lines "SAAS_AUTH_ENABLED" "true"
Ensure-EnvLine $lines "VOXLY_FRONTEND_URL" $VoxlyOrigin
Ensure-EnvLine $lines "GOOGLE_OAUTH_REDIRECT_URI" $RedirectUri
Ensure-EnvLine $lines "CORS_ORIGINS" "$VoxlyOrigin,http://localhost:3000"

if ($ClientId) { $lines["GOOGLE_OAUTH_CLIENT_ID"] = $ClientId.Trim() }
if ($ClientSecret) { $lines["GOOGLE_OAUTH_CLIENT_SECRET"] = $ClientSecret.Trim() }
if (-not $NonInteractive -and -not $lines["GOOGLE_OAUTH_CLIENT_ID"]) {
    $cid = Read-Host "GOOGLE_OAUTH_CLIENT_ID (or Enter to skip)"
    if ($cid) { $lines["GOOGLE_OAUTH_CLIENT_ID"] = $cid.Trim() }
}
if (-not $NonInteractive -and -not $lines["GOOGLE_OAUTH_CLIENT_SECRET"]) {
    $sec = Read-Host "GOOGLE_OAUTH_CLIENT_SECRET (or Enter to skip)" -AsSecureString
    if ($sec) {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        if ($plain) { $lines["GOOGLE_OAUTH_CLIENT_SECRET"] = $plain.Trim() }
    }
}

$out = New-Object System.Collections.Generic.List[string]
if (Test-Path $EnvFile) {
    $seen = @{}
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $k = $matches[1].Trim()
            if ($lines.ContainsKey($k)) {
                $out.Add("$k=$($lines[$k])")
                $seen[$k] = $true
            } else {
                $out.Add($_)
            }
        } else {
            $out.Add($_)
        }
    }
    foreach ($k in $lines.Keys) {
        if (-not $seen[$k]) {
            $out.Add("$k=$($lines[$k])")
        }
    }
} else {
    foreach ($k in ($lines.Keys | Sort-Object)) {
        $out.Add("$k=$($lines[$k])")
    }
}

$out | Set-Content -Path $EnvFile -Encoding utf8
Write-Host "Updated $EnvFile (SAAS_AUTH_ENABLED, redirect URI, CORS)."

# Mirror Resend keys (backend accepts RESEND_API_KEY or resend_api_key)
if ($lines["resend_api_key"] -and -not $lines["RESEND_API_KEY"]) {
    Set-EnvKey $lines "RESEND_API_KEY" $lines["resend_api_key"]
    ($out) | Set-Content -Path $EnvFile -Encoding utf8
}
if ($lines["resend_from_email"] -and -not $lines["RESEND_FROM_EMAIL"]) {
    Set-EnvKey $lines "RESEND_FROM_EMAIL" $lines["resend_from_email"]
}

$importScript = Join-Path $PSScriptRoot "import-google-oauth-json.ps1"
$jsonPath = Join-Path $RepoRoot "data\google-oauth-client.json"
if (Test-Path $jsonPath) {
    Write-Host "Found data/google-oauth-client.json - importing..."
    & $importScript
} else {
    Write-Host "No data/google-oauth-client.json yet. After creating a Web client in Console, download JSON and run:"
    Write-Host "  powershell -File scripts/import-google-oauth-json.ps1"
}

Write-Host "Restart API after changing credentials."

$voxlyEnv = Join-Path $RepoRoot "voxly-ai\.env"
if ($lines["GOOGLE_OAUTH_CLIENT_ID"]) {
    $viteLine = "VITE_GOOGLE_CLIENT_ID=$($lines['GOOGLE_OAUTH_CLIENT_ID'])"
    if (Test-Path $voxlyEnv) {
        $ve = Get-Content $voxlyEnv | Where-Object { $_ -notmatch '^VITE_GOOGLE_CLIENT_ID=' }
        ($ve + $viteLine) | Set-Content $voxlyEnv -Encoding utf8
    } else {
        Set-Content -Path $voxlyEnv -Value $viteLine -Encoding utf8
    }
    Write-Host "Synced VITE_GOOGLE_CLIENT_ID to voxly-ai/.env"
}

Write-Host @"

Optional: same Client ID in voxly-ai/.env for GIS One Tap (auto-synced when you set GOOGLE_OAUTH_CLIENT_ID):
  VITE_GOOGLE_CLIENT_ID=<same as GOOGLE_OAUTH_CLIENT_ID>

Verify:
  curl http://localhost:8000/api/auth/google/config
  curl -I http://localhost:8000/api/auth/google/start

"@
