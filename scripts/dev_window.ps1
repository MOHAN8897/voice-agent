# Host process for one API / web / tunnel window.
# -NoProfile so a user $ErrorActionPreference=Stop cannot kill next/uvicorn
# when they write errors to stderr (Next.js proxy ECONNRESET).
param(
    [Parameter(Mandatory = $true)][string]$RunnerFile
)

$ErrorActionPreference = "Continue"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

if (-not (Test-Path -LiteralPath $RunnerFile)) {
    Write-Error "Dev window runner missing: $RunnerFile"
    return
}

try {
    & $RunnerFile
} catch {
    Write-Host "Dev window failed: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace
}
