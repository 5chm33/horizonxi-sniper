# ⚔️ HorizonXI Bazaar Sniper — CEO Edition

A SOTA (State-of-the-Art) real-time bazaar price monitor for the [HorizonXI](https://horizonxi.com) FFXI private server. Runs 24/7, fires instant desktop popup alerts when underpriced items appear, tracks full metrics, and lets you manage a dynamic watchlist — all externally via the public API, with zero in-game interaction.

---

## Features

| Feature | Details |
|---|---|
| **24/7 Auto-Scan** | Polls `api.horizonxi.com` every 60 seconds automatically |
| **Instant Popup Alerts** | In-app alert window + native OS desktop notification fires the moment a deal is found |
| **Default Watchlist** | Lungo-Nango Jadeshell, Montiont Silverpiece, 100 Byne Bill — all monitored at ≤ 10,000 gil |
| **Dynamic Watchlist** | Add, remove, enable/disable, and edit price caps for any item at any time |
| **Search & Add** | Search live bazaar data by name, see current listings count and min price, then add with one click |
| **Metrics Dashboard** | Total finds, total scans, last scan time, live listing count, per-item find counts |
| **Finds Log** | Full timestamped history of every deal found — exportable to CSV |
| **Persistent State** | Watchlist and finds log saved to disk and restored on restart |
| **No Bot Detection Risk** | Reads the public website API only — no game client interaction whatsoever |

---

## Quick Start

### Windows

1. Install [Python 3.10+](https://python.org/downloads/) — **check "Add to PATH"** during install
2. Double-click `run_scraper.bat`
3. Dependencies install automatically on first run

### Linux / macOS

```bash
# Install dependencies (first run only)
pip3 install requests plyer

# On Ubuntu/Debian, also install tkinter if missing:
sudo apt-get install -y python3-tk

# Launch
bash run_scraper.sh
# or directly:
python3 horizonxi_scraper.py
```

---

## Interface Guide

### 🎯 Watchlist Tab

The main control panel. Shows all items being monitored with their current status.

- **Quick Add row** at the top: manually enter an Item Key, Display Name, and Max Price to add any item instantly
- **Toggle On/Off**: temporarily disable monitoring for a selected item without removing it
- **Edit Max Price**: change the price threshold for any item
- **Remove**: permanently delete from watchlist

> **Item Key format**: lowercase with underscores, e.g. `lungo-nango_jadeshell`, `fire_crystal`, `behemoth_hide`

### 📊 Metrics Tab

Live statistics dashboard showing:
- Total finds across all time
- Total number of scans performed
- Time of last scan
- Number of live bazaar listings fetched
- Per-item find counts with visual cards
- Recent finds table (last 20 deals)

### 📋 Finds Log Tab

Complete timestamped history of every deal detected. Supports:
- **Export CSV**: saves `finds_export.csv` in the same folder
- **Clear Log**: wipe history (with confirmation)

### 🔍 Search & Add Tab

Search the live bazaar by item name:
1. Type a partial item name (e.g. `crystal`, `byne`, `behemoth`)
2. Press Enter or click **Search**
3. Results show all matching items currently listed in bazaar, with listing count and minimum price
4. Select a row, set your **Max Price**, click **➕ Add to Checklist**
5. You're automatically switched to the Watchlist tab to confirm

---

## Alert System

When a deal is found:

1. **In-app popup** appears immediately on top of all windows, showing item name, price, seller, zone, and quantity
2. **Native OS desktop notification** fires (Windows toast / Linux libnotify) — visible even if the app is minimised
3. **Status bar** updates with the find time
4. **Metrics** update automatically

Popups auto-dismiss after 45 seconds, or click **Dismiss** manually.

---

## Files

| File | Purpose |
|---|---|
| `horizonxi_scraper.py` | Main application — all code in one file |
| `run_scraper.bat` | Windows launcher |
| `run_scraper.sh` | Linux/macOS launcher |
| `requirements.txt` | Python dependencies |
| `watchlist.json` | Auto-created — persists your watchlist |
| `finds_log.json` | Auto-created — persists your finds history |
| `finds_export.csv` | Created when you click Export CSV |

---

## Default Watchlist Items

| Display Name | Internal Key | Default Max Price |
|---|---|---|
| Lungo-Nango Jadeshell | `lungo-nango_jadeshell` | 10,000 gil |
| Montiont Silverpiece | `montiont_silverpiece` | 10,000 gil |
| 100 Byne Bill | `one_hundred_byne_bill` | 10,000 gil |

These are the three 100-currency Dynamis items. Current market prices are ~600,000–1,200,000g, so any listing at ≤ 10,000g represents a bazaar player mistake — exactly the edge you're hunting.

---

## Customisation

Open `horizonxi_scraper.py` in any text editor and adjust these constants near the top:

```python
SCAN_INTERVAL = 60   # seconds between scans (minimum recommended: 30)
```

To change default watchlist items, edit `DEFAULT_WATCHLIST` — but note this only applies on first run (before `watchlist.json` is created). After that, use the GUI.

---

## Technical Notes

- **API endpoint**: `https://api.horizonxi.com/api/v1/items/bazaar` — returns all ~800 active bazaar listings as a JSON array
- **Fields per listing**: `name`, `bazaar` (price), `charname` (seller), `zone`, `quantity`, `online_flag`
- **Search**: performed client-side against the cached bazaar data — same approach as the HorizonXI website itself
- **No authentication required**: the API is fully public
- **Rate limiting**: one request per 60 seconds is well within safe limits

---

## Requirements

- Python 3.10 or higher
- `requests` — HTTP client
- `plyer` — cross-platform desktop notifications
- `tkinter` — GUI (bundled with Python on Windows/macOS; `python3-tk` package on Linux)
