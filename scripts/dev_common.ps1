# Shared helpers for local API / Next / tunnel windows.
# Dot-source from other scripts. Do not run this file directly.

$script:DevListenPorts = @(8000, 3000, 3001, 3002, 3003)
$script:WrapperProcessNames = @(
    "powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe",
    "npm.cmd", "node.exe", "python.exe", "pythonw.exe"
)
$script:NeverKillNames = @(
    "idle", "system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe",
    "cursor.exe", "code.exe"
)

function Get-UvicornDevCommand {
    param([Parameter(Mandatory = $true)][string]$PythonPath)
    # Reload only server/ so writes under data/, web/.next, and logs do not
    # bounce uvicorn and reset in-flight Next.js proxy connections (ECONNRESET).
    return "& '$PythonPath' -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload --reload-dir server"
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 2)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-ForService {
    param(
        [string]$Label,
        [string]$Url,
        [int]$MaxAttempts = 90
    )
    Write-Host "Waiting for $Label ($Url)..."
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        if (Test-HttpOk $Url) {
            Write-Host "$Label is ready."
            return $true
        }
        if ($i -gt 0 -and ($i % 5) -eq 0) {
            Write-Host "  still waiting... ($i/$MaxAttempts)"
        }
        Start-Sleep -Seconds 1
    }
    Write-Warning "$Label did not respond at $Url"
    return $false
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Value, $utf8)
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    if ($ProcessId -le 4) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Test-PortInUse {
    param([int]$Port, [string]$HostName = "127.0.0.1")
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(250, $false)
        if (-not $connected) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

function Get-ListeningPids {
    param([int]$Port)
    $ids = New-Object System.Collections.Generic.List[int]
    # netstat is the source of truth on Windows; Get-NetTCPConnection can keep a
    # dead PID in Listen state after uvicorn exits (ghost 8000 / ECONNRESET).
    foreach ($line in @(netstat -ano 2>$null | Select-String ":$Port\s")) {
        if ($line.Line -match "LISTENING\s+(\d+)\s*$") {
            $owning = [int]$Matches[1]
            if ($owning -gt 0 -and -not $ids.Contains($owning)) {
                [void]$ids.Add($owning)
            }
        }
    }
    if ($ids.Count -eq 0) {
        try {
            $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
            foreach ($c in @($conns)) {
                $owning = [int]$c.OwningProcess
                if ($owning -gt 0 -and -not $ids.Contains($owning)) {
                    [void]$ids.Add($owning)
                }
            }
        } catch { }
    }
    return @($ids)
}

function Get-BusyDevPorts {
    $busy = @()
    foreach ($port in $script:DevListenPorts) {
        $live = @(Get-ListeningPids $port)
        if ($live.Count -gt 0) {
            $busy += $port
            continue
        }
        if ((Test-PortInUse $port) -or (Test-PortInUse -Port $port -HostName "localhost")) {
            $busy += $port
        }
    }
    return $busy
}

function Get-Win32Processes {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Get-ProcessNameById {
    param([int]$ProcessId, $ProcessMap)
    if ($ProcessId -le 0) { return "" }
    $row = $ProcessMap[$ProcessId]
    if ($row) { return [string]$row.Name }
    try {
        return [string](Get-Process -Id $ProcessId -ErrorAction Stop).Name
    } catch {
        return ""
    }
}

function Test-NeverKill {
    param([int]$ProcessId, [string]$Name)
    if ($ProcessId -le 4) { return $true }
    $n = $Name.ToLowerInvariant()
    if (-not $n.EndsWith(".exe")) { $n = "$n.exe" }
    return $script:NeverKillNames -contains $n
}

function Get-ProtectedPids {
    $keep = New-Object System.Collections.Generic.HashSet[int]
    [void]$keep.Add(0)
    [void]$keep.Add(4)
    [void]$keep.Add($PID)
    $procs = Get-Win32Processes
    $map = @{}
    foreach ($p in $procs) { $map[[int]$p.ProcessId] = $p }
    $cursor = $PID
    $guard = 0
    while ($cursor -gt 4 -and $guard -lt 24) {
        $guard++
        [void]$keep.Add($cursor)
        $row = $map[$cursor]
        if (-not $row) { break }
        $cursor = [int]$row.ParentProcessId
        $nm = ([string]$row.Name).ToLowerInvariant()
        if ($script:NeverKillNames -contains $nm -or $script:NeverKillNames -contains "$nm.exe") { break }
    }
    return $keep
}

function Get-AncestorRootPid {
    param(
        [int]$ProcessId,
        $ProcessMap,
        $Protected
    )
    $cursor = $ProcessId
    $root = $ProcessId
    $guard = 0
    while ($cursor -gt 4 -and $guard -lt 24) {
        $guard++
        if ($Protected.Contains($cursor)) { break }
        $row = $ProcessMap[$cursor]
        if (-not $row) { break }
        $name = [string]$row.Name
        if (Test-NeverKill -ProcessId $cursor -Name $name) { break }
        $root = $cursor
        $parentId = [int]$row.ParentProcessId
        if ($parentId -le 4 -or $Protected.Contains($parentId)) { break }
        $parent = $ProcessMap[$parentId]
        if (-not $parent) { break }
        $parentName = ([string]$parent.Name).ToLowerInvariant()
        if (-not $parentName.EndsWith(".exe")) { $parentName = "$parentName.exe" }
        if ($script:WrapperProcessNames -notcontains $parentName) { break }
        if (Test-NeverKill -ProcessId $parentId -Name $parent.Name) { break }
        $cursor = $parentId
    }
    return $root
}

function Stop-ProcessTreeForce {
    param(
        [int]$ProcessId,
        $Protected
    )
    if ($ProcessId -le 4) { return }
    if ($Protected -and $Protected.Contains($ProcessId)) { return }
    $name = ""
    try {
        $row = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
        if ($row) { $name = [string]$row.Name }
    } catch { }
    if (Test-NeverKill -ProcessId $ProcessId -Name $name) { return }
    $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue)
    foreach ($k in $kids) {
        Stop-ProcessTreeForce -ProcessId ([int]$k.ProcessId) -Protected $Protected
    }
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Test-DevCommandLine {
    param([string]$CommandLine)
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    if ($CommandLine -match '(?i)uvicorn\s+server\.app') { return $true }
    if ($CommandLine -match '(?i)cloudflared(\.exe)?\s+tunnel') { return $true }
    if ($CommandLine -match '(?i)\bngrok(\.exe)?\s+http') { return $true }
    if ($CommandLine -match '(?i)dev_window\.ps1') { return $true }
    if ($CommandLine -match '(?i)voice-agent-dev-(runners|jobs)') { return $true }
    if ($CommandLine -match '(?i)Voice Agent (API|Web|Tunnel)') { return $true }
    if ($CommandLine -match '(?i)voice agent[\\/]+scripts[\\/]+dev_(stack|up|down)\.ps1') { return $true }
    # Next / npm started from this repo's web folder (space in "voice agent" is required).
    if ($CommandLine -match '(?i)voice agent[\\/]+web' -and $CommandLine -match '(?i)(next|npm)') { return $true }
    return $false
}

function Stop-VoiceAgentDevStack {
    Write-Host "Stopping voice-agent API, website, and tunnels..."
    $protected = Get-ProtectedPids

    for ($round = 1; $round -le 8; $round++) {
        $procs = Get-Win32Processes
        $map = @{}
        foreach ($p in $procs) { $map[[int]$p.ProcessId] = $p }

        $seeds = New-Object System.Collections.Generic.HashSet[int]
        foreach ($port in $script:DevListenPorts) {
            foreach ($owning in @(Get-ListeningPids $port)) {
                [void]$seeds.Add($owning)
                # Uvicorn --reload / multiprocessing can leave children holding the
                # socket after the parent PID is already gone (netstat still shows
                # the dead parent as LISTENING).
                foreach ($orphan in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$owning" -ErrorAction SilentlyContinue)) {
                    [void]$seeds.Add([int]$orphan.ProcessId)
                }
            }
        }
        foreach ($p in $procs) {
            $id = [int]$p.ProcessId
            $name = ([string]$p.Name).ToLowerInvariant()
            if ($name -eq "cloudflared.exe" -or $name -eq "ngrok.exe") {
                [void]$seeds.Add($id)
                continue
            }
            if (Test-DevCommandLine -CommandLine ([string]$p.CommandLine)) {
                [void]$seeds.Add($id)
            }
        }
        foreach ($proc in @(Get-Process -Name powershell, pwsh, cmd -ErrorAction SilentlyContinue)) {
            $title = [string]$proc.MainWindowTitle
            if ($title -match '(?i)Voice Agent|Cloudflare Tunnel') {
                [void]$seeds.Add([int]$proc.Id)
            }
        }

        $roots = New-Object System.Collections.Generic.HashSet[int]
        foreach ($id in @($seeds)) {
            if ($protected.Contains($id)) { continue }
            $name = Get-ProcessNameById -ProcessId $id -ProcessMap $map
            if (Test-NeverKill -ProcessId $id -Name $name) { continue }
            $root = Get-AncestorRootPid -ProcessId $id -ProcessMap $map -Protected $protected
            if (-not $protected.Contains($root)) {
                [void]$roots.Add($root)
            }
        }

        if ($roots.Count -eq 0) {
            $busyNow = @(Get-BusyDevPorts)
            if ($busyNow.Count -eq 0) { break }
        }

        foreach ($id in @($roots)) {
            Write-Host "Stopping process tree PID $id (round $round)"
            Stop-ProcessTreeForce -ProcessId $id -Protected $protected
        }
        Start-Sleep -Milliseconds 450
    }

    $deadline = (Get-Date).AddSeconds(8)
    do {
        $busy = @(Get-BusyDevPorts)
        if ($busy.Count -eq 0) { break }
        Start-Sleep -Milliseconds 400
    } while ((Get-Date) -lt $deadline)

    if ($busy.Count -gt 0) {
        Write-Warning "Ports still listening: $($busy -join ', '). Close those windows and retry npm run dev:down."
        return $false
    }

    Write-Host "All dev ports are free (8000, 3000-3003)."
    return $true
}

function Start-DevWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDir,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$LogFile
    )
    $runnerDir = Join-Path $env:TEMP "voice-agent-dev-runners"
    New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null
    $runnerFile = Join-Path $runnerDir ("run-" + [guid]::NewGuid().ToString() + ".ps1")
    $logDir = Split-Path -Parent $LogFile
    if ($logDir) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }

    # Runner lives under %TEMP% (no spaces). Do not route through scripts under
    # "D:\voice agent\..." via Start-Process -File — that path breaks startup.
    $runner = @"
`$ErrorActionPreference = 'Continue'
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    `$PSNativeCommandUseErrorActionPreference = `$false
}
Set-Location -LiteralPath '$($WorkingDir.Replace("'", "''"))'
try { `$Host.UI.RawUI.WindowTitle = '$($Title.Replace("'", "''"))' } catch { }
`$log = '$($LogFile.Replace("'", "''"))'
`$utf8 = New-Object System.Text.UTF8Encoding `$false
[System.IO.File]::WriteAllText(`$log, "==== $Title start $(Get-Date -Format o) ====`n", `$utf8)
& {
$Command
} 2>&1 | ForEach-Object {
    if (`$_ -is [System.Management.Automation.ErrorRecord]) { `$_.ToString() } else { "`$_" }
} | ForEach-Object {
    [System.IO.File]::AppendAllText(`$log, "`$_`n", `$utf8)
}
"@
    Write-Utf8NoBom -Path $runnerFile -Value $runner

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runnerFile
    ) | Out-Null
    Write-Host "Opened '$Title' window."
}
