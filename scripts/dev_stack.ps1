# Unified dev stack - API + Web + Cloudflare tunnel (one command)
#
# Usage:
#   npm run dev              # Voxly + API + named Cloudflare tunnel (PSTN)
#   npm run dev:open         # same + open browser
#   npm run share            # full stack + print friend share link
#   npm run dev:down         # stop everything including tunnel
#
# Modes:
#   auto      - tunnel if ENABLE_EXOTEL=true or cloudflared/config.yml exists
#   local     - API + web only (no tunnel)
#   telephony - API + web + named/quick API tunnel (Exotel PSTN)
#   share     - API + web + tunnel + public app link for friends

param(
    [ValidateSet("auto", "local", "voxly", "telephony", "share")]
    [string]$Mode = "voxly",
    [switch]$Open,
    [switch]$KillStale
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev_common.ps1")
$RepoRoot = Split-Path -Parent $PSScriptRoot
$CfConfig = Join-Path $RepoRoot "cloudflared\config.yml"
$LogDir = Join-Path $RepoRoot "data\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-EnvFlag {
    param([string]$Key)
    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) { return $false }
    $lines = @()
    try {
        $lines = Get-Content -Path $envFile -Encoding UTF8 -ErrorAction Stop
    } catch {
        $lines = Get-Content -Path $envFile -ErrorAction SilentlyContinue
    }
    foreach ($line in $lines) {
        if ($line -match "^$Key=(.+)$") {
            return $Matches[1].Trim() -match "^(?i)(true|1|yes)$"
        }
    }
    return $false
}

function Test-NamedTunnelConfig {
    return (Test-Path $CfConfig)
}

function Should-StartTunnel {
    if ($Mode -eq "local") { return $false }
    if ($Mode -in @("telephony", "share", "voxly")) {
        return Test-NamedTunnelConfig
    }
    # auto: tunnel only when explicitly enabled (avoids heavy CF + public URL sync on every dev)
    if (Test-EnvFlag "DEV_ENABLE_TUNNEL") {
        if (Test-NamedTunnelConfig) { return $true }
        if (Test-EnvFlag "ENABLE_EXOTEL") { return $true }
    }
    return $false
}

function Should-SyncRemoteEnv {
    if ($Mode -eq "local") { return $false }
    if ($Mode -in @("telephony", "share")) { return $true }
    if ($Mode -eq "voxly" -and (Test-NamedTunnelConfig)) { return $true }
    return Test-EnvFlag "DEV_ENABLE_TUNNEL"
}

# --- Step 1: clean slate ---
# A quick share tunnel must expose the website (including its API/WS proxy).
if ($Mode -eq "share" -and -not (Test-NamedTunnelConfig)) {
    & (Join-Path $PSScriptRoot "share_with_friend.ps1") -Tunnel cloudflared
    exit $LASTEXITCODE
}
Write-Host "Stopping stale servers and tunnels..."
if (-not (Stop-VoiceAgentDevStack)) {
    Write-Error "Could not free dev ports. Close leftover Voice Agent windows and retry."
}

# --- Step 2: sync env URLs from named tunnel config (optional; off in voxly/local mode) ---
$synced = $null
if (Should-SyncRemoteEnv -and (Test-NamedTunnelConfig)) {
    $synced = & (Join-Path $PSScriptRoot "env_sync.ps1")
}

# --- Step 3: start API + web ---
$productionWeb = $Mode -in @("share", "telephony")
$voxlyFocus = $Mode -eq "voxly"
if ($Open) {
    & (Join-Path $PSScriptRoot "dev_up.ps1") -Wait -Open -ProductionWeb:$productionWeb -VoxlyFocus:$voxlyFocus
} else {
    & (Join-Path $PSScriptRoot "dev_up.ps1") -Wait -ProductionWeb:$productionWeb -VoxlyFocus:$voxlyFocus
}
if ($LASTEXITCODE -ne 0) {
    throw "Local stack failed to start. See data/dev-logs/api.log and web.log."
}

# PSTN webhooks need a live local origin before Cloudflare can proxy them.
if (Should-StartTunnel) {
    if (-not (Test-HttpOk "http://127.0.0.1:8000/api/health" 3)) {
        Write-Error "Local API is not healthy after start. Check data\dev-logs\api.log - refusing to start tunnel."
    }
}

# --- Step 4: tunnel ---
$tunnelStarted = $false
$publicApi = $synced.ApiUrl
$publicApp = $synced.AppUrl

