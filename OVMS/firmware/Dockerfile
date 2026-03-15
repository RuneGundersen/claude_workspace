# ─────────────────────────────────────────────────────────────────────────────
# OVMS Fiat 500e — custom firmware build (cell-voltage polling)
#
# Usage:
#   docker build -t ovms-fiat500e firmware/
#   docker run --rm -v "$PWD/firmware/output:/output" ovms-fiat500e
#
# Output: firmware/output/ovms3.bin  — flash via OVMS web UI or esptool
# Build time: ~15–20 min first run (IDF + OVMS clone); ~3 min after (cached).
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: toolchain + ESP-IDF ─────────────────────────────────────────────
# Espressif's official image ships the xtensa cross-compiler and all Python
# dependencies for the IDF version tagged.  OVMS v3 builds against IDF 4.4.x
# (the last stable release before IDF 5).
FROM espressif/idf:v4.4.7 AS toolchain

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*


# ── Stage 2: OVMS source tree ─────────────────────────────────────────────────
# Cloned in a separate layer so rebuilding the plugin doesn't re-clone OVMS.
FROM toolchain AS ovms-src

WORKDIR /build

RUN git clone --depth 1 \
        https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3.git \
        ovms3

# Initialise only the submodules that the build actually needs.
# Full recursive init pulls dozens of unused modules and takes 10+ minutes.
WORKDIR /build/ovms3
# Init all first-level submodules (no --recursive, so sub-submodules are skipped).
# Shallow depth keeps this fast (~1-2 min vs 10+ min for full recursive).
RUN git submodule update --init --depth 1


# ── Stage 3: apply custom plugin + build ─────────────────────────────────────
FROM ovms-src AS builder

# Drop in our modified Fiat 500e plugin (cell-voltage polling)
COPY vehicle_fiat500e.h   /build/ovms3/vehicle/OVMS.V3/components/vehicle_fiat500/src/
COPY vehicle_fiat500e.cpp /build/ovms3/vehicle/OVMS.V3/components/vehicle_fiat500/src/

WORKDIR /build/ovms3/vehicle/OVMS.V3

# Generate sdkconfig from Kconfig defaults without opening the interactive
# menu (which requires a real terminal and fails in Docker).
# `make defconfig` writes sdkconfig silently; subsequent `make` sees it
# already present and skips the menuconfig step entirely.
# TERM=dumb suppresses any residual curses probes.
ENV TERM=dumb

RUN bash -c '. $IDF_PATH/export.sh && make defconfig' \
    && echo "✓ sdkconfig generated"

# Suppress format-truncation warning only in the mongoose component,
# so we don't override global CFLAGS (which would break include paths).
RUN echo "CFLAGS += -Wno-format-truncation" \
    >> /build/ovms3/vehicle/OVMS.V3/components/mongoose/component.mk

RUN bash -c '. $IDF_PATH/export.sh && make -j$(nproc)' \
    && echo "✓ Build succeeded"


# ── Stage 4: runtime — copy binary to mounted volume ─────────────────────────
FROM builder AS final

WORKDIR /build/ovms3/vehicle/OVMS.V3

CMD sh -c '\
    mkdir -p /output && \
    cp build/ovms3.bin             /output/ovms3.bin             && \
    cp build/bootloader/bootloader.bin \
                                   /output/bootloader.bin        && \
    cp build/partition_table/partition-table.bin \
                                   /output/partition-table.bin   && \
    echo "" && \
    echo "════════════════════════════════════════" && \
    echo "  Firmware ready in /output/" && \
    echo "" && \
    echo "  OTA (easiest):" && \
    echo "    OVMS web UI → Config → Firmware → Upload" && \
    echo "    Upload: ovms3.bin" && \
    echo "" && \
    echo "  USB flash (esptool):" && \
    echo "    esptool.py --port /dev/ttyUSB0 --baud 921600 \\" && \
    echo "      write_flash \\" && \
    echo "        0x1000  bootloader.bin \\" && \
    echo "        0x8000  partition-table.bin \\" && \
    echo "        0x10000 ovms3.bin" && \
    echo "════════════════════════════════════════" \
'
