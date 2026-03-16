#!/bin/bash
# Run once on the Raspberry Pi to install the Flexit daemon
# Tested on Raspberry Pi OS Lite (Bookworm / Bullseye)

set -e

echo "=== Installing Flexit daemon dependencies ==="
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv

# Create venv
python3 -m venv /opt/flexit/venv
/opt/flexit/venv/bin/pip install --upgrade pip
/opt/flexit/venv/bin/pip install -r /opt/flexit/requirements.txt

# Copy files
sudo mkdir -p /opt/flexit
sudo cp flexit_daemon.py flexit_config.py requirements.txt /opt/flexit/

echo ""
echo "=== IMPORTANT: edit /opt/flexit/flexit_config.py and set MQTT_PASSWORD ==="
echo ""

# Install systemd service
sudo tee /etc/systemd/system/flexit.service > /dev/null <<EOF
[Unit]
Description=Flexit UNI4 Modbus-MQTT daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/flexit
ExecStart=/opt/flexit/venv/bin/python3 flexit_daemon.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable flexit
echo "=== Service installed. Start with: sudo systemctl start flexit ==="
echo "=== Logs: journalctl -u flexit -f ==="
