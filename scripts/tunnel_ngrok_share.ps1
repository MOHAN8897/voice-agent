# Share the full website via ngrok (single tunnel on port 3000).
# Next.js proxies /api and /ws to the local API - friend only needs one link.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/tunnel_ngrok_share.ps1

param(
    [switch]$SkipHealthCheck
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$WebEnvFile = Join-Path $RepoRoot "web\.env.local"
$NgrokConfig = Join-Path $RepoRoot ".ngrok-share.yml"
$UrlFile = Join-Path $RepoRoot ".tunnel-share-urls.json"

function Find-NgrokExe {
    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ngrok.exe"
    )
    $wingetPkg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_*" `
        -Filter "ngrok.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($wingetPkg) { $candidates += $wingetPkg }
    $candidates += @(
        "$env:ProgramFiles\Ngrok\ngrok.exe",
        "$env:LOCALAPPDATA\ngrok\ngrok.exe"
    )

    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return $null
}

function Ensure-NgrokUpdated {
    param([string]$NgrokExe)
    Write-Host "Checking ngrok version..."
    try {
        $job = Start-Job { param($exe) & $exe version 2>&1 | Select-Object -First 1 } -ArgumentList $NgrokExe
        $verLine = $job | Wait-Job -Timeout 8 | Receive-Job
        $job | Remove-Job -Force -ErrorAction SilentlyContinue
        if (-not $verLine) {
            Write-Warning "ngrok version check timed out"
            return
        }
        Write-Host "  $verLine"
        if ($verLine -match "version\s+(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 20)) {
                Write-Host "  ngrok is too old (need 3.20+). Run: ngrok update"
                Write-Host "  Or use: npm run share  (uses Cloudflare, no ngrok needed)"
            }
        }
    } catch {
        Write-Warning "Could not check ngrok: $_"
    }
}

function Read-EnvToken {
    if ($env:NGROK_AUTHTOKEN) { return $env:NGROK_AUTHTOKEN.Trim() }
    if (-not (Test-Path $EnvFile)) { return $null }
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match "^NGROK_AUTHTOKEN=(.+)$") { return $Matches[1].Trim() }
    }
    return $null
}

function Set-WebEnvSameOriginShare {
    $header = "# Auto-updated by tunnel_ngrok_share.ps1 (single ngrok tunnel)"
    $out = @($header, "API_INTERNAL_URL=http://127.0.0.1:8000")
    if (Test-Path $WebEnvFile) {
        foreach ($line in Get-Content $WebEnvFile) {
            if ($line -match "^# Auto-updated by tunnel_ngrok_share") { continue }
            if ($line -match "^NEXT_PUBLIC_API_URL=") { continue }
            if ($line -match "^API_INTERNAL_URL=") { continue }
            if ($line.Trim()) { $out += $line }
        }
    }
    Set-Content -Path $WebEnvFile -Value $out
}

function Start-NgrokTunnel {
    param(
        [string]$Token,
        [string]$NgrokExe
    )

    Get-CimInstance Win32_Process -Filter "Name='ngrok.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1

    & $NgrokExe config add-authtoken $Token 2>&1 | Out-Null

    @"
version: "2"
authtoken: $Token
tunnels:
  voice-web:
    addr: 3000
    proto: http
"@ | Set-Content -Path $NgrokConfig -Encoding ASCII

    Write-Host "Starting ngrok tunnel on port 3000..."
    $logFile = Join-Path $RepoRoot "data\dev-logs\ngrok.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
    Start-Process -FilePath $NgrokExe `
        -ArgumentList @("start", "voice-web", "--config", $NgrokConfig, "--log=stdout") `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError (Join-Path $RepoRoot "data\dev-logs\ngrok.err.log") | Out-Null

    $webUrl = $null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
            foreach ($t in $resp.tunnels) {
                if ($t.proto -eq "https" -and $t.public_url) {
                    $webUrl = $t.public_url
                    break
                }
            }
            if ($webUrl) { break }
        } catch { }
    }

    if (-not $webUrl) {
        $errLog = Join-Path $RepoRoot "data\dev-logs\ngrok.err.log"
        $hint = ""
        if (Test-Path $errLog) {
            $tail = Get-Content $errLog -Tail 5 -ErrorAction SilentlyContinue
            if ($tail) { $hint = "`nLast ngrok log: $($tail -join ' ')" }
        }
        throw "ngrok did not start. Try: ngrok update`nOpen http://127.0.0.1:4040 or see data\dev-logs\ngrok.err.log$hint"
    }

    return $webUrl
}

$ngrokExe = Find-NgrokExe
if (-not $ngrokExe) {
    Write-Error @"
ngrok not found.
Install: winget install Ngrok.Ngrok
Then close and reopen PowerShell.
"@
}

Ensure-NgrokUpdated -NgrokExe $ngrokExe

$token = Read-EnvToken
if (-not $token) {
    Write-Error "Set NGROK_AUTHTOKEN in .env (https://dashboard.ngrok.com/get-started/your-authtoken)"
}

if (-not $SkipHealthCheck) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
    } catch {
        Write-Error "API is not running on port 8000. Run: npm run share"
    }
}

try {
    $ok = $false
    for ($i = 0; $i -lt 10; $i++) {
        try {
            Invoke-WebRequest -Uri "http://localhost:3000/dev/login" -UseBasicParsing -TimeoutSec 3 | Out-Null
            $ok = $true
            break
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ok) { throw "not ready" }
} catch {
    Write-Error "Website must be running on port 3000 before ngrok starts. Run: npm run share"
}

$webUrl = Start-NgrokTunnel -Token $token -NgrokExe $ngrokExe
Set-WebEnvSameOriginShare
@{ web = $webUrl; mode = "single-tunnel" } | ConvertTo-Json | Set-Content -Path $UrlFile

$shareLink = "$webUrl/dev/test-studio"

Write-Host ""
Write-Host "============================================================"
Write-Host "  SHARE THIS LINK WITH YOUR FRIEND"
Write-Host "============================================================"
Write-Host ""
Write-Host "  $shareLink"
Write-Host ""
Write-Host "  Login: $webUrl/dev/login  (dev / devpass)"
Write-Host "  ngrok dashboard: http://127.0.0.1:4040"
Write-Host "============================================================"

return $shareLink
