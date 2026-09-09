$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dev_common.ps1')

function Assert-Equal($Actual, $Expected, [string]$Label) {
    if ($Actual -ne $Expected) { throw "$Label : expected $Expected, got $Actual" }
}

# Probe status handling without starting a server or contacting the network.
function curl.exe {
    $global:LASTEXITCODE = $script:ProbeExit
    return $script:ProbeCode
}
$script:ProbeExit = 0
foreach ($case in @(@('200', $true), @('302', $true), @('404', $false), @('401', $false), @('500', $false))) {
    $script:ProbeCode = $case[0]
    Assert-Equal (Test-HttpOk 'http://test.invalid') $case[1] "HTTP $($case[0])"
}
$script:ProbeExit = 28
$script:ProbeCode = '200'
Assert-Equal (Test-HttpOk 'http://test.invalid') $false 'Timed out probe'

Assert-Equal (Test-DevCommandLine 'cloudflared.exe tunnel --url http://127.0.0.1:3000') $true 'Own quick tunnel'
Assert-Equal (Test-DevCommandLine 'cloudflared.exe tunnel --url http://127.0.0.1:9000') $false 'Unrelated quick tunnel'
Assert-Equal (Test-DevCommandLine 'ngrok.exe http 9000') $false 'Unrelated ngrok'
$repo = Split-Path -Parent $PSScriptRoot
Assert-Equal (Test-DevCommandLine "cloudflared.exe tunnel --config `"$repo\cloudflared\config.yml`" run") $true 'Own named tunnel'

# Never climb from a managed child into the invoking shell.
$protected = New-Object 'System.Collections.Generic.HashSet[int]'
[void]$protected.Add(100)
$map = @{
    100 = [pscustomobject]@{ Name = 'powershell.exe'; ParentProcessId = 50 }
    101 = [pscustomobject]@{ Name = 'powershell.exe'; ParentProcessId = 100 }
    102 = [pscustomobject]@{ Name = 'node.exe'; ParentProcessId = 101 }
}
Assert-Equal (Get-AncestorRootPid 102 $map $protected) 101 'Protected shell'
Write-Host 'Dev script regression checks passed.'
