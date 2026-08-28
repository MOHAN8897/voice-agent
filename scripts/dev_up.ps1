# Start API + Next.js for local dev (Windows PowerShell)
# Usage (from repo root):
#   npm run dev
#   powershell -ExecutionPolicy Bypass -File scripts/dev_up.ps1
# Options:
#   -KillStale    Stop processes on ports 8000 and 3000 before starting
#   -Wait         Wait until API and web respond before printing links
#   -Open         Open the dev portal in your default browser
#   -ApiOnly      Start API only
#   -WebOnly      Start Next.js only

param(
    [switch]$KillStale,
    [switch]$Wait,
    [switch]$Open,
    [switch]$ApiOnly,
    [switch]$WebOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "web"
$LogDir = Join-Path $RepoRoot "data\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")

$WebUrl = "http://localhost:3000"
$ApiUrl = "http://127.0.0.1:8000"
$DevLoginUrl = "$WebUrl/dev/login"
$TestStudioUrl = "$WebUrl/dev/test-studio"
$AppLoginUrl = "$WebUrl/app/login"
$MarketingUrl = "$WebUrl/"

function Stop-Port {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        if ($procId -and $procId -ne 0) {
            Write-Host "Stopping PID $procId on port $Port"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-ForService {
    param(
        [string]$Label,
        [string]$Url,
        [int]$MaxAttempts = 90
    )
    Write-Host "Waiting for $Label..."
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        if (Test-HttpOk $Url) {
            Write-Host "$Label is ready."
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Warning "$Label did not respond at $Url."
    return $false
}

function Write-DevBanner {
    param(
        [bool]$ApiOk,
        [bool]$WebOk
    )
    Write-Host ""
    Write-Host "============================================================"
    if ($ApiOk -and $WebOk) {
        Write-Host "  Voice agent - local dev is running"
    } else {
        Write-Host "  Voice agent - dev start incomplete"
    }
    Write-Host "============================================================"
    Write-Host ""
    if ($WebOk) {
        Write-Host "  Website (marketing)   $MarketingUrl"
        Write-Host "  Dev portal (login)    $DevLoginUrl"
        Write-Host "    credentials: dev / devpass"
        Write-Host "  Test Studio           $TestStudioUrl"
        Write-Host "  Business app login    $AppLoginUrl"
        Write-Host "    credentials: e2e / e2e-test"
    } else {
        Write-Host "  Website               NOT RUNNING"
        Write-Host "  Check the 'Voice Agent Web' window or: $LogDir\web.log"
    }
    Write-Host ""
    if ($ApiOk) {
        Write-Host "  API health            $ApiUrl/api/health"
    } else {
        Write-Host "  API                   NOT RUNNING"
        Write-Host "  Check the 'Voice Agent API' window or: $LogDir\api.log"
    }
    Write-Host ""
    Write-Host "  Stop servers: npm run dev:down"
    Write-Host "============================================================"
    Write-Host ""
}

function Start-DevWindow {
    param(
        [string]$Title,
        [string]$WorkingDir,
        [string]$Command,
        [string]$LogFile
    )
    $inner = @"
Set-Location '$WorkingDir'
`$Host.UI.RawUI.WindowTitle = '$Title'
`$log = '$LogFile'
& { $Command } *>&1 | Tee-Object -FilePath `$log
"@
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $inner) | Out-Null
}

$python = (Get-Command python -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) {
    $npm = (Get-Command npm -ErrorAction Stop).Source
}

if ($KillStale) {
    Write-Host "Clearing ports 8000 and 3000-3003..."
    & (Join-Path $PSScriptRoot "dev_down.ps1")
}

if (-not $WebOnly) {
    Write-Host "Starting API on $ApiUrl"
    Start-DevWindow -Title "Voice Agent API" -WorkingDir $RepoRoot `
        -Command "& '$python' -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload" `
        -LogFile (Join-Path $LogDir "api.log")
}

if (-not $ApiOnly) {
    if (-not (Test-Path $WebRoot)) {
        Write-Error "Web folder not found: $WebRoot"
    }
    if (-not (Test-Path (Join-Path $WebRoot "node_modules"))) {
        Write-Host "Installing web dependencies (first run)..."
        Push-Location $WebRoot
        & $npm install
        Pop-Location
    }
    Write-Host "Starting Next.js on $WebUrl"
    Start-DevWindow -Title "Voice Agent Web" -WorkingDir $WebRoot `
        -Command "& '$npm' run dev -- -p 3000" `
        -LogFile (Join-Path $LogDir "web.log")
}

$apiOk = $false
$webOk = $false

if ($Wait -or $Open) {
    if (-not $WebOnly) {
        $apiOk = Wait-ForService -Label "API" -Url "$ApiUrl/api/health"
    } else {
        $apiOk = $true
    }
    if (-not $ApiOnly) {
        $webOk = Wait-ForService -Label "Website" -Url $DevLoginUrl
    } else {
        $webOk = $true
    }
} else {
    $apiOk = -not $WebOnly
    $webOk = -not $ApiOnly
}

Write-DevBanner -ApiOk $apiOk -WebOk $webOk

if ($Open -and $webOk) {
    Write-Host "Opening dev portal in browser..."
    Start-Process $DevLoginUrl
}

if (-not $apiOk -or -not $webOk) {
    exit 1
}
