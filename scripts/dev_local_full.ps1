# Start API + Web + Cloudflare quick tunnel for PSTN webhooks
# Usage: powershell -ExecutionPolicy Bypass -File scripts/dev_local_full.ps1

param(
    [switch]$KillStale,
    [ValidateSet("cloudflared", "cloudflare-named", "ngrok", "none")]
    [string]$Tunnel = "cloudflared"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $PSScriptRoot "dev_up.ps1") -KillStale:$KillStale

Write-Host "Waiting for API..."
$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $healthy) {
    Write-Warning "API health check failed. Start API manually, then run tunnel script."
} else {
    Write-Host "API healthy."
}

switch ($Tunnel) {
    "cloudflared"       { & (Join-Path $PSScriptRoot "tunnel_cloudflared.ps1") }
    "cloudflare-named"  { & (Join-Path $PSScriptRoot "run_cloudflare_tunnel.ps1") }
    "ngrok"             { & (Join-Path $PSScriptRoot "tunnel_ngrok.ps1") }
    default             { Write-Host "Skipping tunnel (use -Tunnel cloudflare-named for stable hustlelabs.in URLs)." }
}

Write-Host ""
Write-Host "=== Local dev ready ==="
Write-Host "UI:         http://localhost:3000/dev/login  (dev / devpass)"
Write-Host "Test Studio http://localhost:3000/dev/test-studio"
Write-Host "API:        http://127.0.0.1:8000/api/health"
if (Test-Path (Join-Path $RepoRoot ".tunnel-url")) {
    $u = Get-Content (Join-Path $RepoRoot ".tunnel-url") -Raw
    Write-Host "Public API: $u"
    Write-Host "Answer URL: $u/api/plivo/answer"
}
