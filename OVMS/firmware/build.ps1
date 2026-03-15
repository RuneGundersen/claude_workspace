# Build OVMS Fiat 500e firmware via Docker
# Run from repo root: .\OVMS\firmware\build.ps1

$ErrorActionPreference = "Stop"

$IMAGE = "ovms-fiat500e-cells"
$OUT   = "$PSScriptRoot\output"

Write-Host "Building Docker image (first run ~15 min; cached ~3 min)..." -ForegroundColor Cyan
docker build -t $IMAGE $PSScriptRoot

Write-Host "`nExtracting firmware to $OUT ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
docker run --rm -v "${OUT}:/output" $IMAGE

Write-Host "`nDone. Flash file: $OUT\ovms3.bin" -ForegroundColor Green
