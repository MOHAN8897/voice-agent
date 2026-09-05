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
    [switch]$WebOnly,
    [switch]$ProductionWeb
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev_common.ps1")

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

$python = (Get-Command python -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) {
    $npm = (Get-Command npm -ErrorAction Stop).Source
}

if ($KillStale) {
    Write-Host "Clearing ports 8000 and 3000-3003..."
    $downOk = Stop-VoiceAgentDevStack
    if (-not $downOk) {
        Write-Error "Could not free dev ports. Close leftover Voice Agent windows and retry."
    }
}

$apiOk = $false
$webOk = $false

if (-not $WebOnly) {
    Write-Host "Starting API on $ApiUrl"
    Start-DevWindow -Title "Voice Agent API" -WorkingDir $RepoRoot `
        -Command (Get-UvicornDevCommand -PythonPath $python) `
        -LogFile (Join-Path $LogDir "api.log")
    $apiOk = Wait-ForService -Label "API" -Url "$ApiUrl/api/health"
    if (-not $apiOk) {
        Write-Warning "API did not become healthy. Check $LogDir\api.log"
        if (-not $ApiOnly) {
            Write-Warning "Not starting the website until the API is up (avoids Next.js ECONNRESET)."
        }
    }
} else {
    $apiOk = $true
}

if (-not $ApiOnly) {
    if (-not (Test-Path $WebRoot)) {
        Write-Error "Web folder not found: $WebRoot"
    }
    if ($apiOk -or $WebOnly) {
        if (-not (Test-Path (Join-Path $WebRoot "node_modules"))) {
            Write-Host "Installing web dependencies (first run)..."
            Push-Location $WebRoot
            & $npm install
            Pop-Location
        }
        if ($ProductionWeb) {
            $buildId = Join-Path $WebRoot ".next\BUILD_ID"
            if (-not (Test-Path $buildId)) {
                Write-Host "Building Next.js production bundle (required for public tunnel)..."
                Push-Location $WebRoot
                & $npm run build
                if ($LASTEXITCODE -ne 0) {
                    Pop-Location
                    Write-Error "Next.js production build failed"
                }
                Pop-Location
            }
            Write-Host "Starting Next.js production server on $WebUrl"
            Start-DevWindow -Title "Voice Agent Web" -WorkingDir $WebRoot `
                -Command "& '$npm' run start -- -p 3000" `
                -LogFile (Join-Path $LogDir "web.log")
        } else {
            Write-Host "Starting Next.js on $WebUrl"
            Start-DevWindow -Title "Voice Agent Web" -WorkingDir $WebRoot `
                -Command "& '$npm' run dev -- -p 3000" `
                -LogFile (Join-Path $LogDir "web.log")
        }
        $webOk = Wait-ForService -Label "Website" -Url $DevLoginUrl
        if ($webOk) {
            $proxyOk = Wait-ForService -Label "Website API proxy" -Url "$WebUrl/api/health" -MaxAttempts 30
            if (-not $proxyOk) {
                Write-Warning "Website is up but /api/health proxy failed. API may still be starting."
                $webOk = $false
            }
        }
    }
} else {
    $webOk = $true
}

Write-DevBanner -ApiOk $apiOk -WebOk $webOk

if ($Open -and $webOk) {
    Write-Host "Opening dev portal in browser..."
    Start-Process $DevLoginUrl
}

if (-not $apiOk -or -not $webOk) {
    exit 1
}
exit 0
