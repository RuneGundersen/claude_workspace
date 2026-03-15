# Build OVMS Fiat 500e firmware via Docker
# Run from repo root: .\OVMS\firmware\build.ps1

$ErrorActionPreference = "Stop"

$IMAGE = "ovms-fiat500e-cells"
$OUT   = "$PSScriptRoot\output"

# Pull latest Dockerfile / plugin changes before building
Write-Host "Pulling latest changes..." -ForegroundColor Cyan
git -C "$PSScriptRoot\..\.." pull

# --no-cache-filter forces only the compile stage to re-run.
# --progress=plain shows full build output so errors are visible.
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build --no-cache-filter builder --no-cache-filter final `
    --progress=plain `
    -t $IMAGE $PSScriptRoot

Write-Host "`nExtracting firmware to $OUT ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
docker run --rm -v "${OUT}:/output" $IMAGE

Write-Host "`nDone. Flash file: $OUT\ovms3.bin" -ForegroundColor Green
