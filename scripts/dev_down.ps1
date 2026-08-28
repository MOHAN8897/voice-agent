# Stop local dev servers (API 8000, Next 3000-3003)
$ports = 8000, 3000, 3001, 3002, 3003

foreach ($round in 1..3) {
    foreach ($port in $ports) {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $owning = $c.OwningProcess
            if ($owning -and $owning -ne 0) {
                Write-Host "Stopping PID $owning on port $port"
                Stop-Process -Id $owning -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Milliseconds 700
}

Write-Host "Done."
