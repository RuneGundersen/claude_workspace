# Build OVMS Fiat 500e firmware via Docker
# Run from repo root: .\OVMS\firmware\build.ps1

$ErrorActionPreference = "Stop"

$IMAGE = "ovms-fiat500e-cells"
$OUT   = "$PSScriptRoot\output"

# Pull latest Dockerfile / plugin changes before building
Write-Host "Pulling latest changes..." -ForegroundColor Cyan
git -C "$PSScriptRoot\..\.." pull

# --no-cache-filter forces only the compile stage to re-run;
# the slow OVMS clone stage stays cached.
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build --no-cache-filter builder --no-cache-filter final `
    -t $IMAGE $PSScriptRoot

Write-Host "`nExtracting firmware to $OUT ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
docker run --rm -v "${OUT}:/output" $IMAGE

Write-Host "`nDone. Flash file: $OUT\ovms3.bin" -ForegroundColor Green
