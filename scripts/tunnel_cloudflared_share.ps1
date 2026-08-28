# Share website via Cloudflare quick tunnel (port 3000). No account needed.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/tunnel_cloudflared_share.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $RepoRoot "data\dev-logs\cloudflared-share.log"
$UrlFile = Join-Path $RepoRoot ".tunnel-share-urls.json"
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

function Find-CloudflaredExe {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $winget = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_*" `
        -Filter "cloudflared.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($winget) { return $winget }
    return $null
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
    Write-Error "Website must be running on port 3000. Run: npm run share"
}

$cf = Find-CloudflaredExe
if (-not $cf) {
    Write-Error "cloudflared not found. Install: winget install Cloudflare.cloudflared"
}

Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "tunnel --url" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting Cloudflare tunnel on port 3000..."
Start-Process -FilePath $cf -ArgumentList @("tunnel", "--url", "http://127.0.0.1:3000") `
    -RedirectStandardError $LogFile -WindowStyle Hidden | Out-Null

$publicUrl = $null
for ($i = 0; $i -lt 35; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Test-Path $LogFile)) { continue }
    $log = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
    if ($log -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        $publicUrl = $Matches[1]
        break
    }
}

if (-not $publicUrl) {
    throw "Cloudflare tunnel did not start. Check data\dev-logs\cloudflared-share.log"
}

@{ web = $publicUrl; mode = "cloudflared" } | ConvertTo-Json | Set-Content -Path $UrlFile
$shareLink = "$publicUrl/dev/test-studio"

Write-Host ""
Write-Host "============================================================"
Write-Host "  SHARE THIS LINK WITH YOUR FRIEND"
Write-Host "============================================================"
Write-Host ""
Write-Host "  $shareLink"
Write-Host ""
Write-Host "  Login: $publicUrl/dev/login  (dev / devpass)"
Write-Host "============================================================"

return $shareLink
