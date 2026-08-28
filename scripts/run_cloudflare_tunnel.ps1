# Run named Cloudflare tunnel (requires scripts/setup_cloudflare_tunnel.ps1 first)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ConfigFile = Join-Path $RepoRoot "cloudflared\config.yml"

if (-not (Test-Path $ConfigFile)) {
    Write-Error "Missing $ConfigFile — run: powershell -File scripts/setup_cloudflare_tunnel.ps1"
}

Write-Host "Starting named tunnel (config: cloudflared/config.yml)"
Write-Host "Press Ctrl+C to stop."
& cloudflared tunnel --config $ConfigFile run voice-agent-dev
