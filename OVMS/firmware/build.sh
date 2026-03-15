#!/usr/bin/env bash
# Build OVMS Fiat 500e firmware (cell-voltage polling) via Docker.
# Run from the repo root: bash OVMS/firmware/build.sh

set -e
cd "$(dirname "$0")/.."   # repo root

IMAGE="ovms-fiat500e-cells"
OUT="OVMS/firmware/output"

echo "▶ Building Docker image (first run ~15 min; cached ~3 min)..."
docker build -t "$IMAGE" OVMS/firmware/

echo ""
echo "▶ Extracting firmware to $OUT/ ..."
mkdir -p "$OUT"
docker run --rm -v "$(pwd)/$OUT:/output" "$IMAGE"
