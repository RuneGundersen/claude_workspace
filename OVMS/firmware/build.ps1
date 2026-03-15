# Build OVMS Fiat 500e firmware via Docker
# Run from repo root: .\OVMS\firmware\build.ps1

$IMAGE = "ovms-fiat500e-cells"
$OUT   = "$PSScriptRoot\output"
$LOG   = "$PSScriptRoot\build_log.txt"

# Pull latest Dockerfile / plugin changes before building
Write-Host "Pulling latest changes..." -ForegroundColor Cyan
git -C "$PSScriptRoot\..\.." pull

# --no-cache-filter forces only the compile stage to re-run.
# --progress=plain streams every compiler line so errors are visible.
# Tee-Object saves the full log to build_log.txt for searching.
Write-Host "Building Docker image..." -ForegroundColor Cyan
$env:DOCKER_BUILDKIT = "1"
docker build --no-cache-filter builder --no-cache-filter final `
    --progress=plain `
    -t $IMAGE $PSScriptRoot 2>&1 | Tee-Object $LOG

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nBuild FAILED (exit $LASTEXITCODE). Searching log for errors..." -ForegroundColor Red
    Select-String -Path $LOG -Pattern "error:" | Select-Object -First 40
    exit $LASTEXITCODE
}

Write-Host "Full log: $LOG" -ForegroundColor DarkGray
Write-Host "`nExtracting firmware to $OUT ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $OUT | Out-Null
docker run --rm -v "${OUT}:/output" $IMAGE

Write-Host "`nDone. Flash file: $OUT\ovms3.bin" -ForegroundColor Green