if (Should-StartTunnel) {
    if (Test-NamedTunnelConfig) {
        Write-Host "Starting named Cloudflare tunnel (api-dev + app-dev)..."
        $cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
        if (-not $cf) {
            Write-Warning "cloudflared not installed - PSTN webhooks will not work. winget install Cloudflare.cloudflared"
        } else {
            $tunnelCmd = "& '$cf' tunnel --config '$CfConfig' run"
            Start-DevWindow -Title "Cloudflare Tunnel" -WorkingDir $RepoRoot `
                -Command $tunnelCmd `
                -LogFile (Join-Path $LogDir "cloudflared-named.log")
            if ($publicApi) {
                if (-not (Wait-ForService -Label "Public API" -Url "$publicApi/api/health" -MaxAttempts 45)) {
                    throw "Public API tunnel is not healthy. See data/dev-logs/cloudflared-named.log."
                }
            }
            if ($publicApp) {
                if (-not (Wait-ForService -Label "Public App" -Url "$publicApp/dev/login" -MaxAttempts 45)) {
                    throw "Public website tunnel is not healthy. See data/dev-logs/cloudflared-named.log."
                }
                if (-not (Wait-ForService -Label "Public App API proxy" -Url "$publicApp/api/health" -MaxAttempts 45)) {
                    throw "Public website API proxy is not healthy."
                }
            }
            if ($Mode -eq "share" -and (-not $publicApi -or -not $publicApp)) {
                throw "Named tunnel config must include API (8000) and website (3000) ingress hosts."
            }
            $tunnelStarted = $true
        }
    } else {
        Write-Host "No named tunnel config - starting quick API tunnel for Exotel..."
        & (Join-Path $PSScriptRoot "tunnel_cloudflared.ps1")
        if (Test-Path (Join-Path $RepoRoot ".tunnel-url")) {
            $publicApi = (Get-Content (Join-Path $RepoRoot ".tunnel-url") -Raw).Trim()
            $tunnelStarted = $true
        }
    }
}

# --- Banner ---
Write-Host ""
Write-Host "============================================================"
Write-Host "  Voice agent stack"
Write-Host "============================================================"
Write-Host ""
if ($Mode -eq "voxly") {
    Write-Host "  Voxly (product UI)  http://127.0.0.1:5173"
    Write-Host "  Dev portal          http://localhost:3000/dev/login  (DEV_PORTAL_USERNAME / DEV_PORTAL_PASSWORD in .env)"
    Write-Host "  Test Studio         http://localhost:3000/dev/test-studio"
    Write-Host "  API                 http://127.0.0.1:8000/api/health"
    Write-Host ""
    Write-Host '  Marketing and /app console redirect to Voxly.'
    if ($tunnelStarted) {
        Write-Host '  Cloudflare tunnel is up for Telnyx/PSTN media (api-dev.hustlelabs.in).'
    } else {
        Write-Host '  PSTN tunnel did not start. Install cloudflared and run scripts/setup_cloudflare_tunnel.ps1'
    }
} else {
    Write-Host "  Local website     http://localhost:3000/dev/login  (DEV_PORTAL_* in .env)"
    Write-Host "  Local API         http://127.0.0.1:8000/api/health"
    Write-Host "  Test Studio       http://localhost:3000/dev/test-studio"
}
if ($tunnelStarted -and $publicApi) {
    Write-Host ""
    Write-Host "  Public API        $publicApi"
    Write-Host "  Exotel webhooks   $publicApi/api/exotel/status-callback"
    Write-Host "  Exotel WSS        wss://$($publicApi -replace '^https?://','')/ws/exotel-stream"
}
if ($tunnelStarted -and $publicApp -and $publicApp -notmatch "localhost") {
    Write-Host ""
    Write-Host "  Public website    $publicApp"
    if ($productionWeb) {
        Write-Host "  Dev portal (public) $publicApp/dev/login"
    } else {
        Write-Host "  Dev portal (public) use localhost:3000/dev/login (dev bundles too large for tunnel)"
    }
    Write-Host "  Share with friend $publicApp/dev/test-studio"
}
if ($Mode -eq "share" -and $tunnelStarted -and $publicApp) {
    Write-Host ""
    Write-Host "  COPY THIS LINK: $publicApp/dev/test-studio"
}
Write-Host ""
Write-Host "  Stop everything: npm run dev:down"
Write-Host "============================================================"
Write-Host ""

if ($Mode -eq "share" -and -not $tunnelStarted) {
    Write-Warning "Share mode needs a tunnel - install cloudflared or run setup_cloudflare_tunnel.ps1"
    exit 1
}
