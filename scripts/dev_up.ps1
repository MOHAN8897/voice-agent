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
    [switch]$ProductionWeb,
    [switch]$DialtactFocus,
    # dev_stack.ps1 prints the canonical banner (it knows about the tunnel), so it
    # suppresses this one. Without it the two blocks stack up and look duplicated.
    [switch]$QuietBanner,
    # Retained for compatibility; production mode always builds current sources.
    [switch]$ForceWebBuild
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev_common.ps1")

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "web"
$LogDir = Join-Path $RepoRoot "data\dev-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:Path = $env:Path + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")

$WebUrl = "http://127.0.0.1:3000"
$DialtactUrl = "http://127.0.0.1:5173"
$ApiUrl = "http://127.0.0.1:8000"
$DialtactRoot = Join-Path $RepoRoot "dialtact-app"
$DevLoginUrl = "$WebUrl/dev/login"
$TestStudioUrl = "$WebUrl/dev/test-studio"
$AppLoginUrl = "$WebUrl/app/login"
$MarketingUrl = "$WebUrl/"

function Write-DevBanner {
    param(
        [bool]$ApiOk,
        [bool]$WebOk,
        [bool]$DialtactOk = $false,
        [bool]$DialtactFocus = $false
    )
    Write-Host ""
    Write-Host "============================================================"
    if ($ApiOk -and $WebOk) {
        if ($DialtactFocus) {
            Write-Host "  Dialtact + dev panel (light local stack)"
        } else {
            Write-Host "  Voice agent - local dev is running (API + dev portal + Dialtact)"
        }
    } else {
        Write-Host "  Voice agent - dev start incomplete"
    }
    Write-Host "============================================================"
    Write-Host ""
    if ($WebOk) {
        if ($DialtactOk) {
            Write-Host "  Dialtact (subscriber UI) $DialtactUrl"
        } else {
            Write-Host "  Dialtact                 NOT RUNNING (see dialtact.log)"
        }
        Write-Host "  Dev portal            $DevLoginUrl  (dev / devpass)"
        Write-Host "  Test Studio           $TestStudioUrl"
        if (-not $DialtactFocus) {
            Write-Host "  Legacy marketing      $MarketingUrl  (redirects to Dialtact)"
            Write-Host "  Legacy /app console   $AppLoginUrl  (redirects to Dialtact)"
        }
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
    try {
        $redisOk = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
        if ($redisOk) {
            Write-Host "  Redis Cache           redis://127.0.0.1:6379/0 (ready)"
        }
    } catch { }
    Write-Host ""
    Write-Host "  Stop servers: npm run dev:down"
    Write-Host "============================================================"
    Write-Host ""
}

$python = Get-VoiceAgentPython -RepoRoot $RepoRoot
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
$dialtactOk = $false

if (-not $WebOnly) {
    Ensure-RedisServer | Out-Null
    if (-not (Test-VoiceAgentPythonDeps -PythonPath $python -RepoRoot $RepoRoot)) {
        throw "Install Python dependencies before starting the API (see commands above)."
    }
    Write-Host "Starting API on $ApiUrl"
    # Share/telephony need a stable single worker (PSTN + reliable health waits).
    $apiNoReload = [bool]$ProductionWeb
    if ($apiNoReload) {
        Write-Host "  (stable mode: uvicorn without --reload)"
    }
    Start-DevWindow -Title "Voice Agent API" -WorkingDir $RepoRoot `
        -Command (Get-UvicornDevCommand -PythonPath $python -NoReload:$apiNoReload) `
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
            try {
                & $npm install
                if ($LASTEXITCODE -ne 0) { throw "Web dependency installation failed." }
            } finally { Pop-Location }
        }
        if ($ProductionWeb) {
            # Always build after env sync: NEXT_PUBLIC_* values are compiled into JS.
            $env:NEXT_DIST_DIR = '.next-share'
            $env:NEXT_TELEMETRY_DISABLED = '1'
            $buildDir = [IO.Path]::GetFullPath((Join-Path $WebRoot $env:NEXT_DIST_DIR))
            if ($buildDir -ne [IO.Path]::GetFullPath((Join-Path $RepoRoot 'web\.next-share'))) {
                throw 'Refusing to clean an unexpected build directory.'
            }
            if (Test-Path -LiteralPath $buildDir) {
                # Fail promptly on locked files; Next 14's own cleanup can retry forever.
                Remove-Item -LiteralPath $buildDir -Recurse -Force -ErrorAction Stop
            }
            Write-Host 'Building the current website for sharing...'
            Push-Location $WebRoot
            try {
                & $npm run build
                if ($LASTEXITCODE -ne 0) { throw 'Production web build failed. Fix the build error above and retry.' }
            } finally { Pop-Location }
            if (-not (Test-Path (Join-Path $buildDir 'BUILD_ID'))) {
                throw 'Production build did not produce BUILD_ID.'
            }
            Start-DevWindow -Title 'Voice Agent Web' -WorkingDir $WebRoot `
                -Command "`$env:NEXT_DIST_DIR = '.next-share'; & '$npm' run start -- -p 3000" `
                -LogFile (Join-Path $LogDir 'web.log')
        } else {
            Write-Host "Starting Next.js on $WebUrl"
            Start-DevWindow -Title 'Voice Agent Web' -WorkingDir $WebRoot `
                -Command "`$env:NEXT_DIST_DIR = '.next-dev'; & '$npm' run dev -- -p 3000" `
                -LogFile (Join-Path $LogDir 'web.log')
        }
        $webOk = Wait-ForService -Label "Website" -Url $DevLoginUrl
        if ($webOk) {
            # The uvicorn reloader may bounce the API right after first boot (stale
            # file-system timestamps trigger WatchFiles). When that happens the port
            # goes down entirely for the reload cycle (~15-20 s).
            # Strategy: use fast TCP check to detect if the API *process* is alive,
            # then wait for the HTTP health endpoint. This avoids false-triggering on
            # slow health responses (cold DB pool, warmup) vs. actual reloads.
            $apiPortUp = Test-PortInUse -Port 8000
            if (-not $apiPortUp) {
                Write-Host "API port 8000 is down (uvicorn --reload bounce). Waiting for API to come back..."
                $apiBackOk = Wait-ForService -Label "API (post-reload)" -Url "$ApiUrl/api/health" -MaxAttempts 90 -TimeoutSec 8
                if (-not $apiBackOk) {
                    Write-Warning "API did not recover after reload. Check $LogDir\api.log"
                    $apiOk = $false
                } else {
                    $apiOk = $true
                }
            }
            if ($apiOk) {
                $proxyOk = Wait-ForService -Label "Website API proxy" -Url "$WebUrl/api/health" -MaxAttempts 60 -TimeoutSec 5
                if (-not $proxyOk) {
                    # Distinguish real proxy failure from API being down again
                    if (Test-HttpOk "$ApiUrl/api/health" 8) {
                        Write-Warning "Website is up and API is healthy, but the /api proxy is not forwarding. Check Next.js rewrites."
                        $webOk = $false
                    } else {
                        Write-Warning "Website API proxy failed because the API itself is not responding. Check $LogDir\api.log"
                        $apiOk = $false
                    }
                }
            }
        }
    }
} else {
    $webOk = $true
}

