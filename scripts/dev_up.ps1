# Start API + Next.js for local dev (Windows PowerShell)
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/dev_up.ps1
# Options:
#   -KillStale    Stop processes on ports 8000 and 3000 before starting
#   -ApiOnly      Start API only
#   -WebOnly      Start Next.js only

param(
    [switch]$KillStale,
    [switch]$ApiOnly,
    [switch]$WebOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "web"

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

if ($KillStale) {
    Write-Host "Clearing ports 8000 and 3000-3003..."
    foreach ($port in @(8000, 3000, 3001, 3002, 3003)) {
        Stop-Port $port
    }
    Start-Sleep -Seconds 2
}

if (-not $WebOnly) {
    Write-Host "Starting API on http://127.0.0.1:8000"
    Start-Process -WorkingDirectory $RepoRoot -FilePath "python" -ArgumentList @(
        "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "8000", "--reload"
    )
}

if (-not $ApiOnly) {
    if (-not (Test-Path $WebRoot)) {
        Write-Error "Web folder not found: $WebRoot"
    }
    Write-Host "Starting Next.js on http://localhost:3000"
    Start-Process -WorkingDirectory $WebRoot -FilePath "npm" -ArgumentList @("run", "dev", "--", "-p", "3000")
}

Write-Host ""
Write-Host "Dev Portal:  http://localhost:3000/dev/login"
Write-Host "API health:  http://127.0.0.1:8000/api/health"
Write-Host ""
Write-Host "If port 8000 is already in use, run:  powershell -File scripts/dev_up.ps1 -KillStale"
Write-Host "Do NOT run 'cd web' when you are already inside the web folder."
