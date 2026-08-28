# Quick Cloudflare Tunnel → local API (port 8000). No account required.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/tunnel_cloudflared.ps1
# Writes public URL to .tunnel-url and updates PLIVO_* in .env

param(
    [int]$Port = 8000,
    [string]$Target = "http://127.0.0.1:$Port"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$UrlFile = Join-Path $RepoRoot ".tunnel-url"
$EnvFile = Join-Path $RepoRoot ".env"
$LogFile = Join-Path $RepoRoot ".tunnel-cloudflared.log"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared not found. Install: winget install Cloudflare.cloudflared"
}

# Stop prior tunnel on this machine (cloudflared child processes)
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "tunnel --url" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting Cloudflare quick tunnel → $Target"
$proc = Start-Process -FilePath "cloudflared" -ArgumentList @("tunnel", "--url", $Target) `
    -RedirectStandardError $LogFile -PassThru -WindowStyle Hidden

$publicUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Test-Path $LogFile)) { continue }
    $log = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
    if ($log -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        $publicUrl = $Matches[1]
        break
    }
}

if (-not $publicUrl) {
    Write-Error "Could not read tunnel URL from $LogFile. Is port $Port serving the API?"
}

Set-Content -Path $UrlFile -Value $publicUrl -NoNewline
Write-Host "Public API URL: $publicUrl"
Write-Host "Saved to .tunnel-url"

# Patch .env PLIVO / webhook vars
if (Test-Path $EnvFile) {
    $lines = Get-Content $EnvFile
    $map = @{
        "PUBLIC_TUNNEL_URL"      = $publicUrl
        "PLIVO_WEBHOOK_BASE_URL" = $publicUrl
        "PLIVO_PUBLIC_BASE_URL"  = $publicUrl
        "CLIENT_URL"             = "http://localhost:3000"
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
    Write-Host "Updated .env webhook vars (PUBLIC_TUNNEL_URL, PLIVO_*)."
}

Write-Host ""
Write-Host "Vobiz/Plivo Answer URL: $publicUrl/api/plivo/answer"
Write-Host "Restart API after .env change if it was already running."
Write-Host "Tunnel PID: $($proc.Id)  (log: .tunnel-cloudflared.log)"
