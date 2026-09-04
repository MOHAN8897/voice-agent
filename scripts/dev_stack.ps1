# Unified dev stack - API + Web + Cloudflare tunnel (one command)
#
# Usage:
#   npm run dev              # local + auto tunnel when Exotel / named CF config exists
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
    [ValidateSet("auto", "local", "telephony", "share")]
    [string]$Mode = "auto",
    [switch]$Open,
    [switch]$KillStale
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$CfConfig = Join-Path $RepoRoot "cloudflared\config.yml"
$LogDir = Join-Path $RepoRoot "data\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-EnvFlag {
    param([string]$Key)
    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) { return $false }
    foreach ($line in Get-Content $envFile) {
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
    if ($Mode -in @("telephony", "share")) { return $true }
    # auto
    if (Test-NamedTunnelConfig) { return $true }
    if (Test-EnvFlag "ENABLE_EXOTEL") { return $true }
    return $false
}

function Start-DevWindow {
    param([string]$Title, [string]$WorkingDir, [string]$Command, [string]$LogFile)
    $inner = @"
Set-Location '$WorkingDir'
`$Host.UI.RawUI.WindowTitle = '$Title'
`$log = '$LogFile'
& { $Command } *>&1 | Tee-Object -FilePath `$log
"@
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $inner) | Out-Null
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 5)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500
    } catch { return $false }
}

function Wait-ForService {
    param([string]$Label, [string]$Url, [int]$MaxAttempts = 90)
    Write-Host "Waiting for $Label ($Url)..."
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        if (Test-HttpOk $Url) {
            Write-Host "$Label is ready."
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Warning "$Label did not respond at $Url"
    return $false
}

function Stop-Cloudflared {
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Stopping cloudflared PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

# --- Step 1: clean slate ---
    Write-Host "Stopping stale servers and tunnels..."
    & (Join-Path $PSScriptRoot "dev_down.ps1")

# --- Step 2: sync env URLs from named tunnel config ---
$synced = $null
if (Test-NamedTunnelConfig) {
    $synced = & (Join-Path $PSScriptRoot "env_sync.ps1")
}

# --- Step 3: start API + web ---
$productionWeb = $Mode -in @("share", "telephony")
if ($Open) {
    & (Join-Path $PSScriptRoot "dev_up.ps1") -Wait -Open -ProductionWeb:$productionWeb
} else {
    & (Join-Path $PSScriptRoot "dev_up.ps1") -Wait -ProductionWeb:$productionWeb
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
            $tunnelCmd = "& '$cf' tunnel --config '$CfConfig' run voice-agent-dev"
            Start-DevWindow -Title "Cloudflare Tunnel" -WorkingDir $RepoRoot `
                -Command $tunnelCmd `
                -LogFile (Join-Path $LogDir "cloudflared-named.log")
            $tunnelStarted = $true
            if ($publicApi) {
                Wait-ForService -Label "Public API" -Url "$publicApi/api/health" -MaxAttempts 45 | Out-Null
            }
            if ($publicApp) {
                Wait-ForService -Label "Public App" -Url "$publicApp/dev/login" -MaxAttempts 45 | Out-Null
            }
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
Write-Host "  Local website     http://localhost:3000/dev/login  (dev / devpass)"
Write-Host "  Local API         http://127.0.0.1:8000/api/health"
Write-Host "  Test Studio       http://localhost:3000/dev/test-studio"
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
if ($Mode -eq "share" -and $publicApp) {
    Write-Host ""
    Write-Host "  >>> COPY THIS LINK: $publicApp/dev/test-studio"
}
Write-Host ""
Write-Host "  Stop everything: npm run dev:down"
Write-Host "============================================================"
Write-Host ""

if ($Mode -eq "share" -and -not $tunnelStarted) {
    Write-Warning "Share mode needs a tunnel - install cloudflared or run setup_cloudflare_tunnel.ps1"
    exit 1
}
