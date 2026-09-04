# Sync PUBLIC_TUNNEL_URL, EXOTEL_WEBHOOK_BASE_URL, CLIENT_URL, web/.env.local
# from cloudflared/config.yml or explicit parameters.

param(
    [string]$ApiUrl,
    [string]$AppUrl
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$WebEnvFile = Join-Path $RepoRoot "web\.env.local"
$CfConfig = Join-Path $RepoRoot "cloudflared\config.yml"

function Read-CloudflaredHosts {
    if (-not (Test-Path $CfConfig)) { return $null }
    $text = Get-Content $CfConfig -Raw
    $apiHost = $null
    $appHost = $null
    if ($text -match "hostname:\s*(\S+)\s*\r?\n\s*service:\s*http://127\.0\.0\.1:8000") {
        $apiHost = $Matches[1]
    }
    if ($text -match "hostname:\s*(\S+)\s*\r?\n\s*service:\s*http://127\.0\.0\.1:3000") {
        $appHost = $Matches[1]
    }
    if ($apiHost -and $appHost) {
        return @{
            ApiUrl = "https://$apiHost"
            AppUrl = "https://$appHost"
        }
    }
    return $null
}

if (-not $ApiUrl -or -not $AppUrl) {
    $hosts = Read-CloudflaredHosts
    if ($hosts) {
        if (-not $ApiUrl) { $ApiUrl = $hosts.ApiUrl }
        if (-not $AppUrl) { $AppUrl = $hosts.AppUrl }
    }
}

if (-not $ApiUrl) {
    Write-Warning "env_sync: no API URL - skipping .env update"
    return
}

if (-not $AppUrl) {
    $AppUrl = "http://localhost:3000"
}

function Set-EnvKey {
    param([string[]]$Lines, [string]$Key, [string]$Value)
    $found = $false
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match "^$Key=") {
            $Lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $Lines += "$Key=$Value" }
    return $Lines
}

if (Test-Path $EnvFile) {
    $lines = @(Get-Content $EnvFile)
    $lines = Set-EnvKey $lines "PUBLIC_TUNNEL_URL" $ApiUrl
    $lines = Set-EnvKey $lines "EXOTEL_WEBHOOK_BASE_URL" $ApiUrl
    $lines = Set-EnvKey $lines "CLIENT_URL" $AppUrl
    $lines = Set-EnvKey $lines "PUBLIC_APP_URL" $AppUrl
    Set-Content -Path $EnvFile -Value $lines
    Write-Host "Synced .env -> API $ApiUrl | App $AppUrl"
}

$webLines = @(
    "# Auto-synced by scripts/env_sync.ps1",
    "# Browser on localhost uses NEXT_PUBLIC_API_URL_LOCAL for /ws/* (see web/lib/api.ts)",
    "NEXT_PUBLIC_API_URL=$ApiUrl",
    "NEXT_PUBLIC_API_URL_LOCAL=http://127.0.0.1:8000",
    "API_INTERNAL_URL=http://127.0.0.1:8000"
)
Set-Content -Path $WebEnvFile -Value ($webLines -join "`n")
Write-Host "Synced web/.env.local -> $ApiUrl"

$secretsPath = Join-Path $RepoRoot "data\dev_secrets.json"
if (Test-Path $secretsPath) {
    try {
        $secrets = Get-Content $secretsPath -Raw | ConvertFrom-Json
        $secrets.exotel_webhook_base_url = $ApiUrl
        $secrets | ConvertTo-Json -Depth 20 | Set-Content -Path $secretsPath -Encoding utf8
        Write-Host "Synced data/dev_secrets.json exotel_webhook_base_url -> $ApiUrl"
    } catch {
        Write-Warning "env_sync: could not update dev_secrets.json: $_"
    }
}

return @{ ApiUrl = $ApiUrl; AppUrl = $AppUrl }
