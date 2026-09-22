# Merge OAuth client JSON from Google Cloud Console (Credentials -> Download JSON)
# Save as: data/google-oauth-client.json
# Then: powershell -ExecutionPolicy Bypass -File scripts/import-google-oauth-json.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$JsonPath = Join-Path $RepoRoot "data\google-oauth-client.json"
$EnvFile = Join-Path $RepoRoot ".env"
$VoxlyEnv = Join-Path $RepoRoot "voxly-ai\.env"

if (-not (Test-Path $JsonPath)) {
    Write-Error "Missing $JsonPath — create a Web OAuth client in Cloud Console and download JSON."
}

$raw = Get-Content $JsonPath -Raw | ConvertFrom-Json
$web = $raw.web
if (-not $web) { Write-Error "JSON must contain a 'web' section (Web application client)." }

$clientId = $web.client_id
$secret = $web.client_secret
if (-not $clientId -or -not $secret) { Write-Error "client_id and client_secret required in JSON." }

function Set-EnvKey($path, $key, $value) {
    $lines = @()
    $seen = $false
    if (Test-Path $path) {
        foreach ($line in Get-Content $path) {
            if ($line -match "^$key=") {
                $lines += "$key=$value"
                $seen = $true
            } else {
                $lines += $line
            }
        }
    }
    if (-not $seen) { $lines += "$key=$value" }
    $lines | Set-Content -Path $path -Encoding utf8
}

Set-EnvKey $EnvFile "GOOGLE_OAUTH_CLIENT_ID" $clientId
Set-EnvKey $EnvFile "GOOGLE_OAUTH_CLIENT_SECRET" $secret
Set-EnvKey $EnvFile "GOOGLE_OAUTH_REDIRECT_URI" "http://localhost:5173/api/auth/google/callback"
Set-EnvKey $EnvFile "SAAS_AUTH_ENABLED" "true"
Set-EnvKey $VoxlyEnv "VITE_GOOGLE_CLIENT_ID" $clientId

Write-Host "Imported Google OAuth client into .env and voxly-ai/.env. Restart the API."
