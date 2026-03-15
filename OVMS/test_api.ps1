# Test WebSocket upgrade on port 443 and check OVMS server directly
$user = 'EV88283'
$pass = 'WsR@RQqp%4VVn'

# Test dexters-web WebSocket upgrade header
Write-Host "--- WebSocket upgrade test on port 443 ---"
try {
    $r = Invoke-WebRequest -Uri 'https://ovms.dexters-web.de/mqtt' `
        -Headers @{ Upgrade='websocket'; Connection='Upgrade'; 'Sec-WebSocket-Version'='13'; 'Sec-WebSocket-Key'='dGhlIHNhbXBsZSBub25jZQ==' } `
        -UseBasicParsing -TimeoutSec 8
    Write-Host "Status: $($r.StatusCode) Content: $($r.Content.Substring(0,200))"
} catch { Write-Host "Result: $($_.Exception.Response.StatusCode.value__) $($_.Exception.Message)" }

# Test openvehicles.com MQTT WebSocket
Write-Host "`n--- openvehicles.com ports ---"
foreach ($p in @(1883, 8883, 9001, 8083, 8084)) {
    $r = Test-NetConnection -ComputerName 'openvehicles.com' -Port $p -WarningAction SilentlyContinue
    Write-Host "openvehicles.com:$p -> $($r.TcpTestSucceeded)"
}

# Also try api.openvehicles.com
Write-Host "`n--- api.openvehicles.com ---"
foreach ($p in @(80, 443, 1883, 9001)) {
    $r = Test-NetConnection -ComputerName 'api.openvehicles.com' -Port $p -WarningAction SilentlyContinue
    Write-Host "api.openvehicles.com:$p -> $($r.TcpTestSucceeded)"
}
