# Fiat 500e Cell Voltage Firmware

Custom OVMS firmware fork adding per-cell voltage monitoring via UDS polling
of the BPCM (Battery Pack Control Module).

---

## What's added

| Metric | MQTT topic | Description |
|--------|-----------|-------------|
| `v.b.c.voltage[0]`…`[95]` | `EV88283metric/v/b/c/voltage/0`…`/95` | Per-cell voltage (V) |
| `xse.b.cell_did` | `EV88283metric/xse/b/cell_did` | Active cell DID |
| `xse.b.cell_count` | `EV88283metric/xse/b/cell_count` | Cells decoded last cycle |

Shell commands added:
- `xse cells` — print all 96 cell voltages on the OVMS console
- `xse scan auto` — probe known Bosch BMS DIDs to find cell voltage DID
- `xse scan <start_hex> <end_hex>` — probe a specific DID range
- `xse scan stop` — abort scan

---

## Build

### Prerequisites

OVMS firmware builds under Linux/macOS (or WSL2 on Windows).
You need the ESP-IDF toolchain and the full OVMS repo.

```bash
# 1. Clone OVMS (shallow to save time)
git clone --depth 1 https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3.git ovms3
cd ovms3

# 2. Bootstrap the ESP32 toolchain (first time only, ~10 min)
cd vehicle/OVMS.V3
. ./idf.sh    # sets up IDF environment

# 3. Drop in the modified plugin
cp /path/to/this/firmware/vehicle_fiat500e.h  components/vehicle_fiat500/src/
cp /path/to/this/firmware/vehicle_fiat500e.cpp components/vehicle_fiat500/src/

# 4. Build
make -j$(nproc)
# Firmware image: build/ovms3.bin  (or firmware/ovms3.bin)
```

### Docker (easiest on Windows)

```powershell
# In WSL2 or Git Bash:
docker run --rm -v "$PWD/ovms3:/ovms3" \
  --entrypoint /bin/bash \
  openvehicles/ovms-build:latest \
  -c "cd /ovms3/vehicle/OVMS.V3 && . ./idf.sh && make -j4"
```

### Flash

With the OVMS module connected over USB (CP2102 port):

```bash
make flash ESPPORT=/dev/ttyUSB0
# or via OVMS web UI: Config → Firmware → Upload OTA
```

---

## Step 1: Discover the cell voltage DID

**The exact UDS DID for per-cell voltages is not publicly documented for the
Fiat 500e.** You need to find it by scanning the BPCM while connected to the
car.

Connect to the OVMS console (USB, SSH, or the web shell), then:

```
# Quick scan of most likely DIDs (takes ~30 seconds):
xse scan auto

# When that completes, scan the cell data block:
xse scan 4000 4040

# You can also scan the extended range:
xse scan 2000 2100
```

### What to look for

A response that contains cell voltage data will:
- Return **≥ 192 bytes** (96 cells × 2 bytes each)
- Contain values in the range **0x0A00–0x1068** (2560–4200 in decimal)
  which map to 2.56–4.20 V per cell

Example of a valid response (3.7 V average, 96 cells):
```
DID 0x4020 → 192 bytes: 0E74 0E74 0E78 0E70 0E72 ...
             ^^^^ = 0x0E74 = 3700 mV = 3.700 V
```

### Step 2: Configure the DID

Once found (e.g. DID `0x4020`):

```
config set xse bpcm.cell_did 0x4020
```

Then restart the vehicle module:

```
vehicle module reload
```

Cell voltages will now be polled every 30 seconds while driving (every 60 s
while charging) and published to MQTT automatically.

---

## Step 3: Verify

```
xse cells
```

Expected output:
```
Cell DID: 0x4020   Cells decoded last cycle: 96

[00–07]  3.712V  3.714V  3.710V  3.715V  3.711V  3.708V  3.713V  3.712V
[08–15]  3.709V  3.715V  3.714V  3.711V  3.708V  3.712V  3.715V  3.710V
...
```

Check MQTT topics in the webapp's Battery panel — it will show the cell
voltage heatmap once the `xse.b.cell_did` metric is non-zero.

---

## Decoding notes

### Default encoding assumed

The firmware assumes cells are encoded as **big-endian uint16 millivolts**,
which is the standard Bosch BMS encoding:

```
bytes[i*2]<<8 | bytes[i*2+1]  →  millivolts  →  divide by 1000 → volts
```

### If you get wrong values

If cell voltages look wrong (e.g. all the same, or all zero, or out-of-range),
the encoding may differ. Common alternatives:

| Encoding | Scale | Formula |
|----------|-------|---------|
| `uint16 mV, big-endian` | 1 | `mv / 1000.0` (default) |
| `uint16 mV, little-endian` | 1 | swap bytes first |
| `uint16 × 0.1 mV` | 0.1 | `(mv * 0.1) / 1000.0` |
| `uint8, 4.2V/255 scale` | — | `v / 255.0 * 4.2` |

Adjust `FT5E_CELL_MV_SCALE` in `vehicle_fiat500e.cpp` if needed.

---

## BPCM UDS addresses

| Parameter | Value |
|-----------|-------|
| Bus | CAN1 (C-CAN, 500 kbps) |
| CAN ID format | 29-bit extended |
| Tester → BPCM TX | `0x18DA42F1` |
| BPCM → Tester RX | `0x18DAF142` |
| UDS service | `0x22` ReadDataByIdentifier |
| Protocol | ISO 15765-2 (ISO-TP) |

---

## Files

```
firmware/
├── vehicle_fiat500e.h    — modified header (drop into components/vehicle_fiat500/src/)
├── vehicle_fiat500e.cpp  — modified implementation
└── README_CELLS.md       — this file
```

The `CMakeLists.txt` and `component.mk` in the original repo directory are
unchanged — you do not need to modify them.
