# Stop local dev servers (API 8000, Next 3000-3003) and Cloudflare/ngrok tunnels.
# Kills process trees (uvicorn reloader + worker, npm/node, wrapper PowerShell windows)
# and waits until the ports are actually free.

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev_common.ps1")

Write-Host "dev:down starting..."
$ok = Stop-VoiceAgentDevStack

if (-not $ok) { exit 1 }
# Only remove generated state once shutdown has actually succeeded.
foreach ($folder in @('voice-agent-dev-runners', 'voice-agent-dev-jobs')) {
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')
    $cleanupPath = [IO.Path]::GetFullPath((Join-Path $tempRoot $folder))
    if ((Split-Path -Parent $cleanupPath) -ne $tempRoot) { throw 'Invalid cleanup path.' }
    if (Test-Path -LiteralPath $cleanupPath) {
        Remove-Item -LiteralPath $cleanupPath -Recurse -Force
    }
}
$repoRoot = Split-Path -Parent $PSScriptRoot
foreach ($file in @('.tunnel-url', '.tunnel-share-urls.json')) {
    $path = Join-Path $repoRoot $file
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
Write-Host "Done."
exit 0
