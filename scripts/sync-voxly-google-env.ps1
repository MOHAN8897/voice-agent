# Copy GOOGLE_OAUTH_CLIENT_ID from root .env to voxly-ai/.env as VITE_GOOGLE_CLIENT_ID
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$voxlyEnv = Join-Path $root "voxly-ai\.env"
if (-not (Test-Path $envFile)) { exit 0 }
$cid = $null
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^GOOGLE_OAUTH_CLIENT_ID=(.+)$') { $cid = $matches[1].Trim() }
}
if (-not $cid) { Write-Host "No GOOGLE_OAUTH_CLIENT_ID in .env"; exit 0 }
$lines = @()
if (Test-Path $voxlyEnv) {
  $lines = Get-Content $voxlyEnv | Where-Object { $_ -notmatch '^VITE_GOOGLE_CLIENT_ID=' }
}
$lines += "VITE_GOOGLE_CLIENT_ID=$cid"
$lines | Set-Content $voxlyEnv -Encoding utf8
Write-Host "Wrote VITE_GOOGLE_CLIENT_ID to voxly-ai/.env"
