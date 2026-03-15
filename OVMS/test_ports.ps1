foreach ($srv in @('openvehicles.com','api.openvehicles.com')) {
    foreach ($p in @(1883, 8083, 8084, 8883, 9001, 443)) {
        $r = Test-NetConnection -ComputerName $srv -Port $p -WarningAction SilentlyContinue
        if ($r.TcpTestSucceeded) { Write-Host "$srv :$p OPEN" }
    }
}
