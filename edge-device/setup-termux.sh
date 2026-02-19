#!/data/data/com.termux/files/usr/bin/bash
# Sotto Edge Device — Termux Setup Script
# Run this after installing Termux and Termux:API on your Android phone.
#
# Prerequisites:
#   1. Install Termux (Play Store or F-Droid — use the same source for both)
#   2. Install Termux:API from the same source (for microphone and audio access)
#   3. Grant microphone permission to Termux when prompted
#
# Usage:
#   pkg install git
#   git clone https://github.com/YourBr0ther/Sotto.git
#   cd Sotto/edge-device
#   bash setup-termux.sh

set -e

echo "=== Sotto Edge Device — Termux Setup ==="
echo ""

# Update package index
echo "[1/5] Updating Termux packages..."
pkg update -y

# Install system dependencies (numpy via pkg, not pip — avoids native build failures)
echo "[2/5] Installing system dependencies..."
pkg install -y python python-numpy pulseaudio termux-api

# Install pure-Python dependencies via pip
echo "[3/5] Installing Python dependencies..."
pip install paho-mqtt PyYAML

echo ""
echo "[4/5] Testing MQTT connectivity..."
python test_mqtt_connection.py
MQTT_EXIT=$?

if [ $MQTT_EXIT -ne 0 ]; then
    echo ""
    echo "MQTT connection failed. Check that:"
    echo "  - Your phone is on the same network as the k3s cluster"
    echo "  - The MQTT broker is running (kubectl get pods -n sotto)"
    echo "  - config.yaml has the correct broker_host and broker_port"
    echo ""
    echo "You can edit config.yaml and re-run: python test_mqtt_connection.py"
    exit 1
fi

echo ""
echo "[5/5] Setup complete!"
echo ""
echo "To start the edge device:"
echo "  python main.py"
echo ""
echo "Optional: Install wake word detection (large download, may not work on all devices):"
echo "  pip install openwakeword>=0.6.0"
echo ""
echo "Tip: Use 'termux-wake-lock' to prevent Android from killing Termux in the background."