if (-not $ApiOnly -and (Test-Path $DialtactRoot) -and $apiOk) {
    if (-not (Test-Path (Join-Path $DialtactRoot "node_modules"))) {
        Write-Host "Installing Dialtact dependencies (first run)..."
        Push-Location $DialtactRoot
        try {
            & $npm install
            if ($LASTEXITCODE -ne 0) { throw "Dialtact dependency installation failed." }
        } finally { Pop-Location }
    }
    Write-Host "Starting Dialtact on $DialtactUrl"
    Start-DevWindow -Title "Dialtact AI" -WorkingDir $DialtactRoot `
        -Command "& '$npm' run dev" `
        -LogFile (Join-Path $LogDir "dialtact.log")
    $dialtactOk = Wait-ForService -Label "Dialtact" -Url $DialtactUrl -MaxAttempts 60
}

if (-not $QuietBanner) {
    Write-DevBanner -ApiOk $apiOk -WebOk $webOk -DialtactOk $dialtactOk -DialtactFocus:$DialtactFocus
}

if ($Open -and $webOk) {
    $openUrl = if ($DialtactFocus -and $dialtactOk) { $DialtactUrl } else { $DevLoginUrl }
    Write-Host "Opening $openUrl in browser..."
    Start-Process $openUrl
}

if ($DialtactFocus) {
    # Dialtact mode: API + Dialtact are the critical pair. Website proxy is nice-to-have.
    if (-not $apiOk) {
        Write-Warning "API is not healthy. Exiting with error."
        exit 1
    }
    if (-not $dialtactOk) {
        Write-Warning "Dialtact is not running. Exiting with error."
        exit 1
    }
    if (-not $webOk) {
        Write-Warning "Website proxy is degraded but API + Dialtact are healthy. Continuing."
    }
} else {
    if (-not $apiOk -or -not $webOk) {
        exit 1
    }
}
exit 0
