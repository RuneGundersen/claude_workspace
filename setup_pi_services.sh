#!/bin/bash
# Run this once on the Pi to install Tailscale and set up systemd services
# Usage: bash setup_pi_services.sh

set -e
cd ~/claude_workspace
git pull

echo "=== Installing Tailscale ==="
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

echo ""
echo "=== Installing systemd services ==="

sudo cp HeatPumps/heatpumps.service /etc/systemd/system/
sudo cp OVMS/ovms.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable heatpumps
sudo systemctl enable ovms

sudo systemctl restart heatpumps
sudo systemctl restart ovms

echo ""
echo "=== Status ==="
sudo systemctl status heatpumps --no-pager
sudo systemctl status ovms --no-pager

echo ""
echo "=== Tailscale IP ==="
tailscale ip
echo ""
echo "Done! Install Tailscale on your phone and laptop too:"
echo "  Phone:  https://tailscale.com/download/android"
echo "  Laptop: https://tailscale.com/download/windows"
