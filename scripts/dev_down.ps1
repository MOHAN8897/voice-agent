# Stop local dev servers (API 8000, Next 3000-3003) and Cloudflare tunnels
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

Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "Stopping cloudflared PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "Done."
