"""
HorizonXI Bazaar + AH Sniper  ⚔️  v2.6
=======================================
Changes from v2.5:
  • PSXI.gg transaction stream: polls /s/horizonxi/ah/recent-transactions?after={id}
    every 5 s for new completed AH sales — no auth required, buyer name included
  • PSXI.gg item search: Search & Add tab now queries PSXI for live stock + last price
  • AH stock-delta detection: alerts only when stock INCREASES (new listing appeared)
  • Buyer name shown in all AH alerts, metrics, and log rows
  • Highlight blink fix carried forward from v2.5
  • PUBLIC RELEASE — no personal credentials bundled

Requirements:  requests, plyer
Python:        3.10+
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
import json
import time
import datetime
import os
import csv
import signal
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────
BASE_API        = "https://api.horizonxi.com/api/v1"
BAZAAR_API      = f"{BASE_API}/items/bazaar"
LOGIN_API       = f"{BASE_API}/accounts/login"
ITEMS_API       = f"{BASE_API}/items"

# PSXI endpoints (no auth required)
PSXI_BASE       = "https://www.psxi.gg/s/horizonxi/ah"
PSXI_TXNS       = f"{PSXI_BASE}/recent-transactions"
PSXI_LISTINGS   = f"{PSXI_BASE}/recent-listings"
PSXI_SEARCH     = f"{PSXI_BASE}/search"

BAZAAR_INTERVAL = 5       # seconds between bazaar scans
AH_INTERVAL     = 15      # seconds between horizonxi.com AH scans
PSXI_INTERVAL   = 5       # seconds between PSXI transaction stream polls
TOKEN_TTL       = 3600 * 6
MAX_RETRIES     = 3
RETRY_DELAY     = 4
DEDUP_TTL       = 3600 * 4   # 4 hours — silence same listing for 4 h

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE   = os.path.join(SCRIPT_DIR, "watchlist.json")
LOG_FILE    = os.path.join(SCRIPT_DIR, "finds_log.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

DEFAULT_WATCHLIST = [
    {"key": "lungo-nango_jadeshell", "display": "Lungo-Nango Jadeshell",
     "max_price": 10000, "watch_bazaar": True, "watch_ah": True,
     "ah_stack_mode": "single"},
    {"key": "montiont_silverpiece",  "display": "Montiont Silverpiece",
     "max_price": 10000, "watch_bazaar": True, "watch_ah": True,
     "ah_stack_mode": "single"},
    {"key": "one_hundred_byne_bill", "display": "100 Byne Bill",
     "max_price": 10000, "watch_bazaar": True, "watch_ah": True,
     "ah_stack_mode": "single"},
]

# ─────────────────────────────────────────────────────────────────
# THEMES
# ─────────────────────────────────────────────────────────────────
THEMES = {
    "Dark": {
        "BG": "#0d0f1a", "BG2": "#141728", "BG3": "#1c2035",
        "ACCENT": "#5b8dee", "ACCENT2": "#3ecf8e",
        "WARN": "#f5a623", "DANGER": "#e74c3c",
        "TEXT": "#e8eaf0", "TEXT_DIM": "#7a8099",
        "GOLD": "#ffd700", "GREEN": "#2ecc71",
        "PANEL_BG": "#181c2e", "BORDER": "#2a2f4a",
        "HDR_BG": "#0a0c16", "AH_COLOR": "#c084fc",
        "SEL_BG": "#5b8dee", "SEL_FG": "#ffffff",
    },
    "Midnight": {
        "BG": "#06080f", "BG2": "#0c0e1a", "BG3": "#12152a",
        "ACCENT": "#7c6af7", "ACCENT2": "#22d3ee",
        "WARN": "#fb923c", "DANGER": "#f43f5e",
        "TEXT": "#e2e8f0", "TEXT_DIM": "#64748b",
        "GOLD": "#fbbf24", "GREEN": "#34d399",
        "PANEL_BG": "#0f1120", "BORDER": "#1e2240",
        "HDR_BG": "#030408", "AH_COLOR": "#a78bfa",
        "SEL_BG": "#7c6af7", "SEL_FG": "#ffffff",
    },
    "Ember": {
        "BG": "#1a0d0d", "BG2": "#241414", "BG3": "#2e1a1a",
        "ACCENT": "#f97316", "ACCENT2": "#fbbf24",
        "WARN": "#f59e0b", "DANGER": "#dc2626",
        "TEXT": "#fef3c7", "TEXT_DIM": "#92400e",
        "GOLD": "#fcd34d", "GREEN": "#86efac",
        "PANEL_BG": "#1f1010", "BORDER": "#3b1f1f",
        "HDR_BG": "#0f0808", "AH_COLOR": "#fb7185",
        "SEL_BG": "#f97316", "SEL_FG": "#1a0d0d",
    },
    "Forest": {
        "BG": "#0a140d", "BG2": "#101c13", "BG3": "#162419",
        "ACCENT": "#4ade80", "ACCENT2": "#34d399",
        "WARN": "#facc15", "DANGER": "#f87171",
        "TEXT": "#dcfce7", "TEXT_DIM": "#4b7a55",
        "GOLD": "#fde68a", "GREEN": "#86efac",
        "PANEL_BG": "#0d1810", "BORDER": "#1e3a22",
        "HDR_BG": "#060e08", "AH_COLOR": "#67e8f9",
        "SEL_BG": "#4ade80", "SEL_FG": "#0a140d",
    },
    "Slate": {
        "BG": "#0f172a", "BG2": "#1e293b", "BG3": "#334155",
        "ACCENT": "#38bdf8", "ACCENT2": "#2dd4bf",
        "WARN": "#fbbf24", "DANGER": "#f87171",
        "TEXT": "#f1f5f9", "TEXT_DIM": "#94a3b8",
        "GOLD": "#fde68a", "GREEN": "#4ade80",
        "PANEL_BG": "#1e293b", "BORDER": "#475569",
        "HDR_BG": "#020617", "AH_COLOR": "#c084fc",
        "SEL_BG": "#38bdf8", "SEL_FG": "#0f172a",
    },
}

_T = THEMES["Dark"].copy()

def _apply_theme(name: str):
    global _T
    _T = THEMES.get(name, THEMES["Dark"]).copy()


# ─────────────────────────────────────────────────────────────────
# DESKTOP NOTIFICATION
# ─────────────────────────────────────────────────────────────────

def _desktop_notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="HorizonXI Sniper", timeout=10)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# PERSISTENT ALERT OVERLAY
# ─────────────────────────────────────────────────────────────────

class AlertOverlay:
    """
    Single compact overlay window.
    - Opens on first find; updates in-place on subsequent finds.
    - Fully resizable (both axes).
    - Watchlist changes propagate immediately via push().
    - Never auto-closes; stays until user clicks Dismiss.
    """

    def __init__(self, root: tk.Tk):
        self.root  = root
        self._win: Optional[tk.Toplevel] = None
        self._tree: Optional[ttk.Treeview] = None
        self._hdr_lbl: Optional[tk.Label] = None
        self._all_finds: list = []
        self._lock = threading.Lock()

    def _build(self):
        win = tk.Toplevel(self.root)
        win.title("🎯 SNIPE ALERT")
        win.configure(bg=_T["BG"])
        win.geometry("640x220+30+30")
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._dismiss)

        tk.Frame(win, bg=_T["DANGER"], height=3).pack(fill="x")

        hdr = tk.Frame(win, bg=_T["BG"], pady=4)
        hdr.pack(fill="x", padx=8)

        tk.Label(hdr, text="🎯  DEAL FOUND!",
                 font=("Segoe UI", 11, "bold"),
                 bg=_T["BG"], fg=_T["GOLD"]).pack(side="left")

        self._hdr_lbl = tk.Label(hdr, text="",
                                  font=("Segoe UI", 8),
                                  bg=_T["BG"], fg=_T["TEXT_DIM"])
        self._hdr_lbl.pack(side="left", padx=10)

        tk.Button(hdr, text="✕ Dismiss",
                  command=self._dismiss,
                  bg=_T["BG3"], fg=_T["TEXT_DIM"],
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  cursor="hand2", padx=8, pady=1
                  ).pack(side="right")

        frm = tk.Frame(win, bg=_T["BG2"])
        frm.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        style = ttk.Style(win)
        style.theme_use("default")
        style.configure("Alert.Treeview",
                         background=_T["BG2"], foreground=_T["TEXT"],
                         fieldbackground=_T["BG2"], rowheight=22,
                         font=("Segoe UI", 9))
        style.configure("Alert.Treeview.Heading",
                         background=_T["BG3"], foreground=_T["ACCENT"],
                         font=("Segoe UI", 8, "bold"), relief="flat")
        style.map("Alert.Treeview",
                  background=[("selected", "!focus", _T["SEL_BG"]),
                               ("selected", "focus",  _T["SEL_BG"]),
                               ("selected",           _T["SEL_BG"])],
                  foreground=[("selected", "!focus", _T["SEL_FG"]),
                               ("selected", "focus",  _T["SEL_FG"]),
                               ("selected",           _T["SEL_FG"])])

        # Buyer column added for AH transaction finds
        cols = ("Seller", "Src", "Item", "Price", "Buyer / Zone", "Stack")
        tree = ttk.Treeview(frm, columns=cols, show="headings",
                             style="Alert.Treeview", takefocus=False)
        tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        sb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sb.set)

        for col, w, a in zip(cols,
                              [110, 55, 155, 80, 150, 60],
                              ["w","center","w","center","w","center"]):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor=a, minwidth=40, stretch=True)

        tree.tag_configure("bazaar", foreground=_T["ACCENT2"])
        tree.tag_configure("ah",     foreground=_T["AH_COLOR"])
        tree.tag_configure("psxi",   foreground=_T["GOLD"])

        self._win  = win
        self._tree = tree

    def _dismiss(self):
        with self._lock:
            self._all_finds.clear()
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win  = None
        self._tree = None

    def _rebuild_table(self):
        if not self._tree:
            return
        self._tree.delete(*self._tree.get_children())
        for f in self._all_finds:
            src = f.get("source", "bazaar").upper()
            buyer_zone = f.get("buyer", "") or f.get("zone", "—")
            if buyer_zone:
                buyer_zone = buyer_zone.replace("_", " ")
            stack_lbl = f.get("stack_label", "—")
            self._tree.insert("", "end", values=(
                f.get("seller", "—"),
                src,
                f["display_name"],
                f"{f['price']:,}g" if f.get("price") else "—",
                buyer_zone,
                stack_lbl,
            ), tags=(src.lower(),))

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        n  = len(self._all_finds)
        if self._hdr_lbl:
            self._hdr_lbl.config(text=f"{n} listing(s) — updated {ts}")

    def push(self, new_finds: list):
        with self._lock:
            self._all_finds.extend(new_finds)
        if self._win is None or not self._win.winfo_exists():
            self._build()
        self._rebuild_table()
        try:
            self._win.lift()
            self._win.focus_force()
        except Exception:
            pass

    def sync_watchlist(self, watchlist):
        active_keys = {w.key for w in watchlist if w.enabled}
        with self._lock:
            self._all_finds = [
                f for f in self._all_finds
                if f.get("item_key") in active_keys
            ]
        if self._win and self._win.winfo_exists():
            self._rebuild_table()

    def apply_theme(self):
        if self._win and self._win.winfo_exists():
            saved = list(self._all_finds)
            self._dismiss()
            with self._lock:
                self._all_finds = saved
            if saved:
                self._build()
                self._rebuild_table()


# ─────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────

@dataclass
class WatchItem:
    key:           str
    display:       str
    max_price:     int
    enabled:       bool = True
    watch_bazaar:  bool = True
    watch_ah:      bool = True
    ah_stack_mode: str  = "single"   # "single" | "stack" | "both"
    find_count:    int  = 0
    last_seen:     Optional[str] = None
    last_price:    Optional[int] = None
    last_seller:   Optional[str] = None
    last_source:   Optional[str] = None
    last_buyer:    Optional[str] = None   # NEW: buyer name from PSXI


@dataclass
class FindRecord:
    timestamp:    str
    source:       str
    item_key:     str
    display_name: str
    price:        int
    seller:       str
    zone:         str
    quantity:     int
    buyer:        str = ""          # NEW: buyer name (PSXI AH transactions)
    stack_label:  str = "Single"    # NEW: "Single" | "Stack"


# ─────────────────────────────────────────────────────────────────
# AUTH MANAGER
# ─────────────────────────────────────────────────────────────────

class AuthManager:
    def __init__(self):
        self._token:      Optional[str] = None
        self._token_time: float         = 0.0
        self._username:   str           = ""
        self._password:   str           = ""
        self._lock                      = threading.Lock()
        self._headers_base = {
            "User-Agent":   "HorizonXI-Sniper/2.6",
            "Accept":       "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin":       "https://horizonxi.com",
            "Referer":      "https://horizonxi.com/login",
        }
        self._load_config()

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    cfg = json.load(f)
                self._username = cfg.get("username", "")
                self._password = cfg.get("password", "")
            except Exception:
                pass

    def save_config(self, username: str, password: str):
        self._username = username
        self._password = password
        self._token    = None
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"username": username, "password": password}, f)
        except Exception as e:
            print(f"[CONFIG SAVE ERROR] {e}")

    @property
    def username(self) -> str:
        return self._username

    @property
    def password(self) -> str:
        return self._password

    @property
    def has_credentials(self) -> bool:
        return bool(self._username and self._password)

    def get_token(self, force_refresh: bool = False) -> Optional[str]:
        with self._lock:
            if (not force_refresh
                    and self._token
                    and (time.time() - self._token_time) < TOKEN_TTL):
                return self._token
            if not self.has_credentials:
                return None
            try:
                resp = requests.post(
                    LOGIN_API,
                    json={"user": self._username, "pass": self._password},
                    headers=self._headers_base,
                    timeout=15
                )
                if resp.status_code == 200:
                    raw = resp.text.strip().strip('"')
                    if raw and len(raw) > 20:
                        self._token      = raw
                        self._token_time = time.time()
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        print(f"[AUTH] Token refreshed at {ts}")
                        return self._token
                    try:
                        data = resp.json()
                        token = (data.get("token") or data.get("access_token")
                                 or data.get("jwt"))
                        if token:
                            self._token      = token
                            self._token_time = time.time()
                            ts = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"[AUTH] Token refreshed at {ts}")
                            return self._token
                    except Exception:
                        pass
                print(f"[AUTH FAIL] HTTP {resp.status_code}: {resp.text[:80]}")
            except Exception as e:
                print(f"[AUTH ERROR] {e}")
            return None

    def auth_headers(self, force_refresh: bool = False) -> dict:
        token = self.get_token(force_refresh=force_refresh)
        h = {
            "User-Agent": "HorizonXI-Sniper/2.6",
            "Accept":     "application/json, text/plain, */*",
            "Origin":     "https://horizonxi.com",
            "Referer":    "https://horizonxi.com/",
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h


# ─────────────────────────────────────────────────────────────────
# BAZAAR SCRAPER ENGINE
# ─────────────────────────────────────────────────────────────────

class BazaarScraper:
    def __init__(self):
        self.auth            = AuthManager()
        self.watchlist:      list[WatchItem] = []
        self.finds_log:      list[FindRecord] = []
        self.scan_count      = 0
        self.bazaar_scan_count = 0
        self.ah_scan_count   = 0
        self.psxi_scan_count = 0
        self.last_scan_time: Optional[str] = None
        self.last_bazaar_count = 0
        self.ah_status       = "Initialising…"
        self.psxi_status     = "Initialising…"
        self.running         = False
        self._thread: Optional[threading.Thread] = None
        self._lock           = threading.Lock()
        self._seen_cache:    dict[str, float] = {}
        self._cached_bazaar: list = []
        self._last_ah_scan   = 0.0
        self._last_psxi_scan = 0.0

        # PSXI transaction stream state
        self._psxi_last_txn_id: int = 0   # highest txn id seen so far
        self._psxi_stock_cache: dict[str, int] = {}  # item_name -> last known stock

        self.on_finds_cb = None
        self.on_scan_cb  = None

        self._load()

    # ── Persistence ───────────────────────────────────────────────

    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE) as f:
                    raw = json.load(f)
                if isinstance(raw, list):
                    items = raw
                else:
                    items = raw.get("watchlist", [])
                self.watchlist = [
                    WatchItem(**{k: v for k, v in r.items()
                                 if k in WatchItem.__dataclass_fields__})
                    for r in items
                ]
            except Exception as e:
                print(f"[LOAD ERROR] {e}")
        if not self.watchlist:
            self.watchlist = [WatchItem(**d) for d in DEFAULT_WATCHLIST]

        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE) as f:
                    raw = json.load(f)
                self.finds_log = [
                    FindRecord(**{k: v for k, v in r.items()
                                  if k in FindRecord.__dataclass_fields__})
                    for r in raw
                ]
            except Exception:
                pass

    def save(self):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump({"watchlist": [
                    {k: v for k, v in w.__dict__.items()}
                    for w in self.watchlist
                ]}, f, indent=2)
        except Exception as e:
            print(f"[SAVE ERROR] {e}")
        try:
            with open(LOG_FILE, "w") as f:
                json.dump([r.__dict__ for r in self.finds_log[-5000:]], f)
        except Exception as e:
            print(f"[LOG SAVE ERROR] {e}")

    # ── Watchlist CRUD ────────────────────────────────────────────

    def add_item(self, key, display, max_price,
                 watch_bazaar=True, watch_ah=True,
                 ah_stack_mode="single") -> bool:
        if any(w.key == key for w in self.watchlist):
            return False
        self.watchlist.append(WatchItem(
            key=key, display=display, max_price=max_price,
            watch_bazaar=watch_bazaar, watch_ah=watch_ah,
            ah_stack_mode=ah_stack_mode))
        self.save()
        return True

    def cycle_stack_mode(self, key: str):
        modes = ["single", "stack", "both"]
        for w in self.watchlist:
            if w.key == key:
                idx = modes.index(w.ah_stack_mode) if w.ah_stack_mode in modes else 0
                w.ah_stack_mode = modes[(idx + 1) % len(modes)]
        self.save()

    def remove_item(self, key: str):
        self.watchlist = [w for w in self.watchlist if w.key != key]
        self.save()

    def toggle_item(self, key: str):
        for w in self.watchlist:
            if w.key == key:
                w.enabled = not w.enabled
        self.save()

    def toggle_source(self, key: str, source: str):
        for w in self.watchlist:
            if w.key == key:
                if source == "bazaar":
                    w.watch_bazaar = not w.watch_bazaar
                else:
                    w.watch_ah = not w.watch_ah
        self.save()

    def update_price(self, key: str, price: int):
        for w in self.watchlist:
            if w.key == key:
                w.max_price = price
        self.save()

    # ── Deduplication ─────────────────────────────────────────────

    def _dedup_key(self, source, item_key, seller, value) -> str:
        return f"{source}|{item_key}|{seller}|{value}"

    def _is_new(self, dk: str) -> bool:
        now = time.time()
        exp = self._seen_cache.get(dk, 0)
        if now < exp:
            return False
        self._seen_cache[dk] = now + DEDUP_TTL
        return True

    def _expire_cache(self):
        now = time.time()
        self._seen_cache = {k: v for k, v in self._seen_cache.items() if v > now}

    # ── HTTP helpers ──────────────────────────────────────────────

    _PSXI_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json, text/plain, */*",
        "Referer":    "https://www.psxi.gg/s/horizonxi/ah",
        "Origin":     "https://www.psxi.gg",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def _get(self, url, params=None, auth=False, retry=MAX_RETRIES,
             extra_headers=None):
        for attempt in range(retry):
            try:
                if auth:
                    headers = self.auth.auth_headers()
                elif extra_headers:
                    headers = extra_headers
                else:
                    headers = {
                        "User-Agent": "HorizonXI-Sniper/2.6",
                        "Accept":     "application/json, text/plain, */*",
                    }
                resp = requests.get(url, params=params,
                                    headers=headers, timeout=15)
                if resp.status_code == 401 and auth:
                    headers = self.auth.auth_headers(force_refresh=True)
                    resp = requests.get(url, params=params,
                                        headers=headers, timeout=15)
                if resp.status_code == 200 and resp.content:
                    return resp
                if resp.status_code not in (200, 401):
                    print(f"[HTTP {resp.status_code}] {url}")
            except requests.exceptions.SSLError as e:
                print(f"[SSL RETRY {attempt+1}/{retry}] {e}")
            except requests.exceptions.ConnectionError as e:
                print(f"[CONN RETRY {attempt+1}/{retry}] {e}")
            except Exception as e:
                print(f"[FETCH ERROR] {e}")
                return None
            if attempt < retry - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        return None

    # ── Bazaar fetch ──────────────────────────────────────────────

    def _fetch_bazaar(self) -> Optional[list]:
        resp = self._get(BAZAAR_API)
        if resp is None:
            return None
        try:
            data = resp.json()
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"[BAZAAR JSON ERROR] {e} — body: {resp.text[:80]}")
        return None

    # ── PSXI transaction stream ───────────────────────────────────

    def _fetch_psxi_transactions(self) -> list:
        """
        Poll PSXI recent-transactions with ?after={last_id}.
        Returns only NEW transactions since last poll.
        On first call (last_id=0) seeds the cursor without alerting.
        """
        params = {}
        if self._psxi_last_txn_id > 0:
            params["after"] = self._psxi_last_txn_id

        resp = self._get(PSXI_TXNS, params=params,
                         extra_headers=self._PSXI_HEADERS)
        if resp is None:
            return []
        try:
            data = resp.json()
            # API returns {"transactions": [...]} wrapper
            if isinstance(data, dict):
                txns = data.get("transactions", data.get("data", []))
            else:
                txns = data
            if not txns:
                return []

            # Update cursor to highest id seen
            max_id = max((t.get("id", 0) for t in txns), default=0)
            if max_id > self._psxi_last_txn_id:
                self._psxi_last_txn_id = max_id

            # On seed call, return empty (just initialise cursor)
            if params.get("after") is None:
                print(f"[PSXI] Seeded transaction cursor at id={self._psxi_last_txn_id}")
                return []

            return txns
        except Exception as e:
            print(f"[PSXI TXN ERROR] {e}")
            return []

    def _fetch_psxi_listings(self) -> list:
        """Fetch recent-listings for stock-delta detection."""
        resp = self._get(PSXI_LISTINGS, extra_headers=self._PSXI_HEADERS)
        if resp is None:
            return []
        try:
            data = resp.json()
            # API returns {"listings": [...]} wrapper
            if isinstance(data, dict):
                return data.get("listings", data.get("data", []))
            return data
        except Exception as e:
            print(f"[PSXI LISTINGS ERROR] {e}")
            return []

    # ── Main scan ─────────────────────────────────────────────────

    def _scan(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_finds: list[dict] = []

        if self.scan_count % 120 == 0:
            self._expire_cache()

        # ── Bazaar ────────────────────────────────────────────────
        bazaar_data = self._fetch_bazaar()
        if bazaar_data is not None:
            self._cached_bazaar = bazaar_data
            self.bazaar_scan_count += 1
            self.last_bazaar_count = len(bazaar_data)

            for watch in self.watchlist:
                if not watch.enabled or not watch.watch_bazaar:
                    continue
                for item in bazaar_data:
                    if item["name"] != watch.key:
                        continue
                    if item["bazaar"] > watch.max_price:
                        continue
                    dk = self._dedup_key("bazaar", watch.key,
                                         item["charname"], item["bazaar"])
                    if not self._is_new(dk):
                        continue
                    rec = FindRecord(
                        timestamp=now, source="bazaar",
                        item_key=watch.key, display_name=watch.display,
                        price=item["bazaar"], seller=item["charname"],
                        zone=item["zone"], quantity=item["quantity"],
                        buyer="", stack_label="Single",
                    )
                    self.finds_log.append(rec)
                    watch.find_count  += 1
                    watch.last_seen    = now
                    watch.last_price   = item["bazaar"]
                    watch.last_seller  = item["charname"]
                    watch.last_source  = "bazaar"
                    watch.last_buyer   = ""
                    new_finds.append({
                        "source":       "bazaar",
                        "item_key":     watch.key,
                        "display_name": watch.display,
                        "price":        item["bazaar"],
                        "seller":       item["charname"],
                        "zone":         item["zone"],
                        "quantity":     item["quantity"],
                        "buyer":        "",
                        "stack_label":  "Single",
                    })

        # ── PSXI Transaction Stream ───────────────────────────────
        now_epoch = time.time()
        if (now_epoch - self._last_psxi_scan) >= PSXI_INTERVAL:
            self._last_psxi_scan = now_epoch
            txns = self._fetch_psxi_transactions()
            self.psxi_scan_count += 1
            self.psxi_status = "Active"

            # Build a normalised name → WatchItem map for fast lookup
            # PSXI uses display names like "Lungo-Nango Jadeshell"
            # We match against watch.display (case-insensitive)
            watch_by_display: dict[str, WatchItem] = {
                w.display.lower(): w for w in self.watchlist
                if w.enabled and w.watch_ah
            }
            # Also try matching against key with spaces/hyphens normalised
            watch_by_key_norm: dict[str, WatchItem] = {
                w.key.replace("_", " ").replace("-", " ").lower(): w
                for w in self.watchlist if w.enabled and w.watch_ah
            }

            for txn in txns:
                item_name = txn.get("itemName", "")
                price     = txn.get("price", 0)
                seller    = txn.get("sellerName", "—") or "—"
                buyer     = txn.get("buyerName",  "—") or "—"
                is_stack  = txn.get("isStack", False)
                stack_lbl = "Stack" if is_stack else "Single"

                # Match to watched item
                name_lower = item_name.lower()
                name_norm  = name_lower.replace("-", " ").replace("_", " ")
                watch = (watch_by_display.get(name_lower)
                         or watch_by_display.get(name_norm)
                         or watch_by_key_norm.get(name_norm))
                if not watch:
                    continue

                # Check stack mode filter
                mode = getattr(watch, "ah_stack_mode", "single")
                if mode == "single" and is_stack:
                    continue
                if mode == "stack" and not is_stack:
                    continue

                # Price cap check
                if price > watch.max_price:
                    continue

                dk = self._dedup_key(
                    "psxi", watch.key, f"{seller}|{buyer}", price)
                if not self._is_new(dk):
                    continue

                rec = FindRecord(
                    timestamp=now, source="psxi",
                    item_key=watch.key, display_name=watch.display,
                    price=price, seller=seller,
                    zone=f"AH {stack_lbl}", quantity=1,
                    buyer=buyer, stack_label=stack_lbl,
                )
                self.finds_log.append(rec)
                watch.find_count  += 1
                watch.last_seen    = now
                watch.last_price   = price
                watch.last_seller  = seller
                watch.last_source  = "psxi"
                watch.last_buyer   = buyer
                new_finds.append({
                    "source":       "psxi",
                    "item_key":     watch.key,
                    "display_name": watch.display,
                    "price":        price,
                    "seller":       seller,
                    "zone":         f"AH {stack_lbl}",
                    "quantity":     1,
                    "buyer":        buyer,
                    "stack_label":  stack_lbl,
                })

            # ── PSXI Stock-Delta Detection ─────────────────────────
            # Alert when an item's total stock INCREASES (new listing appeared)
            listings = self._fetch_psxi_listings()
            for listing in listings:
                item_name = listing.get("itemName", "")
                stock     = (listing.get("stock", 0) or 0)
                s_stock   = (listing.get("stackStock", 0) or 0)
                total     = stock + s_stock
                prev      = self._psxi_stock_cache.get(item_name, -1)

                # Update cache
                self._psxi_stock_cache[item_name] = total

                # Only alert on stock INCREASE (new listing appeared)
                if prev < 0 or total <= prev:
                    continue

                name_lower = item_name.lower()
                name_norm  = name_lower.replace("-", " ").replace("_", " ")
                watch = (watch_by_display.get(name_lower)
                         or watch_by_display.get(name_norm)
                         or watch_by_key_norm.get(name_norm))
                if not watch:
                    continue

                last_price = (listing.get("lastPrice") or
                              listing.get("stackLastPrice") or 0)
                if last_price and last_price > watch.max_price:
                    continue

                dk = self._dedup_key(
                    "psxi_stock", watch.key, "STOCK_DELTA", total)
                if not self._is_new(dk):
                    continue

                zone_str = f"AH — stock ↑ {prev}→{total}"
                rec = FindRecord(
                    timestamp=now, source="psxi",
                    item_key=watch.key, display_name=watch.display,
                    price=last_price or 0, seller="(new listing)",
                    zone=zone_str, quantity=total - prev,
                    buyer="", stack_label="—",
                )
                self.finds_log.append(rec)
                watch.find_count  += 1
                watch.last_seen    = now
                watch.last_price   = last_price or 0
                watch.last_seller  = "(new listing)"
                watch.last_source  = "psxi"
                new_finds.append({
                    "source":       "psxi",
                    "item_key":     watch.key,
                    "display_name": watch.display,
                    "price":        last_price or 0,
                    "seller":       "(new listing)",
                    "zone":         zone_str,
                    "quantity":     total - prev,
                    "buyer":        "",
                    "stack_label":  "—",
                })

        # ── HorizonXI.com AH (throttled) ─────────────────────────
        if (self.auth.has_credentials
                and (now_epoch - self._last_ah_scan) >= AH_INTERVAL):
            self._last_ah_scan = now_epoch
            self.ah_status = "Scanning…"
            ah_ok = False
            for watch in self.watchlist:
                if not watch.enabled or not watch.watch_ah:
                    continue
                mode = getattr(watch, "ah_stack_mode", "single")
                stack_queries = []
                if mode == "single":
                    stack_queries = [("0", "Single")]
                elif mode == "stack":
                    stack_queries = [("1", "Stack")]
                else:
                    stack_queries = [("0", "Single"), ("1", "Stack")]

                for stack_val, stack_label in stack_queries:
                    info_resp = self._get(
                        f"{BASE_API}/items/{watch.key}/ah/info",
                        params={"stack": stack_val}, auth=True
                    )
                    if info_resp is None:
                        continue
                    try:
                        info_data = info_resp.json()
                    except Exception:
                        continue
                    ah_ok = True
                    stock = info_data.get("stock", 0)
                    if not stock or stock <= 0:
                        continue
                    dk = self._dedup_key(
                        "ah", watch.key, f"STOCK_{stack_val}", stock)
                    if not self._is_new(dk):
                        continue
                    seller_name  = "—"
                    recent_price = 0
                    buyer_name   = "—"
                    try:
                        hist_resp = self._get(
                            f"{BASE_API}/items/{watch.key}/ah",
                            params={"stack": stack_val}, auth=True
                        )
                        if hist_resp:
                            hist = hist_resp.json()
                            if isinstance(hist, list) and hist:
                                seller_name  = hist[0].get("seller_name", "—")
                                recent_price = hist[0].get("sale", 0)
                                buyer_name   = hist[0].get("buyer_name", "—") or "—"
                    except Exception:
                        pass
                    zone_str = f"AH {stack_label} — {stock} in stock"
                    rec = FindRecord(
                        timestamp=now, source="ah",
                        item_key=watch.key, display_name=watch.display,
                        price=recent_price, seller=seller_name,
                        zone=zone_str, quantity=stock,
                        buyer=buyer_name, stack_label=stack_label,
                    )
                    self.finds_log.append(rec)
                    watch.find_count  += 1
                    watch.last_seen    = now
                    watch.last_price   = recent_price
                    watch.last_seller  = seller_name
                    watch.last_source  = "ah"
                    watch.last_buyer   = buyer_name
                    new_finds.append({
                        "source":       "ah",
                        "item_key":     watch.key,
                        "display_name": watch.display,
                        "price":        recent_price,
                        "seller":       seller_name,
                        "zone":         zone_str,
                        "quantity":     stock,
                        "buyer":        buyer_name,
                        "stack_label":  stack_label,
                    })
            self.ah_status = "Active" if ah_ok else "Auth error — check credentials"
            if ah_ok:
                self.ah_scan_count += 1
        elif not self.auth.has_credentials:
            self.ah_status = "No credentials — configure in Settings"

        self.scan_count    += 1
        self.last_scan_time = now

        if new_finds:
            self.save()
            if self.on_finds_cb:
                self.on_finds_cb(new_finds)
        elif self.scan_count % 60 == 0:
            self.save()

        if self.on_scan_cb:
            self.on_scan_cb()

    def _run_loop(self):
        while self.running:
            self._scan()
            deadline = time.time() + BAZAAR_INTERVAL
            while self.running and time.time() < deadline:
                time.sleep(0.1)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def scan_now(self):
        threading.Thread(target=self._scan, daemon=True).start()

    # ── Item search ───────────────────────────────────────────────

    def search_items_bazaar(self, query: str) -> list[dict]:
        if not self._cached_bazaar:
            data = self._fetch_bazaar()
            if data:
                self._cached_bazaar = data
        data = self._cached_bazaar
        if not data:
            return []
        q = query.lower().strip()
        seen: dict[str, dict] = {}
        for item in data:
            name = item["name"]
            if all(word in name for word in q.split()):
                if name not in seen:
                    seen[name] = {
                        "key":       name,
                        "display":   name.replace("_", " ").title(),
                        "min_price": item["bazaar"],
                        "count":     1,
                        "source":    "bazaar",
                    }
                else:
                    seen[name]["min_price"] = min(
                        seen[name]["min_price"], item["bazaar"])
                    seen[name]["count"] += 1
        return sorted(seen.values(), key=lambda x: x["display"])

    def search_items_psxi(self, query: str) -> list[dict]:
        """
        Search PSXI for items by name — returns live stock + last price.
        No auth required.
        """
        try:
            resp = self._get(PSXI_SEARCH,
                             params={"q": query},
                             extra_headers=self._PSXI_HEADERS)
            if resp is None:
                return []
            data = resp.json()
            # API returns {"results": [...]} wrapper
            if isinstance(data, dict):
                items = data.get("results", data.get("data", []))
            else:
                items = data
            results = []
            for i in items:
                # PSXI search uses 'name' not 'itemName'
                name      = i.get("name", "") or i.get("itemName", "")
                s_stock   = (i.get("singleStock", 0) or 0)
                stk_stock = (i.get("stackStock", 0) or 0)
                s_price   = i.get("price", None) or i.get("singlePrice", None)
                stk_price = i.get("stackPrice", None)
                total_stock = s_stock + stk_stock
                best_price  = s_price or stk_price
                if not name:
                    continue
                # Derive a key: lowercase, spaces→underscores
                key = name.lower().replace(" ", "_").replace("-", "_")
                results.append({
                    "key":       key,
                    "display":   name,
                    "min_price": best_price,
                    "count":     total_stock,
                    "source":    "psxi",
                    "s_stock":   s_stock,
                    "stk_stock": stk_stock,
                })
            return results
        except Exception as e:
            print(f"[PSXI SEARCH ERROR] {e}")
            return []

    def search_items_catalog(self, query: str) -> list[dict]:
        try:
            resp = requests.get(
                ITEMS_API,
                params={"search": query, "limit": 50},
                headers={"User-Agent": "HorizonXI-Sniper/2.6",
                         "Accept": "application/json"},
                timeout=10
            )
            if resp.status_code == 200 and resp.content:
                data = resp.json()
                items = data.get("items", [])
                return [
                    {
                        "key":       i["key"],
                        "display":   i["name"],
                        "min_price": None,
                        "count":     None,
                        "source":    "catalog",
                        "ah":        i.get("ah", False),
                    }
                    for i in items
                ]
        except Exception as e:
            print(f"[CATALOG SEARCH ERROR] {e}")
        return []

    # ── Stats ─────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        by_item:   dict[str, int] = defaultdict(int)
        by_source: dict[str, int] = defaultdict(int)
        by_hour:   dict[str, int] = defaultdict(int)
        for r in self.finds_log:
            by_item[r.display_name]  += 1
            by_source[r.source]      += 1
            try:
                by_hour[r.timestamp[11:13]] += 1
            except Exception:
                pass
        return {
            "total_finds":       len(self.finds_log),
            "bazaar_finds":      by_source.get("bazaar", 0),
            "ah_finds":          by_source.get("ah", 0) + by_source.get("psxi", 0),
            "psxi_finds":        by_source.get("psxi", 0),
            "scan_count":        self.scan_count,
            "bazaar_scan_count": self.bazaar_scan_count,
            "ah_scan_count":     self.ah_scan_count,
            "psxi_scan_count":   self.psxi_scan_count,
            "last_scan":         self.last_scan_time,
            "last_bazaar_count": self.last_bazaar_count,
            "ah_status":         self.ah_status,
            "psxi_status":       self.psxi_status,
            "by_item":           dict(by_item),
            "by_hour":           dict(by_hour),
            "recent":            list(reversed(self.finds_log[-20:])),
        }


# ─────────────────────────────────────────────────────────────────
# GUI APPLICATION
# ─────────────────────────────────────────────────────────────────

class HorizonSniperApp:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.scraper = BazaarScraper()
        self.scraper.on_finds_cb = self._on_finds
        self.scraper.on_scan_cb  = self._on_scan

        self._current_theme = "Dark"
        _apply_theme("Dark")

        self._alert = AlertOverlay(root)

        self._setup_styles()
        self._build_ui()
        self._refresh_all()

        self.scraper.start()
        self._set_status("Scraper running — bazaar+PSXI every 5s, AH every 15s")
        self._schedule_refresh()

    # ── Styles ────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self.root)
        s.theme_use("default")

        s.configure("Dark.Treeview",
                     background=_T["BG2"], foreground=_T["TEXT"],
                     fieldbackground=_T["BG2"], rowheight=26,
                     font=("Segoe UI", 9))
        s.configure("Dark.Treeview.Heading",
                     background=_T["BG3"], foreground=_T["ACCENT"],
                     font=("Segoe UI", 9, "bold"), relief="flat")
        # Definitive flicker fix: cover every possible state combination
        s.map("Dark.Treeview",
              background=[
                  ("selected", "focus",    _T["SEL_BG"]),
                  ("selected", "!focus",   _T["SEL_BG"]),
                  ("selected",             _T["SEL_BG"]),
              ],
              foreground=[
                  ("selected", "focus",    _T["SEL_FG"]),
                  ("selected", "!focus",   _T["SEL_FG"]),
                  ("selected",             _T["SEL_FG"]),
              ])

        s.configure("Dark.TNotebook",    background=_T["BG"], borderwidth=0)
        s.configure("Dark.TNotebook.Tab",
                     background=_T["BG3"], foreground=_T["TEXT_DIM"],
                     padding=[16, 8], font=("Segoe UI", 10, "bold"))
        s.map("Dark.TNotebook.Tab",
              background=[("selected", _T["ACCENT"])],
              foreground=[("selected", "white")])
        s.configure("Dark.Vertical.TScrollbar",
                     background=_T["BG3"], troughcolor=_T["BG"],
                     arrowcolor=_T["TEXT_DIM"])

    # ── Window ────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.title("HorizonXI Bazaar + AH Sniper  ⚔️  v2.6")
        self.root.configure(bg=_T["BG"])
        self.root.geometry("1200x840")
        self.root.minsize(960, 640)

        self._build_header()

        self.nb = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self._build_tab_watchlist()
        self._build_tab_metrics()
        self._build_tab_log()
        self._build_tab_search()
        self._build_tab_settings()

        self._build_statusbar()

    # ── Header ────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=_T["HDR_BG"], height=66)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        left = tk.Frame(hdr, bg=_T["HDR_BG"])
        left.pack(side="left", padx=16, pady=8)
        tk.Label(left, text="⚔️  HorizonXI Sniper",
                 font=("Segoe UI", 17, "bold"),
                 bg=_T["HDR_BG"], fg=_T["GOLD"]).pack(side="left")
        tk.Label(left, text="  Bazaar + AH + PSXI  |  Public Edition v2.6",
                 font=("Segoe UI", 10),
                 bg=_T["HDR_BG"], fg=_T["TEXT_DIM"]).pack(side="left", pady=4)

        right = tk.Frame(hdr, bg=_T["HDR_BG"])
        right.pack(side="right", padx=16)

        self.btn_scan = tk.Button(
            right, text="⚡ Scan Now", command=self._manual_scan,
            bg=_T["ACCENT2"], fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2", padx=12, pady=6, takefocus=False)
        self.btn_scan.pack(side="right", padx=6)

        self.btn_toggle = tk.Button(
            right, text="⏸ Pause", command=self._toggle_scraper,
            bg=_T["WARN"], fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2", padx=12, pady=6, takefocus=False)
        self.btn_toggle.pack(side="right", padx=6)

        self.live_lbl = tk.Label(right, text="● LIVE",
                                  font=("Segoe UI", 10, "bold"),
                                  bg=_T["HDR_BG"], fg=_T["GREEN"])
        self.live_lbl.pack(side="right", padx=10)

        self.psxi_lbl = tk.Label(right, text="PSXI: —",
                                  font=("Segoe UI", 9),
                                  bg=_T["HDR_BG"], fg=_T["GOLD"])
        self.psxi_lbl.pack(side="right", padx=6)

        self.ah_lbl = tk.Label(right, text="AH: —",
                                font=("Segoe UI", 9),
                                bg=_T["HDR_BG"], fg=_T["TEXT_DIM"])
        self.ah_lbl.pack(side="right", padx=8)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=_T["BG3"], height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_var   = tk.StringVar(value="Initialising…")
        self._scaninfo_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._status_var,
                 font=("Segoe UI", 9), bg=_T["BG3"],
                 fg=_T["TEXT_DIM"], anchor="w").pack(side="left", padx=10)
        tk.Label(bar, textvariable=self._scaninfo_var,
                 font=("Segoe UI", 9), bg=_T["BG3"],
                 fg=_T["TEXT_DIM"], anchor="e").pack(side="right", padx=10)

    # ── Tab 1: Watchlist ──────────────────────────────────────────

    def _build_tab_watchlist(self):
        tab = tk.Frame(self.nb, bg=_T["BG"])
        self.nb.add(tab, text="  🎯 Watchlist  ")

        add_frm = tk.LabelFrame(tab, text="  Quick Add Item  ",
                                 bg=_T["BG"], fg=_T["ACCENT"],
                                 font=("Segoe UI", 10, "bold"),
                                 bd=1, relief="groove", labelanchor="nw")
        add_frm.pack(fill="x", padx=12, pady=(10, 4))

        row = tk.Frame(add_frm, bg=_T["BG"])
        row.pack(fill="x", padx=10, pady=8)

        def _lbl(text, col):
            tk.Label(row, text=text, bg=_T["BG"], fg=_T["TEXT"],
                     font=("Segoe UI", 9)).grid(
                         row=0, column=col, sticky="w", padx=(0, 4))

        def _ent(var, width, col):
            e = tk.Entry(row, textvariable=var, width=width,
                         bg=_T["BG3"], fg=_T["TEXT"],
                         insertbackground=_T["TEXT"],
                         font=("Segoe UI", 10), relief="flat", bd=4)
            e.grid(row=0, column=col, padx=(0, 8))
            return e

        _lbl("Item Key:", 0)
        self._add_key = tk.StringVar()
        _ent(self._add_key, 26, 1)

        _lbl("Display Name:", 2)
        self._add_display = tk.StringVar()
        _ent(self._add_display, 20, 3)

        _lbl("Max Price:", 4)
        self._add_price = tk.StringVar(value="10000")
        _ent(self._add_price, 10, 5)

        self._add_bazaar_var = tk.BooleanVar(value=True)
        self._add_ah_var     = tk.BooleanVar(value=True)
        tk.Checkbutton(row, text="Bazaar", variable=self._add_bazaar_var,
                       bg=_T["BG"], fg=_T["ACCENT2"], selectcolor=_T["BG3"],
                       font=("Segoe UI", 9), activebackground=_T["BG"]
                       ).grid(row=0, column=6, padx=(4, 2))
        tk.Checkbutton(row, text="AH", variable=self._add_ah_var,
                       bg=_T["BG"], fg=_T["AH_COLOR"], selectcolor=_T["BG3"],
                       font=("Segoe UI", 9), activebackground=_T["BG"]
                       ).grid(row=0, column=7, padx=(0, 8))

        tk.Button(row, text="➕ Add to Checklist",
                  command=self._add_manual,
                  bg=_T["ACCENT2"], fg="white",
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  takefocus=False
                  ).grid(row=0, column=8, padx=(4, 0))

        # Watchlist table
        tbl_frm = tk.Frame(tab, bg=_T["BG"])
        tbl_frm.pack(fill="both", expand=True, padx=12, pady=4)

        cols = ("On", "Item", "Max Price", "Bazaar", "AH", "AH Mode",
                "Finds", "Last Seller", "Last Buyer", "Last Seen", "Last Price")
        self.watch_tree = ttk.Treeview(tbl_frm, columns=cols,
                                        show="headings",
                                        style="Dark.Treeview",
                                        takefocus=False)
        self.watch_tree.pack(side="left", fill="both", expand=True)

        wsb = ttk.Scrollbar(tbl_frm, orient="vertical",
                             command=self.watch_tree.yview,
                             style="Dark.Vertical.TScrollbar")
        wsb.pack(side="right", fill="y")
        self.watch_tree.configure(yscrollcommand=wsb.set)

        for col, w, a in zip(cols,
                              [40, 185, 80, 50, 40, 65, 50, 115, 115, 140, 80],
                              ["center","w","center","center","center",
                               "center","center","w","w","w","center"]):
            self.watch_tree.heading(col, text=col)
            self.watch_tree.column(col, width=w, anchor=a)

        self.watch_tree.tag_configure("on",  foreground=_T["TEXT"])
        self.watch_tree.tag_configure("off", foreground=_T["TEXT_DIM"])

        self.watch_tree.bind(
            "<FocusOut>",
            lambda _: self.root.after(1, self._reselect_watch_tree)
        )

        # Action buttons
        btn_row = tk.Frame(tab, bg=_T["BG"])
        btn_row.pack(fill="x", padx=12, pady=(2, 8))

        for text, cmd, color in [
            ("✅ Toggle On/Off",       self._toggle_sel,       _T["ACCENT"]),
            ("✏️  Edit Max Price",     self._edit_price,       _T["WARN"]),
            ("🔄 Toggle Bazaar/AH",   self._toggle_source,    _T["AH_COLOR"]),
            ("📦 Cycle AH Mode",      self._cycle_stack_mode, _T["AH_COLOR"]),
            ("🗑 Remove",              self._remove_sel,       _T["DANGER"]),
        ]:
            tk.Button(btn_row, text=text, command=cmd,
                      bg=color, fg="white",
                      font=("Segoe UI", 9, "bold"),
                      relief="flat", cursor="hand2", padx=10, pady=5,
                      takefocus=False
                      ).pack(side="left", padx=(0, 6))

        tk.Label(btn_row,
                 text="💡 Use Search & Add tab to find items by name",
                 bg=_T["BG"], fg=_T["TEXT_DIM"],
                 font=("Segoe UI", 9, "italic")).pack(side="right")

    # ── Tab 2: Metrics ────────────────────────────────────────────

    def _build_tab_metrics(self):
        tab = tk.Frame(self.nb, bg=_T["BG"])
        self.nb.add(tab, text="  📊 Metrics  ")

        cards_frm = tk.Frame(tab, bg=_T["BG"])
        cards_frm.pack(fill="x", padx=12, pady=(12, 6))

        self._stat_lbls = {}
        card_defs = [
            ("total_finds",  "Total Finds",    _T["ACCENT2"]),
            ("bazaar_finds", "Bazaar Finds",   _T["ACCENT2"]),
            ("ah_finds",     "AH+PSXI Finds",  _T["AH_COLOR"]),
            ("psxi_finds",   "PSXI Finds",     _T["GOLD"]),
            ("scan_count",   "Total Scans",    _T["ACCENT"]),
            ("last_scan",    "Last Scan",       _T["WARN"]),
            ("listings",     "Live Listings",  _T["TEXT_DIM"]),
        ]
        for i, (key, label, color) in enumerate(card_defs):
            c = tk.Frame(cards_frm, bg=_T["BG2"], padx=10, pady=10)
            c.grid(row=0, column=i, padx=5, pady=4, sticky="nsew")
            cards_frm.columnconfigure(i, weight=1)
            tk.Label(c, text=label, bg=_T["BG2"], fg=_T["TEXT_DIM"],
                     font=("Segoe UI", 8)).pack()
            lbl = tk.Label(c, text="—", bg=_T["BG2"], fg=color,
                           font=("Segoe UI", 15, "bold"))
            lbl.pack()
            self._stat_lbls[key] = lbl

        self._item_stats_frm = tk.Frame(tab, bg=_T["BG"])
        self._item_stats_frm.pack(fill="x", padx=12, pady=(0, 6))

        tk.Label(tab, text="Recent Finds",
                 bg=_T["BG"], fg=_T["ACCENT"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14)

        rec_frm = tk.Frame(tab, bg=_T["BG2"])
        rec_frm.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        rcols = ("Seller", "Buyer", "Source", "Item", "Price",
                 "Zone / Info", "Time", "Qty")
        self.recent_tree = ttk.Treeview(rec_frm, columns=rcols,
                                         show="headings",
                                         style="Dark.Treeview",
                                         takefocus=False)
        self.recent_tree.pack(side="left", fill="both", expand=True)

        rsb = ttk.Scrollbar(rec_frm, orient="vertical",
                             command=self.recent_tree.yview,
                             style="Dark.Vertical.TScrollbar")
        rsb.pack(side="right", fill="y")
        self.recent_tree.configure(yscrollcommand=rsb.set)

        for col, w, a in zip(rcols,
                              [110, 110, 60, 170, 80, 190, 75, 45],
                              ["w","w","center","w","center","w","center","center"]):
            self.recent_tree.heading(col, text=col)
            self.recent_tree.column(col, width=w, anchor=a)

        self.recent_tree.tag_configure("bazaar", foreground=_T["ACCENT2"])
        self.recent_tree.tag_configure("ah",     foreground=_T["AH_COLOR"])
        self.recent_tree.tag_configure("psxi",   foreground=_T["GOLD"])

    # ── Tab 3: Finds Log ──────────────────────────────────────────

    def _build_tab_log(self):
        tab = tk.Frame(self.nb, bg=_T["BG"])
        self.nb.add(tab, text="  📋 Finds Log  ")

        btn_row = tk.Frame(tab, bg=_T["BG"])
        btn_row.pack(fill="x", padx=12, pady=(10, 4))
        tk.Button(btn_row, text="🗑 Clear Log",
                  command=self._clear_log,
                  bg=_T["DANGER"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=5,
                  takefocus=False
                  ).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="📥 Export CSV",
                  command=self._export_csv,
                  bg=_T["ACCENT"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=5,
                  takefocus=False
                  ).pack(side="left")

        log_frm = tk.Frame(tab, bg=_T["BG2"])
        log_frm.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        lcols = ("Seller", "Buyer", "Source", "Timestamp", "Item",
                 "Price", "Zone / Info", "Qty", "Stack")
        self.log_tree = ttk.Treeview(log_frm, columns=lcols,
                                      show="headings",
                                      style="Dark.Treeview",
                                      takefocus=False)
        self.log_tree.pack(side="left", fill="both", expand=True)

        lsb = ttk.Scrollbar(log_frm, orient="vertical",
                             command=self.log_tree.yview,
                             style="Dark.Vertical.TScrollbar")
        lsb.pack(side="right", fill="y")
        self.log_tree.configure(yscrollcommand=lsb.set)

        for col, w, a in zip(lcols,
                              [110, 110, 55, 145, 170, 80, 185, 45, 55],
                              ["w","w","center","w","w","center","w","center","center"]):
            self.log_tree.heading(col, text=col)
            self.log_tree.column(col, width=w, anchor=a)

        self.log_tree.tag_configure("bazaar", foreground=_T["ACCENT2"])
        self.log_tree.tag_configure("ah",     foreground=_T["AH_COLOR"])
        self.log_tree.tag_configure("psxi",   foreground=_T["GOLD"])

    # ── Tab 4: Search & Add ───────────────────────────────────────

    def _build_tab_search(self):
        tab = tk.Frame(self.nb, bg=_T["BG"])
        self.nb.add(tab, text="  🔍 Search & Add  ")

        ctrl = tk.Frame(tab, bg=_T["BG"])
        ctrl.pack(fill="x", padx=12, pady=(12, 4))

        tk.Label(ctrl, text="Search:", bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 10)).pack(side="left")

        self._search_q = tk.StringVar()
        srch_ent = tk.Entry(ctrl, textvariable=self._search_q, width=28,
                             bg=_T["BG3"], fg=_T["TEXT"],
                             insertbackground=_T["TEXT"],
                             font=("Segoe UI", 11), relief="flat", bd=5)
        srch_ent.pack(side="left", padx=8)
        srch_ent.bind("<Return>", lambda _: self._do_search("psxi"))

        tk.Button(ctrl, text="🔍 Bazaar",
                  command=lambda: self._do_search("bazaar"),
                  bg=_T["ACCENT2"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  takefocus=False
                  ).pack(side="left", padx=(0, 4))
        tk.Button(ctrl, text="⭐ PSXI (AH+Stock)",
                  command=lambda: self._do_search("psxi"),
                  bg=_T["GOLD"], fg="#1a0d0d",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  takefocus=False
                  ).pack(side="left", padx=(0, 4))
        tk.Button(ctrl, text="📚 Full Catalog",
                  command=lambda: self._do_search("catalog"),
                  bg=_T["AH_COLOR"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  takefocus=False
                  ).pack(side="left", padx=(0, 12))

        tk.Label(ctrl, text="Max Price:", bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._search_price = tk.StringVar(value="10000")
        tk.Entry(ctrl, textvariable=self._search_price, width=10,
                 bg=_T["BG3"], fg=_T["TEXT"],
                 insertbackground=_T["TEXT"],
                 font=("Segoe UI", 10), relief="flat", bd=4
                 ).pack(side="left", padx=8)

        self._srch_bazaar_var = tk.BooleanVar(value=True)
        self._srch_ah_var     = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text="Bazaar", variable=self._srch_bazaar_var,
                       bg=_T["BG"], fg=_T["ACCENT2"], selectcolor=_T["BG3"],
                       font=("Segoe UI", 9), activebackground=_T["BG"]
                       ).pack(side="left", padx=(4, 2))
        tk.Checkbutton(ctrl, text="AH", variable=self._srch_ah_var,
                       bg=_T["BG"], fg=_T["AH_COLOR"], selectcolor=_T["BG3"],
                       font=("Segoe UI", 9), activebackground=_T["BG"]
                       ).pack(side="left", padx=(0, 10))

        self._btn_add_sel = tk.Button(ctrl, text="➕ Add to Watchlist",
                                       command=self._add_from_search,
                                       state="disabled",
                                       bg=_T["ACCENT"], fg="white",
                                       font=("Segoe UI", 9, "bold"),
                                       relief="flat", cursor="hand2",
                                       padx=10, pady=4, takefocus=False)
        self._btn_add_sel.pack(side="left")

        self._search_status = tk.Label(ctrl, text="",
                                        bg=_T["BG"], fg=_T["TEXT_DIM"],
                                        font=("Segoe UI", 9))
        self._search_status.pack(side="left", padx=12)

        srch_frm = tk.Frame(tab, bg=_T["BG2"])
        srch_frm.pack(fill="both", expand=True, padx=12, pady=(4, 4))

        scols = ("Display Name", "Item Key", "Source",
                 "Singles", "Stacks", "Last Price")
        self.search_tree = ttk.Treeview(srch_frm, columns=scols,
                                         show="headings",
                                         style="Dark.Treeview",
                                         takefocus=False)
        self.search_tree.pack(side="left", fill="both", expand=True)

        ssb = ttk.Scrollbar(srch_frm, orient="vertical",
                             command=self.search_tree.yview,
                             style="Dark.Vertical.TScrollbar")
        ssb.pack(side="right", fill="y")
        self.search_tree.configure(yscrollcommand=ssb.set)

        for col, w, a in zip(scols, [230, 250, 70, 70, 70, 120],
                              ["w","w","center","center","center","center"]):
            self.search_tree.heading(col, text=col)
            self.search_tree.column(col, width=w, anchor=a)

        self.search_tree.bind("<<TreeviewSelect>>", self._on_search_sel)
        self.search_tree.tag_configure("bazaar",  foreground=_T["ACCENT2"])
        self.search_tree.tag_configure("psxi",    foreground=_T["GOLD"])
        self.search_tree.tag_configure("catalog", foreground=_T["AH_COLOR"])

        tk.Label(tab,
                 text="💡 'Bazaar' searches live bazaar.  "
                      "'PSXI' searches AH with live stock & last price (recommended).  "
                      "'Full Catalog' searches all 15,000+ items.",
                 bg=_T["BG"], fg=_T["TEXT_DIM"],
                 font=("Segoe UI", 9, "italic"),
                 wraplength=1000, justify="left"
                 ).pack(padx=12, pady=(4, 10), anchor="w")

    # ── Tab 5: Settings ───────────────────────────────────────────

    def _build_tab_settings(self):
        tab = tk.Frame(self.nb, bg=_T["BG"])
        self.nb.add(tab, text="  ⚙️ Settings  ")

        frm = tk.LabelFrame(tab, text="  HorizonXI Account (for AH access)  ",
                             bg=_T["BG"], fg=_T["ACCENT"],
                             font=("Segoe UI", 11, "bold"),
                             bd=1, relief="groove")
        frm.pack(fill="x", padx=30, pady=20)

        inner = tk.Frame(frm, bg=_T["BG"])
        inner.pack(padx=20, pady=12)

        tk.Label(inner, text="Username:", bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 10)
                 ).grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._cfg_user = tk.StringVar(value=self.scraper.auth.username)
        tk.Entry(inner, textvariable=self._cfg_user, width=28,
                 bg=_T["BG3"], fg=_T["TEXT"],
                 insertbackground=_T["TEXT"],
                 font=("Segoe UI", 11), relief="flat", bd=5
                 ).grid(row=0, column=1, pady=6)

        tk.Label(inner, text="Password:", bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 10)
                 ).grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        self._cfg_pass = tk.StringVar(value=self.scraper.auth.password)
        tk.Entry(inner, textvariable=self._cfg_pass, width=28, show="•",
                 bg=_T["BG3"], fg=_T["TEXT"],
                 insertbackground=_T["TEXT"],
                 font=("Segoe UI", 11), relief="flat", bd=5
                 ).grid(row=1, column=1, pady=6)

        btn_row = tk.Frame(frm, bg=_T["BG"])
        btn_row.pack(pady=(0, 12))
        tk.Button(btn_row, text="💾 Save & Test Login",
                  command=self._save_credentials,
                  bg=_T["ACCENT"], fg="white",
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", padx=16, pady=8,
                  takefocus=False
                  ).pack(side="left", padx=8)
        self._cred_status = tk.Label(btn_row, text="",
                                      bg=_T["BG"], fg=_T["ACCENT2"],
                                      font=("Segoe UI", 10))
        self._cred_status.pack(side="left", padx=10)

        # PSXI info box
        psxi_frm = tk.LabelFrame(tab, text="  PSXI.gg Integration  ",
                                   bg=_T["BG"], fg=_T["GOLD"],
                                   font=("Segoe UI", 11, "bold"),
                                   bd=1, relief="groove")
        psxi_frm.pack(fill="x", padx=30, pady=(0, 16))
        tk.Label(psxi_frm,
                 text="PSXI.gg is a community AH tracker that provides real-time "
                      "transaction history (seller + buyer names) and live stock data "
                      "with no authentication required.\n\n"
                      "The sniper polls PSXI every 5 seconds using the ?after={id} "
                      "stream pattern — only new transactions are processed, so there "
                      "is no duplicate spam. Stock-delta alerts fire when an item's "
                      "AH stock count increases (new listing appeared).",
                 bg=_T["BG"], fg=_T["TEXT_DIM"],
                 font=("Segoe UI", 9), wraplength=700, justify="left"
                 ).pack(padx=20, pady=12, anchor="w")

        # Theme picker
        theme_frm = tk.LabelFrame(tab, text="  Colour Theme  ",
                                   bg=_T["BG"], fg=_T["ACCENT"],
                                   font=("Segoe UI", 11, "bold"),
                                   bd=1, relief="groove")
        theme_frm.pack(fill="x", padx=30, pady=(0, 16))

        theme_inner = tk.Frame(theme_frm, bg=_T["BG"])
        theme_inner.pack(padx=20, pady=12)

        tk.Label(theme_inner, text="Select theme:",
                 bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 12))

        self._theme_var = tk.StringVar(value=self._current_theme)
        theme_menu = ttk.Combobox(theme_inner,
                                   textvariable=self._theme_var,
                                   values=list(THEMES.keys()),
                                   state="readonly", width=14,
                                   font=("Segoe UI", 10))
        theme_menu.pack(side="left", padx=(0, 12))

        tk.Button(theme_inner, text="Apply Theme",
                  command=self._apply_theme_ui,
                  bg=_T["ACCENT"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=5,
                  takefocus=False
                  ).pack(side="left")

        self._theme_note = tk.Label(theme_inner,
                                     text="(restart app to fully apply)",
                                     bg=_T["BG"], fg=_T["TEXT_DIM"],
                                     font=("Segoe UI", 8, "italic"))
        self._theme_note.pack(side="left", padx=10)

        # Scan info
        info = tk.LabelFrame(tab, text="  Scan Settings  ",
                              bg=_T["BG"], fg=_T["ACCENT"],
                              font=("Segoe UI", 11, "bold"),
                              bd=1, relief="groove")
        info.pack(fill="x", padx=30, pady=(0, 16))
        tk.Label(info,
                 text=f"Bazaar scan interval:  {BAZAAR_INTERVAL}s\n"
                      f"PSXI stream interval:  {PSXI_INTERVAL}s\n"
                      f"HorizonXI AH interval: {AH_INTERVAL}s\n"
                      f"Dedup cache TTL:       {DEDUP_TTL // 3600}h "
                      f"(same listing silenced for {DEDUP_TTL // 3600} hours)",
                 bg=_T["BG"], fg=_T["TEXT_DIM"],
                 font=("Segoe UI", 9), justify="left"
                 ).pack(padx=20, pady=10, anchor="w")

    # ── Refresh helpers ───────────────────────────────────────────

    def _refresh_watchlist(self):
        sel_before = self.watch_tree.selection()
        for row in self.watch_tree.get_children():
            self.watch_tree.delete(row)
        for w in self.scraper.watchlist:
            tag  = "on" if w.enabled else "off"
            chk  = "✓" if w.enabled else "✗"
            baz  = "✓" if w.watch_bazaar else "—"
            ah   = "✓" if w.watch_ah else "—"
            mode_map = {"single": "Single", "stack": "Stack", "both": "Both"}
            mode = mode_map.get(w.ah_stack_mode, w.ah_stack_mode)
            self.watch_tree.insert("", "end", iid=w.key, tags=(tag,), values=(
                chk,
                w.display,
                f"{w.max_price:,}g",
                baz,
                ah,
                mode,
                w.find_count,
                w.last_seller or "—",
                w.last_buyer  or "—",
                (w.last_seen[11:] if w.last_seen else "—"),
                (f"{w.last_price:,}g" if w.last_price else "—"),
            ))
        for iid in sel_before:
            if self.watch_tree.exists(iid):
                self.watch_tree.selection_add(iid)
        self._alert.sync_watchlist(self.scraper.watchlist)

    def _refresh_metrics(self):
        stats = self.scraper.get_stats()
        self._stat_lbls["total_finds"].config(text=str(stats["total_finds"]))
        self._stat_lbls["bazaar_finds"].config(text=str(stats["bazaar_finds"]))
        self._stat_lbls["ah_finds"].config(text=str(stats["ah_finds"]))
        self._stat_lbls["psxi_finds"].config(text=str(stats["psxi_finds"]))
        self._stat_lbls["scan_count"].config(text=str(stats["scan_count"]))
        self._stat_lbls["last_scan"].config(
            text=stats["last_scan"][11:] if stats["last_scan"] else "—")
        self._stat_lbls["listings"].config(
            text=str(stats["last_bazaar_count"])
            if stats["last_bazaar_count"] else "—")

        ah_s = stats["ah_status"]
        ah_color = (_T["ACCENT2"] if "Active" in ah_s
                    else (_T["WARN"] if "No cred" in ah_s else _T["DANGER"]))
        self.ah_lbl.config(text=f"AH: {ah_s}", fg=ah_color)

        psxi_s = stats["psxi_status"]
        psxi_color = _T["GOLD"] if "Active" in psxi_s else _T["TEXT_DIM"]
        self.psxi_lbl.config(text=f"PSXI: {psxi_s}", fg=psxi_color)

        # Per-item cards
        for child in self._item_stats_frm.winfo_children():
            child.destroy()
        for i, watch in enumerate(self.scraper.watchlist):
            c = tk.Frame(self._item_stats_frm, bg=_T["BG2"])
            c.grid(row=0, column=i, padx=6, pady=4, sticky="nsew")
            self._item_stats_frm.columnconfigure(i, weight=1)
            tk.Label(c, text=watch.display, bg=_T["BG2"], fg=_T["TEXT"],
                     font=("Segoe UI", 9, "bold"), wraplength=160
                     ).pack(pady=(8, 2))
            count = stats["by_item"].get(watch.display, 0)
            tk.Label(c, text=str(count), bg=_T["BG2"], fg=_T["ACCENT2"],
                     font=("Segoe UI", 20, "bold")).pack()
            tk.Label(c, text="finds", bg=_T["BG2"], fg=_T["TEXT_DIM"],
                     font=("Segoe UI", 8)).pack()
            if watch.last_seller:
                tk.Label(c, text=f"Seller: {watch.last_seller}",
                         bg=_T["BG2"], fg=_T["GOLD"],
                         font=("Segoe UI", 8, "bold")).pack(pady=(2, 0))
            if watch.last_buyer:
                tk.Label(c, text=f"Buyer:  {watch.last_buyer}",
                         bg=_T["BG2"], fg=_T["AH_COLOR"],
                         font=("Segoe UI", 8)).pack(pady=(0, 8))
            elif not watch.last_seller:
                tk.Label(c, text="No finds yet", bg=_T["BG2"],
                         fg=_T["TEXT_DIM"],
                         font=("Segoe UI", 8)).pack(pady=(2, 8))
            else:
                tk.Label(c, text="", bg=_T["BG2"]).pack(pady=(0, 8))

        # Recent finds
        for row in self.recent_tree.get_children():
            self.recent_tree.delete(row)
        for r in stats["recent"]:
            zone_info = r.zone.replace("_", " ")
            buyer = getattr(r, "buyer", "") or "—"
            self.recent_tree.insert("", "end", values=(
                r.seller,
                buyer,
                r.source.upper(),
                r.display_name,
                f"{r.price:,}g" if r.price else "—",
                zone_info,
                r.timestamp[11:],
                r.quantity,
            ), tags=(r.source,))

    def _refresh_log(self):
        for row in self.log_tree.get_children():
            self.log_tree.delete(row)
        for r in reversed(self.scraper.finds_log):
            zone_info = r.zone.replace("_", " ")
            buyer     = getattr(r, "buyer", "") or "—"
            stk_lbl   = getattr(r, "stack_label", "—") or "—"
            self.log_tree.insert("", "end", values=(
                r.seller,
                buyer,
                r.source.upper(),
                r.timestamp,
                r.display_name,
                f"{r.price:,}g" if r.price else "—",
                zone_info,
                r.quantity,
                stk_lbl,
            ), tags=(r.source,))

    def _refresh_all(self):
        self._refresh_watchlist()
        self._refresh_metrics()
        self._refresh_log()

    def _schedule_refresh(self):
        self._refresh_all()
        self._update_live()
        self.root.after(2_000, self._schedule_refresh)

    def _update_live(self):
        if self.scraper.running:
            self.live_lbl.config(text="● LIVE", fg=_T["GREEN"])
            self.btn_toggle.config(text="⏸ Pause", bg=_T["WARN"])
        else:
            self.live_lbl.config(text="● PAUSED", fg=_T["DANGER"])
            self.btn_toggle.config(text="▶ Resume", bg=_T["ACCENT2"])

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        if self.scraper.last_scan_time:
            self._scaninfo_var.set(
                f"Last: {self.scraper.last_scan_time}  |  "
                f"Scans: {self.scraper.scan_count}  |  "
                f"Bazaar: {self.scraper.last_bazaar_count}  |  "
                f"PSXI: {self.scraper.psxi_scan_count}  |  "
                f"AH: {self.scraper.ah_scan_count}"
            )

    # ── Theme ─────────────────────────────────────────────────────

    def _apply_theme_ui(self):
        name = self._theme_var.get()
        _apply_theme(name)
        self._current_theme = name
        self._setup_styles()
        self._alert.apply_theme()
        self._theme_note.config(
            text=f"✅ Theme '{name}' applied — some colours update on restart",
            fg=_T["ACCENT2"])
        messagebox.showinfo(
            "Theme Applied",
            f"Theme '{name}' applied to styles.\n\n"
            "For a complete visual refresh (window backgrounds, buttons, etc.) "
            "please restart the application.")

    # ── Scraper callbacks ─────────────────────────────────────────

    def _on_finds(self, finds: list):
        count = len(finds)
        title = f"🎯 {count} deal{'s' if count > 1 else ''} — HorizonXI Sniper"
        lines = []
        for f in finds[:4]:
            src    = f.get("source", "bazaar").upper()
            buyer  = f.get("buyer", "")
            buyer_str = f" → {buyer}" if buyer and buyer != "—" else ""
            lines.append(
                f"[{src}] {f.get('seller','?')}{buyer_str} — "
                f"{f['display_name']} @ {f['price']:,}g"
            )
        threading.Thread(
            target=_desktop_notify, args=(title, "\n".join(lines)),
            daemon=True).start()
        self.root.after(0, lambda: self._alert.push(finds))
        self.root.after(0, lambda: self._set_status(
            f"🎯 {count} deal(s) found at "
            f"{datetime.datetime.now().strftime('%H:%M:%S')}!"
        ))

    def _on_scan(self):
        self.root.after(0, lambda: self._set_status(
            f"Scraper running — last scan: {self.scraper.last_scan_time or '—'}"
        ))

    def _toggle_scraper(self):
        if self.scraper.running:
            self.scraper.stop()
            self._set_status("Scraper paused")
        else:
            self.scraper.start()
            self._set_status("Scraper resumed")
        self._update_live()

    def _manual_scan(self):
        self._set_status("⚡ Manual scan triggered…")
        self.scraper.scan_now()

    # ── Watchlist actions ─────────────────────────────────────────

    def _add_manual(self):
        key     = self._add_key.get().strip().lower().replace(" ", "_")
        display = self._add_display.get().strip()
        price_s = self._add_price.get().strip()
        if not key or not display:
            messagebox.showerror("Missing Fields",
                                  "Please enter both Item Key and Display Name.")
            return
        try:
            price = int(price_s.replace(",", ""))
        except ValueError:
            messagebox.showerror("Invalid Price",
                                  "Max Price must be a whole number.")
            return
        if self.scraper.add_item(key, display, price,
                                  self._add_bazaar_var.get(),
                                  self._add_ah_var.get()):
            self._refresh_watchlist()
            self._add_key.set("")
            self._add_display.set("")
            self._set_status(f"✅ Added '{display}' to watchlist")
        else:
            messagebox.showinfo("Already Watching",
                                 f"'{display}' is already in your watchlist.")

    def _toggle_sel(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an item first.")
            return
        for iid in sel:
            self.scraper.toggle_item(iid)
        self._refresh_watchlist()

    def _toggle_source(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an item first.")
            return
        iid   = sel[0]
        watch = next((w for w in self.scraper.watchlist if w.key == iid), None)
        if not watch:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Toggle Source")
        dlg.configure(bg=_T["BG"])
        dlg.geometry("300x160")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        tk.Label(dlg, text=f"Toggle monitoring source for:\n{watch.display}",
                 bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 10), justify="center"
                 ).pack(pady=(16, 10))
        row = tk.Frame(dlg, bg=_T["BG"])
        row.pack()
        tk.Button(row, text="Toggle Bazaar",
                  command=lambda: (self.scraper.toggle_source(iid, "bazaar"),
                                   self._refresh_watchlist(), dlg.destroy()),
                  bg=_T["ACCENT2"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  takefocus=False
                  ).pack(side="left", padx=8)
        tk.Button(row, text="Toggle AH",
                  command=lambda: (self.scraper.toggle_source(iid, "ah"),
                                   self._refresh_watchlist(), dlg.destroy()),
                  bg=_T["AH_COLOR"], fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=6,
                  takefocus=False
                  ).pack(side="left", padx=8)

    def _edit_price(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an item first.")
            return
        iid   = sel[0]
        watch = next((w for w in self.scraper.watchlist if w.key == iid), None)
        if not watch:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Max Price")
        dlg.configure(bg=_T["BG"])
        dlg.geometry("340x165")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        tk.Label(dlg, text=f"New max price for:\n{watch.display}",
                 bg=_T["BG"], fg=_T["TEXT"],
                 font=("Segoe UI", 11), justify="center"
                 ).pack(pady=(20, 8))
        pvar = tk.StringVar(value=str(watch.max_price))
        ent  = tk.Entry(dlg, textvariable=pvar, width=16,
                         bg=_T["BG3"], fg=_T["TEXT"],
                         insertbackground=_T["TEXT"],
                         font=("Segoe UI", 12), relief="flat",
                         bd=6, justify="center")
        ent.pack(pady=4)
        ent.focus_set()
        def _save():
            try:
                self.scraper.update_price(iid, int(pvar.get().replace(",", "")))
                self._refresh_watchlist()
                dlg.destroy()
            except ValueError:
                messagebox.showerror("Invalid", "Enter a whole number.",
                                      parent=dlg)
        ent.bind("<Return>", lambda _: _save())
        tk.Button(dlg, text="Save", command=_save,
                  bg=_T["ACCENT"], fg="white",
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", padx=16, pady=6,
                  takefocus=False
                  ).pack(pady=10)

    def _cycle_stack_mode(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an item first.")
            return
        for iid in sel:
            self.scraper.cycle_stack_mode(iid)
        self._refresh_watchlist()

    def _reselect_watch_tree(self):
        try:
            sel = self.watch_tree.selection()
            if sel:
                self.watch_tree.selection_set(sel)
        except Exception:
            pass

    def _remove_sel(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select an item first.")
            return
        names = [next((w.display for w in self.scraper.watchlist
                        if w.key == iid), iid) for iid in sel]
        if messagebox.askyesno("Confirm Remove",
                                f"Remove {len(sel)} item(s)?\n"
                                + "\n".join(names)):
            for iid in sel:
                self.scraper.remove_item(iid)
            self._refresh_watchlist()

    # ── Search & Add ──────────────────────────────────────────────

    def _do_search(self, mode: str = "psxi"):
        q = self._search_q.get().strip()
        if not q:
            return
        self._search_status.config(text="Searching…", fg=_T["WARN"])
        self.search_tree.delete(*self.search_tree.get_children())
        self._btn_add_sel.config(state="disabled")

        def _fetch():
            if mode == "bazaar":
                results = self.scraper.search_items_bazaar(q)
            elif mode == "psxi":
                results = self.scraper.search_items_psxi(q)
            else:
                results = self.scraper.search_items_catalog(q)
            self.root.after(0, lambda: self._populate_search(results, mode))

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_search(self, results: list, mode: str):
        self.search_tree.delete(*self.search_tree.get_children())
        if not results:
            self._search_status.config(text="No results found.",
                                        fg=_T["DANGER"])
            return
        self._search_status.config(
            text=f"{len(results)} item(s) found", fg=_T["ACCENT2"])
        for item in results:
            if mode == "psxi":
                singles = str(item.get("s_stock", "—"))
                stacks  = str(item.get("stk_stock", "—"))
                price   = (f"{item['min_price']:,}g"
                           if item.get("min_price") is not None else "—")
            elif mode == "bazaar":
                singles = str(item.get("count", "—"))
                stacks  = "—"
                price   = (f"{item['min_price']:,}g"
                           if item.get("min_price") is not None else "—")
            else:
                singles = "—"
                stacks  = "—"
                price   = "—"
            self.search_tree.insert("", "end",
                                     iid=item["key"],
                                     values=(
                                         item["display"],
                                         item["key"],
                                         mode.upper(),
                                         singles,
                                         stacks,
                                         price,
                                     ), tags=(mode,))

    def _on_search_sel(self, _event):
        self._btn_add_sel.config(
            state="normal" if self.search_tree.selection() else "disabled")

    def _add_from_search(self):
        sel = self.search_tree.selection()
        if not sel:
            return
        iid  = sel[0]
        vals = self.search_tree.item(iid, "values")
        display = vals[0]
        key     = vals[1]
        try:
            price = int(self._search_price.get().replace(",", ""))
        except ValueError:
            messagebox.showerror("Invalid Price",
                                  "Max Price must be a whole number.")
            return
        if self.scraper.add_item(key, display, price,
                                  self._srch_bazaar_var.get(),
                                  self._srch_ah_var.get()):
            self._refresh_watchlist()
            self.nb.select(0)
            self._set_status(f"✅ Added '{display}' to watchlist")
        else:
            messagebox.showinfo("Already Watching",
                                 f"'{display}' is already in your watchlist.")

    # ── Settings ──────────────────────────────────────────────────

    def _save_credentials(self):
        user = self._cfg_user.get().strip()
        pw   = self._cfg_pass.get().strip()
        if not user or not pw:
            messagebox.showerror("Missing Fields",
                                  "Enter both username and password.")
            return
        self._cred_status.config(text="Testing login…", fg=_T["WARN"])
        self.root.update()

        def _test():
            self.scraper.auth.save_config(user, pw)
            token = self.scraper.auth.get_token(force_refresh=True)
            if token:
                self.root.after(0, lambda: self._cred_status.config(
                    text="✅ Login successful — AH scanning active",
                    fg=_T["ACCENT2"]))
            else:
                self.root.after(0, lambda: self._cred_status.config(
                    text="❌ Login failed — check username/password",
                    fg=_T["DANGER"]))

        threading.Thread(target=_test, daemon=True).start()

    # ── Log actions ───────────────────────────────────────────────

    def _clear_log(self):
        if messagebox.askyesno("Clear Log",
                                "Clear all finds history? Cannot be undone."):
            self.scraper.finds_log.clear()
            for w in self.scraper.watchlist:
                w.find_count  = 0
                w.last_seen   = None
                w.last_price  = None
                w.last_seller = None
                w.last_source = None
                w.last_buyer  = None
            self.scraper.save()
            self._refresh_all()

    def _export_csv(self):
        path = os.path.join(SCRIPT_DIR, "finds_export.csv")
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Seller","Buyer","Source","Timestamp","Item",
                                  "Price","Zone/Info","Qty","Stack"])
                for r in self.scraper.finds_log:
                    writer.writerow([
                        r.seller,
                        getattr(r, "buyer", ""),
                        r.source,
                        r.timestamp,
                        r.display_name,
                        r.price,
                        r.zone,
                        r.quantity,
                        getattr(r, "stack_label", ""),
                    ])
            messagebox.showinfo("Exported",
                                 f"Finds log exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.configure(bg=_T["BG"])
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = HorizonSniperApp(root)

    def _shutdown(*_):
        print("\n[INFO] Shutting down cleanly…")
        app.scraper.stop()
        app.scraper.save()
        try:
            root.quit()
            root.destroy()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    root.protocol("WM_DELETE_WINDOW", _shutdown)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    print("=" * 46)
    print("  HorizonXI Bazaar + AH Sniper  v2.6")
    print("  CEO Edition - Bazaar + AH + PSXI.gg")
    print("=" * 46)
    print("[INFO] Checking dependencies...")
    try:
        import requests as _r
    except ImportError:
        print("[ERROR] 'requests' not installed. Run: pip install requests")
        sys.exit(1)
    try:
        import plyer as _p
    except ImportError:
        print("[WARN] 'plyer' not installed — desktop notifications disabled.")
        print("       Run: pip install plyer")
    print("[INFO] Starting HorizonXI Sniper...")
    main()
