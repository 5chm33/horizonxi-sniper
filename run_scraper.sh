#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "============================================"
echo "  HorizonXI Bazaar + AH Sniper  v2.0"
echo "  CEO Edition - Bazaar AND Auction House"
echo "============================================"
echo ""

# Install deps
echo "[INFO] Checking dependencies..."
pip3 install requests plyer --quiet 2>/dev/null || true

# Install tkinter on Linux if missing
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "[INFO] Installing tkinter..."
    sudo apt-get install -y python3-tk 2>/dev/null || true
fi

echo "[INFO] Starting HorizonXI Sniper..."
echo ""
cd "$SCRIPT_DIR"
python3 horizonxi_scraper.py
