# Stop local dev servers (API 8000, Next 3000-3003) and Cloudflare/ngrok tunnels.
# Kills process trees (uvicorn reloader + worker, npm/node, wrapper PowerShell windows)
# and waits until the ports are actually free.

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "dev_common.ps1")

Write-Host "dev:down starting..."
$ok = Stop-VoiceAgentDevStack

$runnerDir = Join-Path $env:TEMP "voice-agent-dev-runners"
if (Test-Path $runnerDir) {
    Remove-Item -LiteralPath $runnerDir -Recurse -Force -ErrorAction SilentlyContinue
}
$jobDir = Join-Path $env:TEMP "voice-agent-dev-jobs"
if (Test-Path $jobDir) {
    Remove-Item -LiteralPath $jobDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $ok) { exit 1 }
Write-Host "Done."
exit 0
