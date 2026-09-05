# One command: start API + Web + ngrok and print the share link.
# Usage: npm run share

param(
    [ValidateSet("auto", "ngrok", "cloudflared")]
    [string]$Tunnel = "cloudflared"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev_common.ps1")
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "web"
$WebEnvFile = Join-Path $RepoRoot "web\.env.local"
$LogDir = Join-Path $RepoRoot "data\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")

$python = (Get-Command python -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) { $npm = (Get-Command npm -ErrorAction Stop).Source }

function Set-WebEnvSameOriginShare {
    $header = "# Auto-updated by share_with_friend.ps1 (single ngrok tunnel)"
    $out = @($header, "API_INTERNAL_URL=http://127.0.0.1:8000")
    if (Test-Path $WebEnvFile) {
        foreach ($line in Get-Content $WebEnvFile) {
            if ($line -match "^# Auto-updated by") { continue }
            if ($line -match "^NEXT_PUBLIC_API_URL=") { continue }
            if ($line -match "^API_INTERNAL_URL=") { continue }
            if ($line.Trim()) { $out += $line }
        }
    }
    Set-Content -Path $WebEnvFile -Value $out
}

Write-Host "Step 1/5: Clearing old servers..."
if (-not (Stop-VoiceAgentDevStack)) {
    Write-Error "Could not free dev ports. Close leftover Voice Agent windows and retry."
}

Write-Host "Step 2/5: Configuring website for public sharing..."
Set-WebEnvSameOriginShare

Write-Host "Step 3/5: Starting API..."
Start-DevWindow -Title "Voice Agent API" -WorkingDir $RepoRoot `
    -Command (Get-UvicornDevCommand -PythonPath $python) `
    -LogFile (Join-Path $LogDir "api.log")

if (-not (Wait-ForService -Label "API" -Url "http://127.0.0.1:8000/api/health")) {
    Write-Error "API failed to start. Check data\dev-logs\api.log"
}

if (-not (Test-Path (Join-Path $WebRoot "node_modules"))) {
    Write-Host "Installing web dependencies (first run)..."
    Push-Location $WebRoot
    & $npm install
    Pop-Location
}

Write-Host "Step 4/5: Starting website..."
Start-DevWindow -Title "Voice Agent Web" -WorkingDir $WebRoot `
    -Command "& '$npm' run dev -- -p 3000" `
    -LogFile (Join-Path $LogDir "web.log")

if (-not (Wait-ForService -Label "Website" -Url "http://localhost:3000/dev/login")) {
    Write-Error "Website failed to start. Check data\dev-logs\web.log"
}
if (-not (Wait-ForService -Label "Website API proxy" -Url "http://localhost:3000/api/health" -MaxAttempts 30)) {
    Write-Error "Website is up but /api/health proxy failed. Check data\dev-logs\api.log"
}

Write-Host "Step 5/5: Starting public tunnel..."
$shareLink = $null
$tunnelScript = Join-Path $PSScriptRoot "tunnel_ngrok_share.ps1"
$cfScript = Join-Path $PSScriptRoot "tunnel_cloudflared_share.ps1"

if ($Tunnel -eq "cloudflared") {
    $shareLink = & $cfScript
} elseif ($Tunnel -eq "ngrok") {
    $shareLink = & $tunnelScript -SkipHealthCheck
} else {
    try {
        $shareLink = & $tunnelScript -SkipHealthCheck
    } catch {
        Write-Warning "ngrok failed: $($_.Exception.Message)"
        Write-Host "Trying Cloudflare tunnel instead..."
        $shareLink = & $cfScript
    }
}

if (-not $shareLink) {
    Write-Error "Could not start a public tunnel."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  ALL READY - COPY AND SEND THIS LINK"
Write-Host "============================================================"
Write-Host ""
Write-Host "  $shareLink"
Write-Host ""
Write-Host "  Your friend opens this in Chrome/Edge and allows microphone."
Write-Host "  Login if needed: dev / devpass"
Write-Host ""
Write-Host "  Keep this PC on. Stop with: npm run dev:down"
Write-Host "============================================================"
Write-Host ""
