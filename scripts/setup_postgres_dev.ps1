# Bootstrap local PostgreSQL for voice-agent development (Windows).
# Requires PostgreSQL service running (e.g. postgresql-x64-18).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $env:POSTGRES_ADMIN_PASSWORD) {
    $secure = Read-Host "PostgreSQL admin password (postgres user)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $env:POSTGRES_ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
}

python scripts/setup_postgres_dev.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Optional: start Redis via Docker Desktop when available:"
Write-Host "  docker compose up -d redis"
