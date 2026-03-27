#!/usr/bin/env bash
# =============================================================================
# install.sh — Boot config + autostart setup for analog_display.py
# Raspberry Pi 3 Model B + DFRobot Arduino Expansion Shield v2.0 (DFR0327)
#
# Run as root:  sudo bash install.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOT_CONFIG="/boot/config.txt"
SERVICE_NAME="analog-display"
SERVICE_SRC="${SCRIPT_DIR}/analog-display.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Helper ────────────────────────────────────────────────────────────────────
info()  { echo -e "\e[32m[INFO]\e[0m  $*"; }
warn()  { echo -e "\e[33m[WARN]\e[0m  $*"; }
error() { echo -e "\e[31m[ERROR]\e[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Please run with sudo: sudo bash install.sh"

# ── 1. /boot/config.txt — I2C entries ────────────────────────────────────────
info "Checking /boot/config.txt for I2C settings..."

apply_boot_param() {
    local param="$1"
    local key="${param%%=*}"
    if grep -qE "^${key}" "${BOOT_CONFIG}"; then
        warn "${key} already set in ${BOOT_CONFIG} — skipping."
    else
        echo "${param}" >> "${BOOT_CONFIG}"
        info "Added: ${param}"
    fi
}

# Ensure there's a section header
if ! grep -q "# DFRobot DFR0327" "${BOOT_CONFIG}"; then
    echo "" >> "${BOOT_CONFIG}"
    echo "# DFRobot DFR0327 — I2C for ADS1115 analog input" >> "${BOOT_CONFIG}"
fi

apply_boot_param "dtparam=i2c_arm=on"
apply_boot_param "dtparam=i2c_arm_baudrate=400000"

# Load i2c-dev module on every boot
if ! grep -q "i2c-dev" /etc/modules; then
    echo "i2c-dev" >> /etc/modules
    info "Added i2c-dev to /etc/modules."
else
    warn "i2c-dev already in /etc/modules — skipping."
fi

# ── 2. Python dependencies ────────────────────────────────────────────────────
info "Installing Python dependencies..."
pip3 install --quiet -r "${SCRIPT_DIR}/requirements.txt"
info "Python packages installed."

# ── 3. systemd service ────────────────────────────────────────────────────────
info "Installing systemd service..."

# Patch the WorkingDirectory and ExecStart in the service file to match the
# actual location of this repo on this machine.
INSTALL_USER="${SUDO_USER:-pi}"
INSTALL_HOME=$(eval echo "~${INSTALL_USER}")

sed \
    -e "s|User=pi|User=${INSTALL_USER}|g" \
    -e "s|/home/pi/.Xauthority|${INSTALL_HOME}/.Xauthority|g" \
    -e "s|/home/pi/claude_workspace/RpiWShield|${SCRIPT_DIR}|g" \
    "${SERVICE_SRC}" > "${SERVICE_DEST}"

chmod 644 "${SERVICE_DEST}"
info "Service file written to ${SERVICE_DEST}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
info "Service enabled — will start automatically on next graphical boot."

# Offer to start now
read -r -p "Start the service now? [y/N] " reply
if [[ "${reply,,}" == "y" ]]; then
    systemctl start "${SERVICE_NAME}.service"
    info "Service started. Check status with:  systemctl status ${SERVICE_NAME}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
info "Installation complete."
info "Verify I2C bus after reboot:  sudo i2cdetect -y 1"
info "View live logs:               journalctl -fu ${SERVICE_NAME}"
info "Stop autostart:               sudo systemctl disable ${SERVICE_NAME}"
