# ngrok tunnel → local API (port 8000). Requires free ngrok account + authtoken.
# 1. Sign up: https://dashboard.ngrok.com/signup
# 2. Copy authtoken → set in .env as NGROK_AUTHTOKEN=...
# Usage: powershell -ExecutionPolicy Bypass -File scripts/tunnel_ngrok.ps1

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$UrlFile = Join-Path $RepoRoot ".tunnel-url"
$EnvFile = Join-Path $RepoRoot ".env"
$LogFile = Join-Path $RepoRoot ".tunnel-ngrok.log"

function Set-TunnelEnv {
    param([string]$PublicUrl)
    Set-Content -Path $UrlFile -Value $PublicUrl -NoNewline
    if (-not (Test-Path $EnvFile)) { return }
    $lines = Get-Content $EnvFile
    $map = @{
        "PUBLIC_TUNNEL_URL"         = $PublicUrl
        "EXOTEL_WEBHOOK_BASE_URL"   = $PublicUrl
        "CLIENT_URL"                = "http://localhost:3000"
    }
    foreach ($key in $map.Keys) {
        $val = $map[$key]
        $found = $false
        for ($j = 0; $j -lt $lines.Count; $j++) {
            if ($lines[$j] -match "^$key=") {
                $lines[$j] = "$key=$val"
                $found = $true
                break
            }
        }
        if (-not $found) { $lines += "$key=$val" }
    }
    Set-Content -Path $EnvFile -Value $lines
}

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error "ngrok not found. Install: winget install Ngrok.Ngrok"
}

$token = $env:NGROK_AUTHTOKEN
if (-not $token -and (Test-Path $EnvFile)) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match "^NGROK_AUTHTOKEN=(.+)$") { $token = $Matches[1].Trim(); break }
    }
}
if (-not $token) {
    Write-Error "Set NGROK_AUTHTOKEN in .env. Get it from https://dashboard.ngrok.com/get-started/your-authtoken"
}

ngrok config add-authtoken $token | Out-Null

Get-CimInstance Win32_Process -Filter "Name='ngrok.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting ngrok http $Port ..."
Start-Process -FilePath "ngrok" -ArgumentList @("http", $Port.ToString(), "--log=stdout") `
    -WindowStyle Hidden -RedirectStandardOutput $LogFile -RedirectStandardError (Join-Path $RepoRoot ".tunnel-ngrok.err.log") | Out-Null

$publicUrl = $null
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $api = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
        $publicUrl = ($api.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1).public_url
        if ($publicUrl) { break }
    } catch { }
}

if (-not $publicUrl) {
    Write-Error "ngrok did not start. Open http://127.0.0.1:4040 or check $LogFile"
}

Set-TunnelEnv -PublicUrl $publicUrl
Write-Host "Public API URL: $publicUrl"
Write-Host "Exotel passthru: $publicUrl/api/exotel/passthru"
Write-Host "ngrok dashboard: http://127.0.0.1:4040"
