"""Board Game Library — Tkinter GUI."""
from __future__ import annotations

import os
import random
import re
import shutil
import sys
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
try:
    from tkcalendar import DateEntry as _DateEntry
    _HAVE_CAL = True
except ImportError:
    _HAVE_CAL = False
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageTk

import bgg
import config
import db

# ── Secure credential storage ─────────────────────────────────────────────────
# Layered approach:
#   1. Windows DPAPI via ctypes  — no external libs, works in any .exe build
#   2. keyring (if installed)    — also uses DPAPI under the hood on Windows
# The DPAPI-encrypted blob is stored in DATA_DIR/creds so it survives restarts.

def _dpapi_encrypt(text: str) -> Optional[str]:
    """Encrypt *text* with Windows DPAPI (user-scoped). Returns base64 string."""
    try:
        import ctypes, ctypes.wintypes, base64 as _b64  # noqa: PLC0415
        class _BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]
        raw   = text.encode("utf-8")
        inp   = _BLOB(len(raw), ctypes.cast(ctypes.c_char_p(raw),
                                             ctypes.POINTER(ctypes.c_char)))
        out   = _BLOB()
        ok    = ctypes.windll.Crypt32.CryptProtectData(
                    ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out))
        if ok:
            result = ctypes.string_at(out.pbData, out.cbData)
            ctypes.windll.Kernel32.LocalFree(out.pbData)
            return _b64.b64encode(result).decode()
    except Exception:
        pass
    return None

def _dpapi_decrypt(blob: str) -> Optional[str]:
    """Decrypt a DPAPI blob produced by _dpapi_encrypt."""
    try:
        import ctypes, ctypes.wintypes, base64 as _b64  # noqa: PLC0415
        class _BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]
        raw   = _b64.b64decode(blob)
        inp   = _BLOB(len(raw), ctypes.cast(ctypes.c_char_p(raw),
                                             ctypes.POINTER(ctypes.c_char)))
        out   = _BLOB()
        ok    = ctypes.windll.Crypt32.CryptUnprotectData(
                    ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out))
        if ok:
            result = ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
            ctypes.windll.Kernel32.LocalFree(out.pbData)
            return result
    except Exception:
        pass
    return None

# Path for the DPAPI-encrypted credential file
_CREDS_PATH: Optional[Path] = None  # set after paths module is loaded

def _creds_file() -> Optional[Path]:
    global _CREDS_PATH
    if _CREDS_PATH is None:
        try:
            from paths import DATA_DIR  # noqa: PLC0415
            _CREDS_PATH = DATA_DIR / "creds"
        except Exception:
            pass
    return _CREDS_PATH

def _kr_get_password() -> str:
    """Read the BGG password from the DPAPI-encrypted credential file."""
    try:
        cf = _creds_file()
        if cf and cf.exists():
            blob = cf.read_text(encoding="utf-8").strip()
            pwd  = _dpapi_decrypt(blob)
            if pwd:
                return pwd
    except Exception:
        pass
    # Fallback: try keyring if available
    try:
        import keyring as _kr  # noqa: PLC0415
        return _kr.get_password("BoardGameLibrary", "bgg_password") or ""
    except Exception:
        pass
    return ""

def _kr_set_password(pwd: str) -> None:
    """Write the BGG password to the DPAPI-encrypted credential file."""
    try:
        cf = _creds_file()
        if cf is not None:
            if pwd:
                blob = _dpapi_encrypt(pwd)
                if blob:
                    cf.write_text(blob, encoding="utf-8")
                    return
            else:
                if cf.exists():
                    cf.unlink()
                return
    except Exception:
        pass
    # Fallback: keyring
    try:
        import keyring as _kr  # noqa: PLC0415
        if pwd:
            _kr.set_password("BoardGameLibrary", "bgg_password", pwd)
        else:
            try: _kr.delete_password("BoardGameLibrary", "bgg_password")
            except Exception: pass
    except Exception:
        pass
from paths import DATA_DIR, DB_PATH, CONFIG_PATH, IMAGES_DIR
from version import __version__ as APP_VERSION


def _resource_path(name: str) -> str:
    """Path to a bundled resource (works in dev and in a PyInstaller bundle)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

THUMB_SIZE = (240, 240)
# Card size presets: card_w, cover_h, title font pt, sub-text font pt, wrap px
_CARD_SIZES = {
    "sm": {"card_w": 180, "cover_h": 120, "title": 12, "sub": 10, "wrap": 155},
    "md": {"card_w": 260, "cover_h": 200, "title": 16, "sub": 13, "wrap": 210},
    "lg": {"card_w": 340, "cover_h": 260, "title": 18, "sub": 14, "wrap": 285},
}
PLACEHOLDER_BG = "#EAEEF2"  # C_LINE_100 — defined before color tokens
APP_CREATED   = "May 5, 2026"
APP_AUTHOR    = "Ballewcifer"
APP_CONTACT   = "ballewcifer@gmail.com"



def _open_url(url: str) -> None:
    """Open a URL in the system default browser.

    Uses os.startfile on Windows (most reliable from a PyInstaller bundle),
    'open' on macOS, and 'xdg-open' on Linux.
    """
    try:
        if sys.platform == "win32":
            os.startfile(url)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", url])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", url])
    except Exception:
        pass

# ── Design system tokens (design-tokens.json) ────────────────────────────────
# Brand / navy
C_NAVY_900 = "#0E2A47"   # header / top bar
C_NAVY_800 = "#13395F"   # tab strip
C_NAVY_700 = "#1B4B79"
# Action blue
C_BLUE_600 = "#1366C9"   # primary buttons, links, focus ring
C_BLUE_700 = "#0F52A3"   # hover
C_BLUE_800 = "#0B3F80"   # pressed
C_BLUE_050 = "#E7F0FB"   # tints / selected row bg
# Neutrals
C_INK_900  = "#16202B"   # primary text
C_INK_600  = "#51606E"   # secondary text
C_INK_500  = "#6B7785"   # muted / icons
C_LINE_200 = "#D9E0E7"   # borders
C_LINE_100 = "#EAEEF2"   # hairlines
C_SURFACE  = "#FFFFFF"   # card surface
C_BG       = "#F4F6F8"   # app canvas
# Status
C_OK_TEXT  = "#1E6E32";  C_OK_BG  = "#E6F4EA";  C_OK_SOLID  = "#2E7D32"
C_WN_TEXT  = "#8A5300";  C_WN_BG  = "#FFF3E0";  C_WN_SOLID  = "#B26A00"
C_DR_TEXT  = "#B3261E";  C_DR_BG  = "#FCEBEA";  C_DR_SOLID  = "#C62828"
# Star / favorite
C_STAR_TEXT = "#B07A00"; C_STAR_FILL = "#F2A900"

# Aliases so existing code that references the old names keeps working
C_NAVY  = C_NAVY_900
C_BLUE  = C_BLUE_600
C_SKY   = C_BLUE_050
C_PALE  = C_LINE_100
C_WHITE = C_SURFACE
C_TEXT  = C_INK_900
C_GOLD  = C_STAR_FILL

# ── UI colour themes ─────────────────────────────────────────────────────────
# Each theme overrides only the brand family (dark app-bar/tab base + accent);
# neutrals, status, and star colours stay constant so contrast is preserved.
THEMES: dict = {
    "Classic Navy": {"navy900": "#0E2A47", "navy800": "#13395F", "navy700": "#1B4B79",
                     "blue600": "#1366C9", "blue700": "#0F52A3", "blue800": "#0B3F80", "blue050": "#E7F0FB"},
    "Ocean":        {"navy900": "#0A2A43", "navy800": "#0E3D5F", "navy700": "#12527E",
                     "blue600": "#1488D6", "blue700": "#106BA8", "blue800": "#0C527F", "blue050": "#E4F1FB"},
    "Teal":         {"navy900": "#0B2E33", "navy800": "#10464D", "navy700": "#155E67",
                     "blue600": "#0E8C99", "blue700": "#0B6E78", "blue800": "#08545C", "blue050": "#E4F4F5"},
    "Forest":       {"navy900": "#10331F", "navy800": "#16492C", "navy700": "#1C5E39",
                     "blue600": "#1F8A4C", "blue700": "#176B3A", "blue800": "#11512C", "blue050": "#E6F4EA"},
    "Slate":        {"navy900": "#1C2530", "navy800": "#2A3744", "navy700": "#384857",
                     "blue600": "#3D6FA5", "blue700": "#305885", "blue800": "#244468", "blue050": "#E9EFF6"},
    "Indigo":       {"navy900": "#1A1F4E", "navy800": "#262C6E", "navy700": "#33398E",
                     "blue600": "#3D47C4", "blue700": "#30389B", "blue800": "#252C79", "blue050": "#E9EAF9"},
    "Purple":       {"navy900": "#2A1240", "navy800": "#3E1B5E", "navy700": "#52247B",
                     "blue600": "#7A33C9", "blue700": "#5F28A0", "blue800": "#491E7C", "blue050": "#F0E9FB"},
    "Burgundy":     {"navy900": "#3A1220", "navy800": "#561B2F", "navy700": "#73243E",
                     "blue600": "#B3264C", "blue700": "#8E1E3D", "blue800": "#6E172F", "blue050": "#FBE9EE"},
    "Crimson":      {"navy900": "#3F0F15", "navy800": "#5E171F", "navy700": "#7D202B",
                     "blue600": "#C62434", "blue700": "#9C1C29", "blue800": "#79151F", "blue050": "#FBE8EA"},
    "Bronze":       {"navy900": "#3A2A0E", "navy800": "#574016", "navy700": "#74561E",
                     "blue600": "#B5832A", "blue700": "#8E6620", "blue800": "#6E4F19", "blue050": "#F7EFDF"},
    # Accessible: maximum contrast (black bar + vivid blue accent)
    "High Contrast":     {"navy900": "#000000", "navy800": "#1A1A1A", "navy700": "#333333",
                          "blue600": "#0B57D0", "blue700": "#0842A0", "blue800": "#063078", "blue050": "#E8F0FE"},
    # Accessible: Okabe-Ito blue — distinguishable for common colour blindness
    "Colour-blind Safe": {"navy900": "#00344A", "navy800": "#004C6B", "navy700": "#00638C",
                          "blue600": "#0072B2", "blue700": "#005B8F", "blue800": "#00466E", "blue050": "#E1F0F8"},
}


def apply_theme(name: str) -> None:
    """Override the brand-colour globals with the named theme (default Classic Navy)."""
    global C_NAVY_900, C_NAVY_800, C_NAVY_700
    global C_BLUE_600, C_BLUE_700, C_BLUE_800, C_BLUE_050
    global C_NAVY, C_BLUE, C_SKY
    t = THEMES.get(name) or THEMES["Classic Navy"]
    C_NAVY_900, C_NAVY_800, C_NAVY_700 = t["navy900"], t["navy800"], t["navy700"]
    C_BLUE_600, C_BLUE_700, C_BLUE_800, C_BLUE_050 = (
        t["blue600"], t["blue700"], t["blue800"], t["blue050"])
    C_NAVY, C_BLUE, C_SKY = C_NAVY_900, C_BLUE_600, C_BLUE_050


_ORDINALS = {
    "First": "1st", "Second": "2nd", "Third": "3rd", "Fourth": "4th",
    "Fifth": "5th", "Sixth": "6th", "Seventh": "7th", "Eighth": "8th",
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
    "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
}
_ORDINAL_RE = re.compile(r"\b(" + "|".join(_ORDINALS) + r")\b")


def _shorten(text: str) -> str:
    """Replace spelled-out ordinals with compact numeral forms to save card space."""
    return _ORDINAL_RE.sub(lambda m: _ORDINALS[m.group()], text)


def fmt_players(min_p: Optional[int], max_p: Optional[int]) -> str:
    if not min_p and not max_p:
        return "?"
    if min_p == max_p or not max_p:
        return f"{min_p}"
    if not min_p:
        return f"up to {max_p}"
    return f"{min_p}–{max_p}"


def fmt_time(minp: Optional[int], maxp: Optional[int], avg: Optional[int]) -> str:
    if minp and maxp and minp != maxp:
        return f"{minp}–{maxp} min"
    if avg:
        return f"{avg} min"
    if minp:
        return f"{minp} min"
    return "?"


def fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


class _AutocompleteEntry(ttk.Entry):
    """Entry widget that shows a dropdown of suggestions as the user types.

    Supports comma-separated values: pressing a suggestion replaces only the
    *last* comma-delimited token, so Players can be entered as
    "Alice, Bob, ..." with autocomplete on each name.
    """

    def __init__(self, parent, suggestions: list[str], **kwargs):
        self._suggestions = suggestions
        self._var: tk.StringVar = kwargs.pop("textvariable", tk.StringVar())
        super().__init__(parent, textvariable=self._var, **kwargs)
        self._popup: Optional[tk.Toplevel] = None
        self._lb:    Optional[tk.Listbox]  = None
        self._var.trace_add("write", self._on_change)
        self.bind("<FocusOut>", lambda e: self.after(150, self._hide))
        self.bind("<Escape>",   lambda e: self._hide())
        self.bind("<Down>",     self._focus_lb)

    @property
    def var(self) -> tk.StringVar:
        return self._var

    def _last_token(self) -> str:
        text = self._var.get()
        return text.rsplit(",", 1)[-1].strip()

    def _on_change(self, *_) -> None:
        token = self._last_token()
        if not token:
            self._hide()
            return
        matches = [s for s in self._suggestions if token.lower() in s.lower()]
        if matches:
            self._show(matches)
        else:
            self._hide()

    def _show(self, matches: list[str]) -> None:
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup.wm_attributes("-topmost", True)
            self._lb = tk.Listbox(
                self._popup, selectmode="single",
                font=("Segoe UI", 9), activestyle="none",
                selectbackground=C_BLUE, selectforeground=C_WHITE,
                relief="solid", borderwidth=1,
            )
            self._lb.pack(fill="both", expand=True)
            self._lb.bind("<ButtonRelease-1>", self._pick)
            self._lb.bind("<Return>",          self._pick)
            self._lb.bind("<FocusOut>",        lambda e: self.after(150, self._hide))

        self._lb.delete(0, "end")
        for m in matches[:8]:
            self._lb.insert("end", m)

        count = min(len(matches), 8)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 200)
        self._popup.wm_geometry(f"{w}x{count * 22}+{x}+{y}")
        self._popup.deiconify()
        self._popup.lift()

    def _hide(self, *_) -> None:
        if self._popup:
            self._popup.withdraw()

    def _focus_lb(self, event=None) -> None:
        if self._lb and self._lb.size():
            self._lb.focus_set()
            self._lb.selection_set(0)

    def _pick(self, event=None) -> None:
        if not self._lb:
            return
        sel = self._lb.curselection()
        if not sel:
            return
        picked = self._lb.get(sel[0])
        current = self._var.get()
        if "," in current:
            prefix = current.rsplit(",", 1)[0].rstrip() + ", "
        else:
            prefix = ""
        self._var.set(prefix + picked)
        self.icursor("end")
        self._hide()
        self.focus_set()


def _date_entry(parent, textvariable: tk.StringVar, width: int = 12, **kw):
    """Return a tkcalendar DateEntry if available, else a plain ttk.Entry.

    Either way the widget reads/writes YYYY-MM-DD through *textvariable*.
    NOTE: Do NOT pass textvariable to DateEntry — it confuses the internal
    date parser. Instead we initialise via set_date() and keep the var in
    sync through event bindings.
    """
    if _HAVE_CAL:
        from datetime import date as _date

        de = _DateEntry(parent, date_pattern="yyyy-mm-dd", width=width, **kw)

        # Initialise from the StringVar's current value
        initial = textvariable.get()
        try:
            y, m, d = map(int, initial.split("-"))
            de.set_date(_date(y, m, d))
        except Exception:
            pass  # Leave as today's date

        # Keep StringVar in sync whenever the user picks a date or leaves the field
        def _sync(*_):
            try:
                textvariable.set(de.get_date().strftime("%Y-%m-%d"))
            except Exception:
                pass

        de.bind("<<DateEntrySelected>>", _sync)
        de.bind("<FocusOut>", _sync)
        return de
    else:
        return ttk.Entry(parent, textvariable=textvariable, width=width, **kw)


class App(tk.Tk):
    # ── Design-system type ramp (Tkinter pt sizes, tuned per Implementation Notes) ──
    FONT_FAMILY = "Segoe UI"
    FONTS = {
        "display":     ("Segoe UI", 22, "bold"),   # app header
        "title":       ("Segoe UI", 19, "bold"),   # section / dialog titles (prototype: 19px)
        "card_title":  ("Segoe UI", 16, "bold"),   # game name on a card (prototype: 16px)
        "card_year":   ("Segoe UI", 13),           # year below card title (prototype: 13px)
        "card_specs":  ("Segoe UI", 13),           # players/time specs (prototype: 13.5→13 in Tk)
        "card_bestat": ("Segoe UI", 13, "bold"),   # best-at line
        "body":        ("Segoe UI", 11),           # general body text
        "body_strong": ("Segoe UI", 11, "bold"),
        "control":     ("Segoe UI", 11, "bold"),   # button text
        "label":       ("Segoe UI", 12, "bold"),   # UPPERCASE filter labels (prototype: 12px)
        "chip":        ("Segoe UI", 13, "bold"),   # active-filter chips (prototype: 13px)
        "meta":        ("Segoe UI", 14),           # count / sort row (prototype: 14px)
        "loaned_to":   ("Segoe UI", 13),           # "To Name · due Date" line
    }

    # Gradient palette for cover placeholders (inspired by prototype game colours)
    _COVER_PALETTES = [
        ("#7B341E", "#C05621"),  # rust-orange
        ("#553C9A", "#9F7AEA"),  # purple
        ("#975A16", "#D69E2E"),  # amber-gold
        ("#1A365D", "#4299E1"),  # deep blue
        ("#276749", "#48BB78"),  # forest green
        ("#822727", "#E53E3E"),  # crimson
        ("#285E61", "#38B2AC"),  # teal
        ("#322659", "#6B46C1"),  # indigo
        ("#0E2A47", "#1B4B79"),  # navy (design-system)
        ("#7B2D00", "#C05621"),  # burnt sienna
        ("#1A202C", "#4A5568"),  # charcoal
        ("#3C1A54", "#805AD5"),  # violet
    ]
    # ── Spacing scale — multiples of 4 (design-tokens.json) ──
    SP = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}

    def __init__(self) -> None:
        super().__init__()
        self.title("Board Game Library")

        # ── DPI scaling ───────────────────────────────────────────────────────
        # The process is marked DPI-aware (see __main__), so the display now
        # reports its true DPI. Scale Tk's point→pixel factor and our fixed
        # pixel dimensions to that DPI so the whole UI renders crisp and at the
        # right physical size (instead of being bitmap-stretched and blurry).
        try:
            self._ui_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            self._ui_scale = 1.0
        try:
            self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass
        if self._ui_scale > 1.01:
            self._scale_ui_constants(self._ui_scale)

        sc = self._ui_scale
        # Open at the scaled default size, but never larger than the screen.
        w = min(round(1280 * sc), self.winfo_screenwidth()  - 40)
        h = min(round(720 * sc),  self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")
        self.minsize(min(round(980 * sc), w), min(round(560 * sc), h))

        # Window / title-bar icon (also inherited by Toplevel dialogs via
        # default=…). iconbitmap covers the title bar; the taskbar icon is set
        # separately below with a DPI-correct size because Tk hands Windows a
        # fixed ~32px icon that gets upscaled (blurry) on high-DPI taskbars.
        try:
            if sys.platform == "win32":
                self.iconbitmap(default=_resource_path("icon.ico"))
        except Exception:
            pass
        # Set a crisp, DPI-sized taskbar icon via the Win32 API once the
        # top-level window actually exists (deferred to the event loop).
        if sys.platform == "win32":
            self.after(400, self._apply_win_taskbar_icon)

        db.init_db()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = config.load()
        # Migrate any plaintext password left by older versions — move to keychain
        if _stale_pwd := self.settings.pop("bgg_password", None):
            _kr_set_password(_stale_pwd)
            config.save(self.settings)
        # Backfill: an existing single-collection library becomes one named collection
        with db.connect() as c:
            db.ensure_collection_migration(
                c,
                default_username=self.settings.get("bgg_username", ""),
                default_name=self.settings.get("bgg_username", "") or "My Collection",
            )
        self._image_cache:    dict[str, ImageTk.PhotoImage] = {}
        self._gradient_cache: dict[int, ImageTk.PhotoImage] = {}  # palette_idx → gradient
        self._placeholder_img: Optional[ImageTk.PhotoImage] = None
        self._search_after_id: Optional[str] = None
        self._view_mode: str = self.settings.get("view_mode", "cards")
        self._card_size: str = self.settings.get("card_size", "md")
        self._sort_col: Optional[str] = None
        self._sort_rev: bool = False
        self._table_games: list = []
        self._card_games: list = []      # full ordered list backing the card view
        self._cards_rendered: int = 0    # how many card widgets are built (batched)
        self._card_open_loans: dict = {}
        self._card_play_counts: dict = {}
        self._lazy_generation: int = 0   # incremented each refresh to cancel stale loaders
        # ── multi-collection state ──
        self._active_collection: Optional[int] = None   # None = "All"
        self._compare_mode: str = "off"                 # off | shared | only | diff
        self._compare_other: Optional[int] = None
        self._collections: list = []                    # cached collection rows
        self._gc_map: dict = {}                          # {game_id: {collection_id,...}}
        self._my_collection_ids = None                   # collections owned by "me" (None = no claim)
        self._collection_sig = None                     # rebuild guard for the tab bar

        apply_theme(self.settings.get("ui_theme", "Classic Navy"))
        self.configure(bg=C_BG)          # grey canvas so white cards separate visually
        self._apply_style()
        self._build_menubar()
        self._build_header()
        self._build_tabs()   # toolbar now built inside _build_games_tab()
        self._build_status_bar()

        self.refresh_all()

        # Show first-run setup guide if this is a fresh install
        if not self.settings.get("welcome_shown"):
            self.after(300, self._show_welcome_dialog)

        # BGG sync is manual — use Library → Sync from BGG…

    # ---------- first-run welcome ----------

    def _show_welcome_dialog(self) -> None:
        win = tk.Toplevel(self)
        win.title("Welcome to Board Game Library")
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg=C_BG)

        # ── header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=C_NAVY, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\U0001f3b2", bg=C_NAVY, fg=C_WHITE,
                 font=("Segoe UI", 28)).pack()
        tk.Label(hdr, text="Welcome to Board Game Library!",
                 bg=C_NAVY, fg=C_WHITE,
                 font=("Segoe UI", 14, "bold")).pack(pady=(2, 0))
        tk.Label(hdr, text="Let's get your collection set up.",
                 bg=C_NAVY, fg=C_SKY,
                 font=("Segoe UI", 10)).pack(pady=(2, 0))

        # ── body ──────────────────────────────────────────────────────────────
        body = tk.Frame(win, bg=C_BG, padx=28, pady=16)
        body.pack(fill="both", expand=True)

        def section(parent, number: str, title: str, color=C_NAVY):
            row = tk.Frame(parent, bg=C_BG)
            row.pack(fill="x", pady=(10, 2))
            tk.Label(row, text=number, bg=C_BLUE, fg=C_WHITE,
                     font=("Segoe UI", 10, "bold"),
                     width=3, pady=2).pack(side="left", anchor="n")
            tk.Label(row, text=f"  {title}", bg=C_BG, fg=color,
                     font=("Segoe UI", 10, "bold")).pack(side="left", anchor="w")

        def bullet(parent, text: str):
            row = tk.Frame(parent, bg=C_BG)
            row.pack(fill="x")
            tk.Label(row, text="    •", bg=C_BG, fg=C_TEXT,
                     font=("Segoe UI", 9)).pack(side="left", anchor="n")
            tk.Label(row, text=f"  {text}", bg=C_BG, fg=C_TEXT,
                     font=("Segoe UI", 9), justify="left",
                     wraplength=400).pack(side="left", anchor="w")

        def link_btn(parent, text: str, url: str):
            tk.Button(
                parent, text=f"    ↗  {text}",
                bg=C_BG, fg=C_BLUE, relief="flat", cursor="hand2",
                font=("Segoe UI", 9, "underline"), anchor="w",
                command=lambda u=url: _open_url(u),
            ).pack(anchor="w", padx=(16, 0))

        # ── Step 1 ────────────────────────────────────────────────────────────
        section(body, "1", "Import from BGG  (easiest)")
        bullet(body, 'Use File → Import from BGG… and enter your BGG username.')
        bullet(body, "Your BGG collection must be set to public.")
        link_btn(body, "boardgamegeek.com/collection/user/YOUR_USERNAME",
                 "https://boardgamegeek.com/collection")

        # divider
        tk.Frame(body, bg=C_PALE, height=1).pack(fill="x", pady=(14, 0))
        tk.Label(body, text="  — OR —",
                 bg=C_BG, fg=C_INK_500, font=("Segoe UI", 9, "italic")).pack(anchor="w")
        tk.Frame(body, bg=C_PALE, height=1).pack(fill="x", pady=(0, 4))

        # ── Step 1 alt ────────────────────────────────────────────────────────
        section(body, "1b", "Export your collection as a CSV")
        bullet(body, "Log into BoardGameGeek and open your collection.")
        bullet(body, 'Click the export / download icon → choose CSV format.')
        bullet(body, 'Use File → Import collection CSV… to load it.')
        bullet(body, "Note: your CSV may not include image URLs — use File → Download Images after importing.")

        # ── Step 2 ────────────────────────────────────────────────────────────
        section(body, "2", "You're done!")
        bullet(body, "Browse your games, check them out to members, and log plays.")
        bullet(body, 'Use Library → Add Game… to manually add games not on BGG.')

        # ── footer ────────────────────────────────────────────────────────────
        tk.Frame(win, bg=C_BLUE, height=1).pack(fill="x")
        footer = tk.Frame(win, bg=C_PALE, pady=10, padx=28)
        footer.pack(fill="x")

        def close() -> None:
            self.settings["welcome_shown"] = True
            config.save(self.settings)
            win.destroy()

        tk.Button(
            footer, text="Get Started",
            bg=C_BLUE_600, fg=C_SURFACE,
            activebackground=C_BLUE_700, activeforeground=C_SURFACE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=14, pady=5, cursor="hand2",
            command=close,
        ).pack(side="right")

        win.grab_set()

    # ---------- style / theme ----------

    def _apply_style(self) -> None:
        """Map the design tokens to ttk.Style.

        Built from scratch off design-tokens.json + the Implementation Notes:
          • clam theme (only theme that honours colour overrides everywhere)
          • type ramp:  Display 22 / Title 15 / Card-title 13 / Body 11 / Label 9-bold
          • spacing scale: 4 / 8 / 12 / 16 / 24
          • one filled primary button; everything else is Ghost / Quiet
        """
        s = ttk.Style(self)
        s.theme_use("clam")   # clam respects colour overrides on all platforms

        FONT = self.FONT_FAMILY

        # ── Global defaults ────────────────────────────────────────────────────
        s.configure(".",
            background=C_BG, foreground=C_INK_900,
            font=self.FONTS["body"])

        # ── Frames ─────────────────────────────────────────────────────────────
        s.configure("TFrame",      background=C_BG)
        s.configure("Card.TFrame",    background=C_SURFACE)
        s.configure("TLabelframe",    background=C_BG)
        s.configure("TLabelframe.Label", background=C_BG, foreground=C_NAVY_900,
                    font=self.FONTS["body_strong"])

        # ── Labels ─────────────────────────────────────────────────────────────
        s.configure("TLabel", background=C_BG, foreground=C_INK_900,
                    font=self.FONTS["body"])
        s.configure("Muted.TLabel",  background=C_BG, foreground=C_INK_500,
                    font=self.FONTS["body"])
        s.configure("Section.TLabel", background=C_BG, foreground=C_NAVY_900,
                    font=self.FONTS["title"])

        # ── Buttons — Primary (the single filled action per context) ───────────
        s.configure("TButton",
            background=C_BLUE_600, foreground=C_SURFACE,
            font=self.FONTS["control"],
            padding=[self.SP["lg"], self.SP["xs"] + 2],
            relief="flat", borderwidth=0,
            focusthickness=3, focuscolor=C_BLUE_700)
        s.map("TButton",
            background=[("pressed", C_BLUE_800), ("active", C_BLUE_700),
                        ("disabled", C_LINE_200)],
            foreground=[("disabled", C_INK_500),
                        ("pressed", C_SURFACE), ("active", C_SURFACE)])

        # ── Buttons — Ghost (outline / secondary) ──────────────────────────────
        s.configure("Ghost.TButton",
            background=C_SURFACE, foreground=C_INK_900,
            font=self.FONTS["body"],
            padding=[self.SP["lg"], self.SP["xs"] + 2],
            relief="solid", borderwidth=1)
        s.map("Ghost.TButton",
            background=[("pressed", C_BG), ("active", C_BG)],
            foreground=[("pressed", C_INK_900), ("active", C_INK_900)],
            bordercolor=[("active", C_INK_500), ("!disabled", C_LINE_200)])

        # ── Buttons — Quiet (text-only) ────────────────────────────────────────
        s.configure("Quiet.TButton",
            background=C_BG, foreground=C_BLUE_700,
            font=self.FONTS["body"],
            padding=[self.SP["sm"], self.SP["xs"]],
            relief="flat", borderwidth=0)
        s.map("Quiet.TButton",
            background=[("active", C_BLUE_050)],
            foreground=[("active", C_BLUE_700)])

        # ── Buttons — Danger ───────────────────────────────────────────────────
        s.configure("Danger.TButton",
            background=C_DR_SOLID, foreground=C_SURFACE,
            font=self.FONTS["control"],
            padding=[self.SP["lg"], self.SP["xs"] + 2],
            relief="flat", borderwidth=0)
        s.map("Danger.TButton",
            background=[("active", "#a01e18")])

        # ── Notebook tabs (navy-800 strip) ─────────────────────────────────────
        s.configure("TNotebook", background=C_NAVY_800, borderwidth=0,
                    tabmargins=[2, 6, 2, 0])
        s.configure("TNotebook.Tab",
            background=C_NAVY_800, foreground="#C7D6E6",
            font=("Segoe UI", 9),
            padding=[self.SP["sm"], self.SP["xs"] + 2],
            focuscolor="")
        s.map("TNotebook.Tab",
            background=[("selected", C_BG), ("active", "#1E4A73")],
            foreground=[("selected", C_NAVY_900), ("active", C_SURFACE)],
            font=[("selected", self.FONTS["control"])],
            padding=[("selected", [self.SP["xl"], self.SP["sm"] + 1])],
            expand=[("selected", [1, 3, 1, 0])])

        # ── Entry / Combobox ───────────────────────────────────────────────────
        s.configure("TEntry",
            fieldbackground=C_SURFACE, foreground=C_INK_900,
            insertcolor=C_BLUE_600, bordercolor=C_LINE_200,
            padding=[self.SP["sm"], self.SP["xs"] + 2])
        s.map("TEntry", bordercolor=[("focus", C_BLUE_600)])
        s.configure("TCombobox",
            fieldbackground=C_SURFACE, foreground=C_INK_900,
            selectbackground=C_BLUE_600, selectforeground=C_SURFACE,
            bordercolor=C_LINE_200, arrowcolor=C_INK_500,
            padding=[self.SP["sm"], self.SP["xs"] + 1])
        s.map("TCombobox",
            fieldbackground=[("readonly", C_SURFACE), ("focus", C_BLUE_050)],
            bordercolor=[("focus", C_BLUE_600)])

        # ── Checkbutton / Radiobutton ──────────────────────────────────────────
        s.configure("TCheckbutton", background=C_BG, foreground=C_INK_900,
                    font=self.FONTS["body"])
        s.map("TCheckbutton", background=[("active", C_BG)])
        s.configure("TRadiobutton", background=C_BG, foreground=C_INK_900,
                    font=self.FONTS["body"])
        s.map("TRadiobutton", background=[("active", C_BG)])

        # ── Treeview (table view) ──────────────────────────────────────────────
        s.configure("Treeview",
            background=C_SURFACE, fieldbackground=C_SURFACE,
            foreground=C_INK_900, rowheight=32, borderwidth=0,
            font=self.FONTS["body"])
        s.configure("Treeview.Heading",
            background=C_NAVY_900, foreground=C_SURFACE,
            font=self.FONTS["label"], relief="flat", padding=[self.SP["sm"], 6])
        s.map("Treeview.Heading", background=[("active", C_NAVY_800)])
        s.map("Treeview",
            background=[("selected", C_BLUE_050)],
            foreground=[("selected", C_INK_900)])

        # ── Scrollbar ──────────────────────────────────────────────────────────
        s.configure("TScrollbar",
            background=C_LINE_100, troughcolor=C_BG,
            arrowcolor=C_INK_500, borderwidth=0)

        # ── Separator ──────────────────────────────────────────────────────────
        s.configure("TSeparator", background=C_LINE_200)

        # ── Toolbar / filter bar helpers ───────────────────────────────────────
        s.configure("Filter.TFrame", background=C_BG)
        s.configure("Filter.TLabel", background=C_BG, foreground=C_INK_600,
                    font=self.FONTS["label"], padding=(0, 0, 2, 0))
        s.configure("Count.TLabel",  background=C_BG, foreground=C_INK_600,
                    font=self.FONTS["meta"])
        s.configure("Filter.TCheckbutton", background=C_BG, foreground=C_INK_900,
                    font=self.FONTS["body"])
        s.map("Filter.TCheckbutton", background=[("active", C_BG)])
        s.configure("Count.TLabel", background=C_BG, foreground=C_INK_600,
                    font=self.FONTS["body"])

        # ── Status bar (navy-900) ──────────────────────────────────────────────
        s.configure("Status.TFrame", background=C_NAVY_900)
        s.configure("Status.TLabel", background=C_NAVY_900, foreground=C_SURFACE,
                    font=self.FONTS["body"])
        # Determinate progress bar shown in the status strip during long tasks.
        s.configure("Status.Horizontal.TProgressbar",
                    troughcolor=C_NAVY_800, background=C_BLUE_600,
                    bordercolor=C_NAVY_800, lightcolor=C_BLUE_600,
                    darkcolor=C_BLUE_600, thickness=10)

    # ---------- layout ----------

    def _build_menubar(self) -> None:
        """OS-native menu bar: File | Library | Help."""
        self.option_add("*tearOff", False)
        menubar = tk.Menu(self)

        # ── File ──────────────────────────────────────────────────────────────
        file_menu = tk.Menu(menubar)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import from BGG…",       command=self.on_import_from_bgg)
        file_menu.add_command(label="Import collection CSV…", command=self.on_import_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Download Images",        command=self.on_download_images)
        file_menu.add_command(label="Upgrade Image Quality…", command=self.on_upgrade_images)
        file_menu.add_separator()
        file_menu.add_command(label="Export Library…",        command=self.on_export_data)
        file_menu.add_command(label="Import Library…",        command=self.on_import_data)
        file_menu.add_command(label="Export for Mobile…",     command=self.on_export_for_mobile)
        file_menu.add_separator()
        file_menu.add_command(label="Export Plays to CSV…",       command=self.on_export_plays_csv)
        file_menu.add_command(label="Export Loan History to CSV…", command=self.on_export_loans_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Import BGG Play History…",    command=self.on_import_bgg_plays)
        file_menu.add_separator()
        file_menu.add_command(label="Settings…",             command=self.on_open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",                   command=self.destroy)

        # ── Library ───────────────────────────────────────────────────────────
        lib_menu = tk.Menu(menubar)
        menubar.add_cascade(label="Library", menu=lib_menu)
        lib_menu.add_command(label="Sync from BGG…", command=self.on_import_from_bgg)
        lib_menu.add_separator()
        lib_menu.add_command(label="Add Game…", command=self.on_add_game)
        lib_menu.add_command(label="Pick a Random Game…", command=self.on_random_game)

        # ── View ──────────────────────────────────────────────────────────────
        view_menu = tk.Menu(menubar)
        menubar.add_cascade(label="View", menu=view_menu)
        theme_menu = tk.Menu(view_menu)
        view_menu.add_cascade(label="Colour Theme", menu=theme_menu)
        self._theme_var = tk.StringVar(value=self.settings.get("ui_theme", "Classic Navy"))
        for _name in THEMES:
            theme_menu.add_radiobutton(
                label=_name, value=_name, variable=self._theme_var,
                command=lambda n=_name: self.on_set_theme(n))

        # ── Help ──────────────────────────────────────────────────────────────
        help_menu = tk.Menu(menubar)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About…", command=self.on_about)

        self.config(menu=menubar)

    def on_set_theme(self, name: str) -> None:
        """Switch the UI colour theme live and remember the choice."""
        self.settings["ui_theme"] = name
        config.save(self.settings)
        apply_theme(name)
        if hasattr(self, "_theme_var"):
            self._theme_var.set(name)
        # ttk styles repaint all styled widgets; reconfigure the tk header band
        # and repaint the cards/chips/dashboard with the new colours.
        self._apply_style()
        if hasattr(self, "_hdr"):
            self._hdr.configure(bg=C_NAVY_900)
            self._hdr_inner.configure(bg=C_NAVY_900)
            self._hdr_logo.configure(bg=C_NAVY_900)
            self._hdr_title.configure(bg=C_NAVY_900)
        self._collection_sig = None      # force the collection tab bar to recolour
        self.refresh_games()
        self.refresh_dashboard()
        self.status(f"Theme: {name}")

    def _build_header(self) -> None:
        """Navy-900 app bar: white logo chip + title on its own band (kept compact)."""
        self._hdr = tk.Frame(self, bg=C_NAVY_900)
        self._hdr.pack(side="top", fill="x")

        self._hdr_inner = tk.Frame(self._hdr, bg=C_NAVY_900)
        self._hdr_inner.pack(side="left", padx=self.SP["lg"], pady=self.SP["xs"])

        # Logo chip — the actual program icon in a white square (falls back to a
        # die glyph if the icon can't be loaded).
        try:
            _logo_im = Image.open(_resource_path("icon.ico")).convert("RGBA").resize((28, 28), Image.LANCZOS)
            self._hdr_logo_img = ImageTk.PhotoImage(_logo_im)
            self._hdr_logo = tk.Label(self._hdr_inner, image=self._hdr_logo_img,
                                      bg=C_NAVY_900, bd=0, padx=0, pady=0)
        except Exception:
            self._hdr_logo = tk.Label(
                self._hdr_inner, text="\U0001f3b2",
                bg=C_NAVY_900, fg=C_SURFACE,
                font=("Segoe UI", 14, "bold"), padx=2, pady=1,
            )
        self._hdr_logo.pack(side="left", padx=(0, self.SP["sm"]))

        self._hdr_title = tk.Label(
            self._hdr_inner, text="Board Game Library",
            bg=C_NAVY_900, fg=C_SURFACE,
            font=("Segoe UI", 15, "bold"),
        )
        self._hdr_title.pack(side="left")

        # Hairline under the app bar (line_200 over the navy/grey seam)
        tk.Frame(self, bg=C_LINE_200, height=1).pack(side="top", fill="x")

    def _build_toolbar(self, parent=None) -> None:
        """Toolbar (search + segmented view toggle), filter bar, and chips row.

        Built from the prototype's .toolbar / .filters / .chips structure:
          • search-first: one wide labelled input + a Quiet "Clear"
          • one segmented Grid/Table toggle with a clear pressed state
          • each filter = an UPPERCASE label sitting above its control
          • a Quiet "Reset filters" and a live game count
        """
        parent = parent or self
        SP = self.SP

        # ── toolbar row: search field (expands) + segmented view toggle ─────────
        bar = ttk.Frame(parent, padding=(SP["lg"], SP["md"], SP["lg"], SP["xs"]))
        bar.pack(side="top", fill="x")

        search_field = ttk.Frame(bar, style="Filter.TFrame")
        search_field.pack(side="left", fill="x", expand=True, padx=(0, SP["md"]))
        ttk.Label(search_field, text="SEARCH", style="Filter.TLabel").pack(anchor="w")

        self.search_var = tk.StringVar()
        def _on_search_changed(*_):
            if self._search_after_id:
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(250, self.refresh_games)
        self.search_var.trace_add("write", _on_search_changed)

        search_row = ttk.Frame(search_field, style="Filter.TFrame")
        search_row.pack(fill="x")
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text="Clear", style="Quiet.TButton",
                   command=lambda: self.search_var.set("")).pack(side="left", padx=(SP["xs"], 0))

        # VIEW dropdown
        view_field = ttk.Frame(bar, style="Filter.TFrame")
        view_field.pack(side="right")
        ttk.Label(view_field, text="VIEW", style="Filter.TLabel").pack(anchor="w")
        self._view_var = tk.StringVar(value="Cards" if self._view_mode == "cards" else "Table")
        view_cb = ttk.Combobox(view_field, textvariable=self._view_var,
                               values=["Cards", "Table"], state="readonly", width=7)
        view_cb.pack()
        view_cb.bind("<<ComboboxSelected>>",
                     lambda e: self._set_view(
                         "cards" if self._view_var.get() == "Cards" else "table"))

        # SIZE dropdown — only visible in card view
        self._size_field = ttk.Frame(bar, style="Filter.TFrame")
        if self._view_mode == "cards":
            self._size_field.pack(side="right", padx=(0, SP["md"]))
        ttk.Label(self._size_field, text="SIZE", style="Filter.TLabel").pack(anchor="w")
        _sz_labels = {"sm": "Small", "md": "Medium", "lg": "Large"}
        _sz_keys   = {"Small": "sm", "Medium": "md", "Large": "lg"}
        self._size_var = tk.StringVar(value=_sz_labels[self._card_size])
        size_cb = ttk.Combobox(self._size_field, textvariable=self._size_var,
                               values=["Small", "Medium", "Large"], state="readonly", width=7)
        size_cb.pack()
        size_cb.bind("<<ComboboxSelected>>",
                     lambda e: self._set_card_size(_sz_keys[self._size_var.get()]))

        # ── filter bar: labelled groups, bottom-aligned ────────────────────────
        fbar = ttk.Frame(parent, style="Filter.TFrame",
                         padding=(SP["lg"], SP["xs"], SP["lg"], SP["sm"]))
        fbar.pack(side="top", fill="x")

        def fgroup(label_text, widget_factory):
            frame = ttk.Frame(fbar, style="Filter.TFrame")
            frame.pack(side="left", padx=(0, SP["md"]), anchor="s")
            ttk.Label(frame, text=label_text, style="Filter.TLabel").pack(anchor="w")
            w = widget_factory(frame)
            w.pack(fill="x")
            return w

        def fcheck(text, var):
            """A checkbox bottom-aligned to sit level with the combobox controls."""
            frame = ttk.Frame(fbar, style="Filter.TFrame")
            frame.pack(side="left", padx=(0, SP["md"]), anchor="s")
            ttk.Label(frame, text=" ", style="Filter.TLabel").pack(anchor="w")  # spacer
            ttk.Checkbutton(frame, text=text, variable=var,
                            command=self.refresh_games,
                            style="Filter.TCheckbutton").pack(anchor="w", pady=(0, 3))

        self.players_var = tk.StringVar(value="Any")
        fgroup("PLAYERS", lambda p: ttk.Combobox(
            p, textvariable=self.players_var, width=7, state="readonly",
            values=["Any", "1", "2", "3", "4", "5", "6", "7", "8+"],
        )).bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.exact_players_var = tk.BooleanVar(value=False)
        fcheck("Exact count", self.exact_players_var)

        self.best_at_var = tk.StringVar(value="Any")
        fgroup("BEST AT", lambda p: ttk.Combobox(
            p, textvariable=self.best_at_var, width=7, state="readonly",
            values=["Any", "1", "2", "3", "4", "5", "6", "7", "8+"],
        )).bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.time_var = tk.StringVar(value="Any")
        fgroup("PLAY TIME", lambda p: ttk.Combobox(
            p, textvariable=self.time_var, width=12, state="readonly",
            values=["Any", "≤ 30 min", "31–60 min", "61–90 min", "91–120 min", "121+ min"],
        )).bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.weight_var = tk.StringVar(value="Any")
        fgroup("COMPLEXITY", lambda p: ttk.Combobox(
            p, textvariable=self.weight_var, width=12, state="readonly",
            values=["Any", "Light (1–2)", "Medium (2–3)", "Heavy (3–5)"],
        )).bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.status_filter_var = tk.StringVar(value="Any")
        fgroup("STATUS", lambda p: ttk.Combobox(
            p, textvariable=self.status_filter_var, width=12, state="readonly",
            values=["Any", "Available", "Checked out", "Favorites"],
        )).bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.tag_filter_var = tk.StringVar(value="Any")
        self.tag_filter_cb = fgroup("TAG", lambda p: ttk.Combobox(
            p, textvariable=self.tag_filter_var, width=12, state="readonly",
            values=["Any"],
        ))
        self.tag_filter_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        reset_frame = ttk.Frame(fbar, style="Filter.TFrame")
        reset_frame.pack(side="left", padx=(SP["xs"], SP["lg"]), anchor="s")
        ttk.Label(reset_frame, text=" ", style="Filter.TLabel").pack(anchor="w")
        ttk.Button(reset_frame, text="Reset filters", style="Quiet.TButton",
                   command=self._reset_filters).pack(anchor="w", pady=(0, 3))

        # ── Sort by + game count — right side of the same filter bar row ─────────
        sort_rhs = ttk.Frame(fbar, style="Filter.TFrame")
        sort_rhs.pack(side="right", anchor="s", pady=(0, 3))
        self._sort_var = tk.StringVar(value="Title (A–Z)")
        sort_cb = ttk.Combobox(sort_rhs, textvariable=self._sort_var, state="readonly",
                               width=13,
                               values=["Title (A–Z)", "Year (newest)", "Most played",
                                       "Complexity ↑", "Complexity ↓"])
        sort_cb.pack(side="right")
        ttk.Label(sort_rhs, text="Sort by", style="Count.TLabel").pack(side="right",
                                                                        padx=(SP["md"], SP["xs"]))
        self._count_label = ttk.Label(sort_rhs, text="", style="Count.TLabel")
        self._count_label.pack(side="right", padx=(0, SP["lg"]))
        sort_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        # ── active-filter chips row — always packed here so it stays in the
        # correct position above the card grid; children are added/removed by
        # _refresh_chips() without ever re-packing the frame itself.
        self._chips_frame = ttk.Frame(parent, style="Filter.TFrame",
                                      padding=(SP["lg"], 0, SP["lg"], SP["xs"]))
        self._chips_frame.pack(side="top", fill="x")

    def _refresh_chips(self) -> None:
        """Rebuild the active-filter chips row below the filter bar."""
        for w in self._chips_frame.winfo_children():
            w.destroy()

        active: list[tuple] = []
        if self.search_var.get():
            v = self.search_var.get()
            active.append(("Search", v, lambda: self.search_var.set("")))
        if self.players_var.get() != "Any":
            v = self.players_var.get()
            active.append(("Players", v, lambda _v=v: self.players_var.set("Any")))
        if self.exact_players_var.get():
            active.append(("Exact", "on", lambda: self.exact_players_var.set(False)))
        if self.best_at_var.get() != "Any":
            v = self.best_at_var.get()
            active.append(("Best at", v, lambda _v=v: self.best_at_var.set("Any")))
        if self.time_var.get() != "Any":
            v = self.time_var.get()
            active.append(("Time", v, lambda _v=v: self.time_var.set("Any")))
        if self.weight_var.get() != "Any":
            v = self.weight_var.get()
            active.append(("Complexity", v, lambda _v=v: self.weight_var.set("Any")))
        if self.status_filter_var.get() != "Any":
            v = self.status_filter_var.get()
            active.append(("Status", v, lambda _v=v: self.status_filter_var.set("Any")))
        if self.tag_filter_var.get() != "Any":
            v = self.tag_filter_var.get()
            active.append(("Tag", v, lambda _v=v: self.tag_filter_var.set("Any")))

        # Never re-pack the frame — it's already in the correct position above
        # the card grid. Just populate or clear its children.
        for label, value, clear_fn in active:
            chip = tk.Frame(self._chips_frame, bg=C_BLUE_050)
            chip.pack(side="left", padx=(0, self.SP["sm"]), pady=(0, 2))
            tk.Label(chip, text=f"{label}: {value}",
                     bg=C_BLUE_050, fg=C_BLUE_800,
                     font=self.FONTS["chip"],
                     padx=self.SP["md"], pady=self.SP["xs"]).pack(side="left")

            def _make_dismiss(fn):
                def _dismiss():
                    fn()
                    self.refresh_games()
                return _dismiss

            tk.Button(chip, text="×",
                      bg=C_BLUE_050, fg=C_BLUE_700,
                      activebackground=C_SURFACE, activeforeground=C_BLUE_700,
                      font=("Segoe UI", 11, "bold"),
                      relief="flat", bd=0, padx=self.SP["sm"], pady=1,
                      cursor="hand2",
                      command=_make_dismiss(clear_fn)).pack(side="left")

    def _build_tabs(self) -> None:
        self.nb = ttk.Notebook(self)
        self.nb.pack(side="top", fill="both", expand=True)

        self.games_tab = ttk.Frame(self.nb)
        self.members_tab = ttk.Frame(self.nb)
        self.history_tab = ttk.Frame(self.nb)
        self.plays_tab = ttk.Frame(self.nb)
        self.dashboard_tab = ttk.Frame(self.nb)

        # Tab order matches the mobile app: Dashboard, Games, Members, Plays, History
        self.nb.add(self.dashboard_tab, text="Dashboard")
        self.nb.add(self.games_tab, text="Games")
        self.nb.add(self.members_tab, text="Members")
        self.nb.add(self.plays_tab, text="Plays")
        self.nb.add(self.history_tab, text="History")

        self._build_games_tab()
        self._build_members_tab()
        self._build_history_tab()
        self._build_plays_tab()
        self._build_dashboard_tab()

        self.bind_all("<MouseWheel>", self._on_scroll)

    def _scale_ui_constants(self, sc: float) -> None:
        """Scale the app's fixed *pixel* dimensions by the DPI factor so the UI
        keeps the same physical size while rendering crisp. Font point sizes are
        left alone — Tk's scaling factor handles those."""
        # Spacing scale (class dict → shadow with a scaled per-instance copy).
        self.SP = {k: max(1, round(v * sc)) for k, v in App.SP.items()}
        # Card-size presets: scale pixel fields only (not the 'title'/'sub' pts).
        for preset in _CARD_SIZES.values():
            for key in ("card_w", "cover_h", "wrap"):
                if key in preset:
                    preset[key] = round(preset[key] * sc)

    def _apply_win_taskbar_icon(self) -> None:
        """Reinforce the taskbar button icon at the exact DPI size from
        icon.ico, so the running window's big icon is as crisp as Windows can
        render it at the current display scaling."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            IMAGE_ICON      = 1
            LR_LOADFROMFILE = 0x0010
            WM_SETICON      = 0x0080
            ICON_BIG        = 1

            user32.LoadImageW.restype  = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                          wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                          wintypes.UINT]
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                            wintypes.WPARAM, wintypes.LPARAM]

            hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
            try:
                dpi = user32.GetDpiForWindow(hwnd) or 96
            except Exception:
                dpi = 96
            big = max(16, round(32 * dpi / 96))     # 32@100% 48@150% 64@200%

            path = _resource_path("icon.ico")
            self._hicon_big = user32.LoadImageW(
                None, path, IMAGE_ICON, big, big, LR_LOADFROMFILE)
            if self._hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, self._hicon_big)
        except Exception:
            pass

    def _build_status_bar(self) -> None:
        """Navy-900 status strip pinned to the bottom edge, with a progress bar
        and an "X of N" count that appear during long tasks (sync / downloads)."""
        self.status_var = tk.StringVar(value="Ready.")
        self._progress_var = tk.StringVar(value="")
        bar = ttk.Frame(self, style="Status.TFrame")
        bar.pack(side="bottom", fill="x")
        ttk.Label(
            bar, textvariable=self.status_var, anchor="w",
            style="Status.TLabel", padding=(self.SP["md"], self.SP["xs"] + 1),
        ).pack(side="left", fill="x", expand=True)

        # Right side: "34 of 269" + determinate progress bar (hidden when idle).
        self._progress_count = ttk.Label(
            bar, textvariable=self._progress_var, anchor="e",
            style="Status.TLabel", padding=(self.SP["sm"], self.SP["xs"] + 1),
        )
        self._progress_bar = ttk.Progressbar(
            bar, style="Status.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", length=160,
        )
        # Not packed yet — _set_progress() packs them when a task is running.
        self._progress_active = False

    # ---------- dashboard tab ----------

    def _build_dashboard_tab(self) -> None:
        outer = ttk.Frame(self.dashboard_tab, padding=self.SP["xl"])
        outer.pack(fill="both", expand=True)

        # Scrollable canvas so the dashboard works at any window height
        vsb = ttk.Scrollbar(outer, orient="vertical")
        vsb.pack(side="right", fill="y")
        canvas = tk.Canvas(outer, highlightthickness=0, bg=C_BG, yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.configure(command=canvas.yview)
        inner = ttk.Frame(canvas)
        _win = canvas.create_window(0, 0, anchor="nw", window=inner)

        def _on_resize(e):
            canvas.itemconfigure(_win, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._dashboard_canvas = canvas
        self._dashboard_inner  = inner

        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        inner = self._dashboard_inner
        for w in inner.winfo_children():
            w.destroy()
        self._dashboard_canvas.yview_moveto(0)   # always start at the top

        with db.connect() as c:
            summary      = db.stats_summary(c)
            checked_out  = db.currently_checked_out(c)
            recent       = db.recent_plays(c, limit=8)
            top_games    = db.top_games_by_plays(c, limit=5)
            top_wins     = db.top_winners(c, limit=5)

        today = datetime.now().date()

        def section(parent, title):
            ttk.Label(parent, text=title,
                      font=self.FONTS["card_title"], foreground=C_NAVY_900,
                      background=C_BG).pack(anchor="w", pady=(self.SP["lg"], self.SP["xs"]))
            ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=(0, self.SP["sm"]))

        def stat_card(parent, label, value, color=C_NAVY_900, tab=None):
            # Solid coloured stat tile (navy / green / purple / red per token map)
            f = tk.Frame(parent, bg=color, padx=self.SP["lg"], pady=self.SP["md"],
                         highlightbackground=color, highlightthickness=1,
                         cursor="hand2" if tab else "")
            f.pack(side="left", expand=True, fill="both", padx=(0, self.SP["sm"]))
            val_lbl = tk.Label(f, text=str(value), bg=color, fg=C_SURFACE,
                               font=self.FONTS["display"])
            val_lbl.pack()
            txt_lbl = tk.Label(f, text=label, bg=color, fg=C_SURFACE,
                               font=self.FONTS["label"])
            txt_lbl.pack()
            if tab is not None:
                _jump = lambda e, t=tab: self.nb.select(t)
                for w in (f, val_lbl, txt_lbl):
                    w.bind("<Button-1>", _jump)
                f.bind("<Enter>", lambda e, fr=f: fr.configure(highlightbackground=C_SURFACE))
                f.bind("<Leave>", lambda e, fr=f, cc=color: fr.configure(highlightbackground=cc))

        # ── stat cards row ────────────────────────────────────────────────────
        cards_row = tk.Frame(inner, bg=C_BG)
        cards_row.pack(fill="x", pady=(0, self.SP["xs"]))
        stat_card(cards_row, "Games",       summary["total_games"],   C_NAVY_900, tab=self.games_tab)
        stat_card(cards_row, "Total Plays", summary["total_plays"],   C_OK_SOLID, tab=self.plays_tab)
        stat_card(cards_row, "Members",     summary["total_members"], "#4A148C",  tab=self.members_tab)
        stat_card(cards_row, "Checked Out", summary["checked_out"],
                  C_DR_SOLID if summary["checked_out"] else C_INK_600,
                  tab=self.history_tab)

        # ── currently checked out ────────────────────────────────────────────
        section(inner, "Currently Checked Out")
        if not checked_out:
            ttk.Label(inner, text="All games are available.",
                      style="Muted.TLabel").pack(anchor="w")
        else:
            cols = ("Game", "Borrower", "Since", "Due")
            tree = ttk.Treeview(inner, columns=cols, show="headings", height=min(len(checked_out), 6))
            for col in cols:
                tree.heading(col, text=col)
            tree.column("Game",     width=220)
            tree.column("Borrower", width=160)
            tree.column("Since",    width=100, anchor="center")
            tree.column("Due",      width=100, anchor="center")
            tree.tag_configure("overdue", foreground=C_DR_TEXT,
                               font=self.FONTS["body_strong"])
            for row in checked_out:
                since = row["checked_out_at"][:10]
                due   = row["due_date"] or "—"
                borrower = f"{row['first_name']} {row['last_name']}".strip()
                overdue = (row["due_date"] and row["due_date"] < str(today))
                tree.insert("", "end", values=(row["game_name"], borrower, since, due),
                            tags=("overdue",) if overdue else ())
            tree.pack(fill="x")

        # ── two-column lower section ─────────────────────────────────────────
        lower = tk.Frame(inner, bg=C_BG)
        lower.pack(fill="both", expand=True, pady=(self.SP["sm"], 0))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)

        # Recent plays (left)
        lf = ttk.Frame(lower)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, self.SP["sm"]))
        section(lf, "Recent Plays")
        if not recent:
            ttk.Label(lf, text="No plays logged yet.", style="Muted.TLabel").pack(anchor="w")
        else:
            for r in recent:
                date = r["played_at"][:10]
                winner = f"  🏆 {r['winner']}" if r["winner"] else ""
                ttk.Label(lf, text=f"{date}  {r['game_name']}{winner}",
                          font=self.FONTS["body"]).pack(anchor="w", pady=1)

        # Top games + top winners (right)
        rf = ttk.Frame(lower)
        rf.grid(row=0, column=1, sticky="nsew")
        section(rf, "Most Played")
        if not top_games:
            ttk.Label(rf, text="No plays yet.", style="Muted.TLabel").pack(anchor="w")
        else:
            for i, r in enumerate(top_games, 1):
                ttk.Label(rf, text=f"{i}. {r['name']}  ({r['play_count']} play{'s' if r['play_count'] != 1 else ''})",
                          font=self.FONTS["body"]).pack(anchor="w", pady=1)

        section(rf, "Top Winners")
        if not top_wins:
            ttk.Label(rf, text="No winners recorded yet.", style="Muted.TLabel").pack(anchor="w")
        else:
            for i, r in enumerate(top_wins):
                row = tk.Frame(rf, bg=C_BG)
                row.pack(fill="x", pady=1)
                rank = i  # 0-based
                if rank < 3:
                    key = (rank, 38)
                    if not hasattr(self, '_ribbon_photos'):
                        self._ribbon_photos = {}
                    if key not in self._ribbon_photos:
                        self._ribbon_photos[key] = self._make_ribbon_photo(rank, 38)
                    ph = self._ribbon_photos[key]
                    tk.Label(row, image=ph, bg=C_BG).pack(side="left", padx=(0, self.SP["sm"] - 2))
                else:
                    tk.Label(row, text=f"{i + 1}.", bg=C_BG,
                             font=self.FONTS["body_strong"],
                             foreground=C_INK_500, width=3).pack(side="left", padx=(0, self.SP["sm"] - 2))
                wins = r['win_count']
                ttk.Label(row, text=f"{r['winner']}  ({wins} win{'s' if wins != 1 else ''})",
                          font=self.FONTS["body"]).pack(side="left")

    # ---------- games tab ----------

    def _build_games_tab(self) -> None:
        # Search bar, view toggle, and filter bar — live inside the Games tab
        self._build_toolbar(parent=self.games_tab)

        # Collection tabs + comparison — only populated when ≥2 collections exist.
        self._collection_bar = ttk.Frame(self.games_tab, style="Filter.TFrame")
        self._collection_bar.pack(side="top", fill="x")

        wrapper = ttk.Frame(self.games_tab)
        wrapper.pack(fill="both", expand=True)

        # ── card grid ─────────────────────────────────────────────────────────
        self._card_frame = ttk.Frame(wrapper)

        # A–Z jump bar — rightmost strip (pack right-to-left so canvas gets remainder)
        self._alpha_bar = tk.Frame(self._card_frame, bg=C_BG, width=22)
        self._alpha_bar.pack(side="right", fill="y")
        self._alpha_bar.pack_propagate(False)

        scroll = ttk.Scrollbar(self._card_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self._card_scroll = scroll

        self.games_canvas = tk.Canvas(self._card_frame, highlightthickness=0, background=C_BG,
                                      yscrollcommand=self._card_yscroll)
        scroll.configure(command=self.games_canvas.yview)
        self.games_canvas.pack(side="left", fill="both", expand=True)

        self.games_inner = ttk.Frame(self.games_canvas)
        self.games_window_id = self.games_canvas.create_window((0, 0), window=self.games_inner, anchor="nw")
        self.games_inner.bind("<Configure>", lambda e: self.games_canvas.configure(scrollregion=self.games_canvas.bbox("all")))
        self.games_canvas.bind("<Configure>", self._reflow_games)

        # ── table view ────────────────────────────────────────────────────────
        self._table_frame = ttk.Frame(wrapper)
        self._build_table_widget(self._table_frame)

        self._cards: list[ttk.Frame] = []

        # Show whichever view was last used
        if self._view_mode == "table":
            self._table_frame.pack(fill="both", expand=True)
        else:
            self._card_frame.pack(fill="both", expand=True)

    def _build_table_widget(self, parent: ttk.Frame) -> None:
        cols = ("fav", "insert", "name", "year", "players", "time", "weight", "rating", "best", "status", "plays")
        self.games_tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")

        col_defs = [
            ("fav",     "★",           34,  "center"),
            ("insert",  "📦",          34,  "center"),
            ("name",    "Name",        260, "w"     ),
            ("year",    "Year",         56, "center"),
            ("players", "Players",      88, "center"),
            ("time",    "Time",         92, "center"),
            ("weight",  "Complexity",  104, "center"),
            ("rating",  "BGG ★",        66, "center"),
            ("best",    "Best At",      80, "center"),
            ("status",  "Status",      120, "center"),
            ("plays",   "Plays",        64, "center"),
        ]
        # Fixed-width columns stay put; the "name" column has stretch=True so
        # Tkinter hands all spare horizontal space to it — the table stays
        # adaptive to the window width with no manual bookkeeping.
        for cid, heading, width, anchor in col_defs:
            self.games_tree.heading(cid, text=heading,
                                    command=lambda c=cid: self._sort_table(c))
            self.games_tree.column(cid, width=width, anchor=anchor,
                                   stretch=(cid == "name"),
                                   minwidth=30 if cid != "name" else 120)

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.games_tree.yview)
        self.games_tree.configure(yscrollcommand=vsb.set)
        self.games_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.games_tree.bind("<Double-1>",  self._on_table_double_click)
        self.games_tree.bind("<Return>",    self._on_table_return)
        self.games_tree.bind("<Button-3>",  self._on_table_right_click)

        # Row colour tags
        self.games_tree.tag_configure("out",       background=C_WN_BG)
        self.games_tree.tag_configure("favorite",  foreground=C_GOLD)
        self.games_tree.tag_configure("expansion", background="#f3e5f5")
        # Per-game actions live on the row right-click menu (no bulk toolbar).

    def _set_view(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self.settings["view_mode"] = mode
        config.save(self.settings)
        self._view_var.set("Cards" if mode == "cards" else "Table")
        if mode == "table":
            self._size_field.pack_forget()
            self._card_frame.pack_forget()
            self._table_frame.pack(fill="both", expand=True)
        else:
            self._size_field.pack(side="right", padx=(0, self.SP["md"]))
            self._table_frame.pack_forget()
            self._card_frame.pack(fill="both", expand=True)
        self.refresh_games()

    def _set_card_size(self, size: str) -> None:
        if size == self._card_size:
            return
        self._card_size = size
        self.settings["card_size"] = size
        config.save(self.settings)
        self._size_var.set({"sm": "Small", "md": "Medium", "lg": "Large"}[size])
        self.refresh_games()

    def _on_scroll(self, event: tk.Event) -> None:
        if event.widget.winfo_toplevel() is not self:
            return  # don't scroll the main window while a dialog is open
        delta = int(-event.delta / 120)
        tab = self.nb.index(self.nb.select())
        if tab == 0:
            self._dashboard_canvas.yview_scroll(delta, "units")
        elif tab == 1:
            if self._view_mode == "cards":
                self.games_canvas.yview_scroll(delta, "units")
            else:
                self.games_tree.yview_scroll(delta, "units")
        elif tab == 2:
            self.members_tree.yview_scroll(delta, "units")
        elif tab == 3:
            self.plays_tree.yview_scroll(delta, "units")
        elif tab == 4:
            if self.history_mode.get() == "plays":
                self.history_plays_tree.yview_scroll(delta, "units")
            else:
                self.history_tree.yview_scroll(delta, "units")

    def _reflow_games(self, event: tk.Event) -> None:
        self.games_canvas.itemconfigure(self.games_window_id, width=event.width)
        self._layout_cards(event.width)

    def _layout_cards(self, container_width: int) -> None:
        if not self._cards:
            return
        card_w = _CARD_SIZES[self._card_size]["card_w"]
        gap = 16
        cols = max(1, (container_width - gap) // (card_w + gap))
        rows_used = 0
        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            rows_used = max(rows_used, r + 1)
            card.grid(row=r, column=c, padx=gap // 2, pady=gap // 2, sticky="nsew")
        for c in range(cols):
            self.games_inner.grid_columnconfigure(c, weight=1)
        # weight=1 makes every row expand to the tallest card in that row,
        # so all cards share the same height and buttons line up at the bottom.
        for r in range(rows_used):
            self.games_inner.grid_rowconfigure(r, weight=1)

    # ── multi-collection: tab bar + comparison ──────────────────────────────

    _COMPARE_LABELS = [
        ("off",    "Compare: Off"),
        ("shared", "Shared by all"),
        ("only",   "Only in this one"),
        ("diff",   "In this, not in…"),
    ]

    def _collection_pass(self, bgg_id: int) -> bool:
        """Whether a game passes the active collection tab + comparison filter."""
        cols = self._collections
        if len(cols) < 2:
            return True
        member = self._gc_map.get(bgg_id, set())
        active = self._active_collection
        mode = self._compare_mode
        if mode == "shared":
            return {col["id"] for col in cols} <= member
        if mode == "only":
            return active is not None and member == {active}
        if mode == "diff":
            if active is None or self._compare_other is None:
                return True
            return active in member and self._compare_other not in member
        # mode == "off"
        if active is None:
            return True
        return active in member

    def _refresh_collection_bar(self) -> None:
        cols = self._collections
        ids = {col["id"] for col in cols}
        if self._active_collection not in ids:
            self._active_collection = None
        if self._compare_other not in ids:
            self._compare_other = None

        sig = tuple((col["id"], col["name"], col["game_count"],
                     col["owner_user_id"]) for col in cols)
        multi = len(cols) >= 2
        # Map owner id → first name for the claim indicator on each tab.
        owner_name = {}
        if any(col["owner_user_id"] for col in cols):
            with db.connect() as c:
                owner_name = {u["id"]: u["first_name"] for u in db.list_users(c)}

        if sig != self._collection_sig:
            self._collection_sig = sig
            for w in self._collection_bar.winfo_children():
                w.destroy()
            self._tab_widgets = {}
            self._other_cb = None
            if not multi:
                self._collection_bar.configure(padding=0)
                self._active_collection = None
                self._compare_mode = "off"
                self._compare_other = None
                return
            self._collection_bar.configure(
                padding=(self.SP["lg"], self.SP["sm"], self.SP["lg"], self.SP["sm"]))
            ttk.Label(self._collection_bar, text="Library:",
                      style="Filter.TLabel").pack(side="left", padx=(0, self.SP["sm"]))
            self._make_collection_tab("All", None)
            for col in cols:
                label = f"{col['name']} ({col['game_count']})"
                if col["owner_user_id"] and col["owner_user_id"] in owner_name:
                    label += f"  👤 {owner_name[col['owner_user_id']]}"
                self._make_collection_tab(label, col["id"])
            # Comparison controls (right-aligned)
            self._other_cb = ttk.Combobox(self._collection_bar, state="readonly",
                                          width=16, values=[])
            self._other_cb.bind("<<ComboboxSelected>>", self._on_other_change)
            self._compare_cb = ttk.Combobox(
                self._collection_bar, state="readonly", width=18,
                values=[lbl for _m, lbl in self._COMPARE_LABELS])
            self._compare_cb.bind("<<ComboboxSelected>>", self._on_compare_change)
            self._compare_cb.pack(side="right")
            ttk.Label(self._collection_bar, text="Compare:",
                      style="Filter.TLabel").pack(side="right", padx=(self.SP["md"], self.SP["xs"]))

        if not multi:
            return
        self._update_collection_highlight()
        self._compare_cb.set(dict(self._COMPARE_LABELS).get(self._compare_mode, "Compare: Off"))
        self._sync_other_combobox()

    def _make_collection_tab(self, text: str, col_id: Optional[int]) -> None:
        lbl = tk.Label(self._collection_bar, text=text, padx=10, pady=3,
                       cursor="hand2", font=("Segoe UI", 9, "bold"))
        lbl.pack(side="left", padx=(0, self.SP["xs"]))
        lbl.bind("<Button-1>", lambda *_e, cid=col_id: self._on_select_collection(cid))
        if col_id is not None:
            lbl.bind("<Button-3>", lambda e, cid=col_id: self._collection_menu(e, cid))
        self._tab_widgets[col_id] = lbl

    def _update_collection_highlight(self) -> None:
        for cid, lbl in getattr(self, "_tab_widgets", {}).items():
            if cid == self._active_collection:
                lbl.configure(bg=C_BLUE_600, fg=C_SURFACE)
            else:
                lbl.configure(bg=C_LINE_100, fg=C_INK_900)

    def _on_select_collection(self, col_id: Optional[int]) -> None:
        self._active_collection = col_id
        if col_id is None and self._compare_mode in ("only", "diff"):
            self._compare_mode = "off"   # those modes need a specific library
        self.refresh_games()

    def _on_compare_change(self, *_e) -> None:
        lbl = self._compare_cb.get()
        self._compare_mode = next((m for m, l in self._COMPARE_LABELS if l == lbl), "off")
        if self._compare_mode in ("only", "diff") and self._active_collection is None:
            if self._collections:
                self._active_collection = self._collections[0]["id"]
        self.refresh_games()

    def _on_other_change(self, *_e) -> None:
        name = self._other_cb.get()
        self._compare_other = next(
            (col["id"] for col in self._collections if col["name"] == name), None)
        self.refresh_games()

    def _sync_other_combobox(self) -> None:
        if not self._other_cb:
            return
        if self._compare_mode == "diff":
            others = [col for col in self._collections if col["id"] != self._active_collection]
            self._other_cb.configure(values=[col["name"] for col in others])
            cur = next((col["name"] for col in others if col["id"] == self._compare_other), "")
            if not cur and others:
                self._compare_other = others[0]["id"]
                cur = others[0]["name"]
            self._other_cb.set(cur)
            self._other_cb.pack(side="right", padx=(0, self.SP["sm"]))
        else:
            self._other_cb.pack_forget()

    def _collection_menu(self, event, col_id: int) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename…", command=lambda: self._rename_collection(col_id))
        owner = next((col["owner_user_id"] for col in self._collections
                      if col["id"] == col_id), None)
        menu.add_command(label="Claim for member…",
                         command=lambda: self._claim_collection(col_id))
        if owner:
            menu.add_command(label="Release claim",
                             command=lambda: self._claim_collection(col_id, clear=True))
        menu.add_separator()
        menu.add_command(label="Remove collection", command=lambda: self._delete_collection(col_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _claim_collection(self, col_id: int, clear: bool = False) -> None:
        if clear:
            with db.connect() as c:
                db.claim_collection(c, col_id, None)
            self._collection_sig = None
            self.refresh_games()
            self.status("Collection claim released.")
            return
        with db.connect() as c:
            users = db.list_users(c)
        if not users:
            messagebox.showinfo(
                "No members",
                "Add a member on the Members tab first, then claim the collection.")
            return
        win = tk.Toplevel(self)
        win.title("Claim Collection")
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=C_BG)
        name = next((col["name"] for col in self._collections if col["id"] == col_id), "")
        ttk.Label(win, text=f"Who owns “{name}”?", padding=(16, 14, 16, 6)).pack(anchor="w")
        ttk.Label(win, text="They'll be able to check out only games from this collection.",
                  foreground=C_INK_600, font=("Segoe UI", 8),
                  padding=(16, 0, 16, 8)).pack(anchor="w")
        member_names = [f"{u['first_name']} {u['last_name']}" for u in users]
        var = tk.StringVar(value=member_names[0])
        ttk.Combobox(win, textvariable=var, values=member_names, state="readonly",
                     width=30).pack(padx=16, pady=(0, 10))

        def do_claim() -> None:
            uid = users[member_names.index(var.get())]["id"]
            with db.connect() as c:
                db.claim_collection(c, col_id, uid)
            win.destroy()
            self._collection_sig = None
            self.refresh_games()
            self.status(f"“{name}” claimed by {var.get()}.")

        row = ttk.Frame(win)
        row.pack(anchor="e", padx=16, pady=(0, 14))
        ttk.Button(row, text="Cancel", style="Ghost.TButton",
                   command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Claim", command=do_claim).pack(side="left")
        win.grab_set()

    def _rename_collection(self, col_id: int) -> None:
        cur = next((col["name"] for col in self._collections if col["id"] == col_id), "")
        new = simpledialog.askstring("Rename collection", "Collection name:",
                                     initialvalue=cur, parent=self)
        if new and new.strip():
            with db.connect() as c:
                db.rename_collection(c, col_id, new.strip())
            self._collection_sig = None
            self.refresh_games()

    def _delete_collection(self, col_id: int) -> None:
        name = next((col["name"] for col in self._collections if col["id"] == col_id), "")
        if not messagebox.askyesno(
            "Remove collection",
            f"Remove the collection “{name}”?\n\n"
            "The games themselves stay in your library; only this collection grouping "
            "is removed."):
            return
        with db.connect() as c:
            db.delete_collection(c, col_id)
        if self._active_collection == col_id:
            self._active_collection = None
        self._collection_sig = None
        self.refresh_games()

    def _reset_filters(self) -> None:
        self.players_var.set("Any")
        self.exact_players_var.set(False)
        self.best_at_var.set("Any")
        self.time_var.set("Any")
        self.weight_var.set("Any")
        self.status_filter_var.set("Any")
        self.tag_filter_var.set("Any")
        self._active_collection = None
        self._compare_mode = "off"
        self._compare_other = None
        self.search_var.set("")

    def _apply_filters(self, games: list, open_loans: dict) -> list:
        players_val = self.players_var.get()
        time_val = self.time_var.get()
        weight_val = self.weight_var.get()
        status_val = self.status_filter_var.get()

        best_at_val = self.best_at_var.get()
        exact_only = self.exact_players_var.get()

        out = []
        for g in games:
            # --- players filter ---
            if players_val != "Any":
                mn = g["min_players"]
                mx = g["max_players"]
                if exact_only:
                    # Only games where min == max == N (strictly N-player games)
                    if players_val == "8+":
                        if not (mn and mx and mn >= 8 and mn == mx):
                            continue
                    else:
                        n = int(players_val)
                        if not (mn == n and mx == n):
                            continue
                else:
                    # Games that support N players (min <= N <= max)
                    if players_val == "8+":
                        if not mx or mx < 8:
                            continue
                    else:
                        n = int(players_val)
                        lo = mn if mn else 1
                        hi = mx if mx else mn
                        if not hi or not (lo <= n <= hi):
                            continue

            # --- best-at filter ---
            if best_at_val != "Any":
                bp = g["best_players"] or ""
                if not bp:
                    continue   # no data — exclude when filtering
                # Match if any token in best_players covers the target count.
                target = best_at_val   # e.g. "3" or "8+"
                matched = False
                for token in re.split(r"[,\s]+", bp):
                    token = token.strip()
                    if not token:
                        continue
                    if "-" in token:
                        # range like "3-4"
                        parts = token.split("-", 1)
                        try:
                            lo, hi = int(parts[0]), int(parts[1])
                            if target == "8+":
                                if hi >= 8:
                                    matched = True
                            else:
                                if lo <= int(target) <= hi:
                                    matched = True
                        except ValueError:
                            pass
                    else:
                        try:
                            v = int(token)
                            if target == "8+":
                                if v >= 8:
                                    matched = True
                            elif int(target) == v:
                                matched = True
                        except ValueError:
                            pass
                if not matched:
                    continue

            # --- play time filter (use playing_time, fall back to max_playtime) ---
            if time_val != "Any":
                pt = g["playing_time"] or g["max_playtime"] or g["min_playtime"]
                if pt is None:
                    continue  # unknown time — exclude when filtering
                if time_val == "≤ 30 min" and pt > 30:
                    continue
                elif time_val == "31–60 min" and not (31 <= pt <= 60):
                    continue
                elif time_val == "61–90 min" and not (61 <= pt <= 90):
                    continue
                elif time_val == "91–120 min" and not (91 <= pt <= 120):
                    continue
                elif time_val == "121+ min" and pt < 121:
                    continue

            # --- complexity (weight) filter ---
            if weight_val != "Any":
                w = g["weight"]
                if w is None:
                    continue  # unknown weight — exclude when filtering
                if weight_val == "Light (1–2)" and not (1.0 <= w <= 2.0):
                    continue
                elif weight_val == "Medium (2–3)" and not (2.0 < w <= 3.0):
                    continue
                elif weight_val == "Heavy (3–5)" and not (w > 3.0):
                    continue

            # --- availability / favorites filter ---
            if status_val == "Available" and g["bgg_id"] in open_loans:
                continue
            if status_val == "Checked out" and g["bgg_id"] not in open_loans:
                continue
            if status_val == "Favorites" and not g["is_favorite"]:
                continue

            # --- tag filter ---
            tag_val = self.tag_filter_var.get()
            if tag_val != "Any":
                game_tags = [t.strip() for t in (g["tags"] or "").split(",") if t.strip()]
                if tag_val not in game_tags:
                    continue

            # --- collection tab / comparison filter ---
            if not self._collection_pass(g["bgg_id"]):
                continue

            out.append(g)
        return out

    def refresh_games(self) -> None:
        with db.connect() as c:
            games = db.list_games(c, self.search_var.get().strip())
            total_count = c.execute("SELECT COUNT(*) FROM games WHERE own = 1").fetchone()[0]
            open_loans = {
                row["game_id"]: row
                for row in c.execute(
                    """
                    SELECT loans.*, users.first_name, users.last_name
                    FROM loans JOIN users ON users.id = loans.user_id
                    WHERE loans.returned_at IS NULL
                    """
                )
            }
            play_counts = db.play_counts(c)
            all_tags = ["Any"] + db.all_tags(c)
            # Only show collections that still have games — an emptied collection
            # drops its tab automatically.
            self._collections = [r for r in db.list_collections(c) if r["game_count"] > 0]
            self._gc_map = db.game_collection_map(c)
            # Collections owned by "me" (the device owner who claimed during
            # import). None → no claim, so check-out is offered for every game.
            _mine = self.settings.get("claimed_member_id")
            self._my_collection_ids = (
                db.owned_collection_ids(c, _mine) if _mine else None)

        # Refresh tag dropdown (preserve selection if tag still exists)
        cur_tag = self.tag_filter_var.get()
        self.tag_filter_cb["values"] = all_tags
        if cur_tag not in all_tags:
            self.tag_filter_var.set("Any")

        self._refresh_collection_bar()
        games = self._apply_filters(list(games), open_loans)
        self._refresh_chips()

        # Apply sort (card view and table view both respect this)
        sort_key = getattr(self, '_sort_var', None)
        sort_val  = sort_key.get() if sort_key else "Title (A–Z)"
        if sort_val == "Year (newest)":
            games = sorted(games, key=lambda g: g["year"] or 0, reverse=True)
        elif sort_val == "Most played":
            games = sorted(games, key=lambda g: play_counts.get(g["bgg_id"], 0), reverse=True)
        elif sort_val == "Complexity ↑":
            games = sorted(games, key=lambda g: g["weight"] or 0)
        elif sort_val == "Complexity ↓":
            games = sorted(games, key=lambda g: g["weight"] or 0, reverse=True)
        # Default "Title (A–Z)" is already the DB order

        # Update count label — "266 games" or "8 of 266 games" when filtered
        shown = len(games)
        if self._filters_active():
            self._count_label.configure(text=f"{shown} of {total_count} games")
        else:
            self._count_label.configure(text=f"{total_count} game{'s' if total_count != 1 else ''}")

        if self._view_mode == "table":
            self._refresh_table_view(games, open_loans, play_counts)
            self.games_tree.yview_moveto(0)
        else:
            self._refresh_card_view(games, open_loans, play_counts)
            self.games_canvas.yview_moveto(0)

    def _filters_active(self) -> bool:
        return (
            any(v != "Any" for v in [self.players_var.get(), self.best_at_var.get(),
                                      self.time_var.get(), self.weight_var.get(),
                                      self.status_filter_var.get(),
                                      self.tag_filter_var.get()])
            or self.exact_players_var.get()
            or bool(self.search_var.get())
            or (len(self._collections) >= 2
                and (self._active_collection is not None or self._compare_mode != "off"))
        )

    # Cards are rendered in batches as the user scrolls, so a large library
    # opens fast instead of building every card widget up front.
    _CARD_BATCH = 60

    def _refresh_card_view(self, games, open_loans, play_counts) -> None:
        for card in self._cards:
            card.destroy()
        self._cards.clear()

        # Store the full set; _render_more_cards() builds it batch by batch.
        self._card_games = games
        self._card_open_loans = open_loans
        self._card_play_counts = play_counts
        self._cards_rendered = 0
        self._lazy_generation += 1   # cancel any in-flight loaders from a prior view

        if not games:
            msg = (
                "No games match your filters."
                if self._filters_active()
                else 'No games yet. Use File → Import from BGG… or Import collection CSV… to get started.'
            )
            empty = ttk.Label(self.games_inner, text=msg, style="Muted.TLabel",
                              padding=self.SP["xl"])
            empty.grid(row=0, column=0)
            self._cards.append(empty)
            self.after(80, lambda: self._update_alpha_bar([]))
            return

        self._render_more_cards()
        self.after(80, lambda g=games: self._update_alpha_bar(g))

    def _render_more_cards(self) -> None:
        """Build the next batch of card widgets (called initially and on scroll)."""
        games = getattr(self, "_card_games", None)
        if not games:
            return
        start = self._cards_rendered
        if start >= len(games):
            return
        end = min(start + self._CARD_BATCH, len(games))

        self.games_canvas.itemconfigure(self.games_window_id, state="hidden")
        lazy_queue: list[tuple] = []
        for game in games[start:end]:
            card, lazy = self._build_card(
                game, self._card_open_loans.get(game["bgg_id"]), self._card_play_counts)
            self._cards.append(card)
            lazy_queue.append(lazy)
        self._cards_rendered = end

        self._layout_cards(self.games_canvas.winfo_width())
        self.games_canvas.itemconfigure(self.games_window_id, state="normal")

        threading.Thread(
            target=self._lazy_load_images,
            args=(lazy_queue, self._lazy_generation),
            daemon=True,
        ).start()

    def _flush_card_batches(self) -> None:
        """Render all remaining card batches now (used before an A–Z jump)."""
        while self._cards_rendered < len(getattr(self, "_card_games", [])):
            self._render_more_cards()

    def _card_yscroll(self, first: str, last: str) -> None:
        """Scrollbar callback: keep the bar in sync and load more cards as the
        bottom approaches."""
        self._card_scroll.set(first, last)
        try:
            if float(last) > 0.9 and self._cards_rendered < len(getattr(self, "_card_games", [])):
                self.after_idle(self._render_more_cards)
        except (ValueError, tk.TclError):
            pass

    # ---------- lazy image loading ----------

    def _lazy_load_images(self, items: list[tuple], generation: int) -> None:
        """Background thread: open PIL images and post each one back to the main thread.

        PhotoImage creation is intentionally left to the main thread so we never
        call Tkinter from a worker thread.
        """
        for canvas, img_id, game in items:
            if self._lazy_generation != generation:
                return   # a newer refresh has started — stop immediately

            path = game["image_path"]
            if not path or not Path(path).exists():
                continue  # no file on disk; placeholder is fine

            # Size the image to the actual canvas so it never overflows
            ch = getattr(canvas, "_card_height", 200)
            cw = getattr(canvas, "_card_width",  260)
            cache_key = (path, ch)

            # If already cached at this size, just reuse it
            if cache_key in self._image_cache:
                tk_img = self._image_cache[cache_key]
                self.after(0, lambda c=canvas, i=img_id, im=tk_img:
                           self._apply_lazy_image(c, i, im))
                continue

            # Disk I/O + PIL resize in the background
            try:
                pil_img = Image.open(path)
                pil_img.thumbnail((cw, ch))
            except (OSError, ValueError):
                continue

            self.after(0, lambda c=canvas, i=img_id, p=pil_img, ck=cache_key:
                       self._apply_lazy_image_from_pil(c, i, p, ck))

    def _apply_lazy_image(self, canvas: tk.Canvas, img_id: int,
                          tk_img: ImageTk.PhotoImage) -> None:
        """Main thread: update a card's canvas with an already-created PhotoImage."""
        try:
            if canvas.winfo_exists():
                canvas.itemconfigure(img_id, image=tk_img)
                canvas._card_img_ref = tk_img
                # Hide the cover-title text overlay now that a real image is showing
                tid = getattr(canvas, "_cover_title_id", None)
                if tid:
                    canvas.itemconfigure(tid, state="hidden")
        except tk.TclError:
            pass

    def _apply_lazy_image_from_pil(self, canvas: tk.Canvas, img_id: int,
                                    pil_img: "Image.Image", cache_key) -> None:
        """Main thread: convert a PIL Image → PhotoImage, cache it, show it."""
        try:
            if not canvas.winfo_exists():
                return
            tk_img = ImageTk.PhotoImage(pil_img)
            self._image_cache[cache_key] = tk_img
            canvas.itemconfigure(img_id, image=tk_img)
            canvas._card_img_ref = tk_img
            # Hide the cover-title text overlay now that a real image is showing
            tid = getattr(canvas, "_cover_title_id", None)
            if tid:
                canvas.itemconfigure(tid, state="hidden")
        except tk.TclError:
            pass

    # ---------- A–Z jump bar ----------

    def _update_alpha_bar(self, games: list) -> None:
        """Rebuild the vertical A–Z strip from the current ordered game list."""
        # Map letter → index of the first card starting with that letter
        letter_idx: dict[str, int] = {}
        for i, g in enumerate(games):
            first = (g["name"] or "#")[0].upper()
            if first.isalpha() and first not in letter_idx:
                letter_idx[first] = i

        for w in self._alpha_bar.winfo_children():
            w.destroy()

        # Top spacer so letters don't start flush with the very top edge
        tk.Frame(self._alpha_bar, bg=C_BG, height=4).pack()

        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            idx = letter_idx.get(letter)
            active = idx is not None
            lbl = tk.Label(
                self._alpha_bar,
                text=letter,
                font=("Segoe UI", 7, "bold" if active else "normal"),
                fg=C_BLUE_600 if active else C_LINE_200,
                bg=C_BG,
                cursor="hand2" if active else "",
                pady=1, padx=2,
            )
            lbl.pack(fill="x")
            if active:
                lbl.bind("<Button-1>",
                         lambda e, i=idx: self._scroll_to_card(i))
                lbl.bind("<Enter>", lambda e, lb=lbl: lb.configure(bg=C_PALE))
                lbl.bind("<Leave>", lambda e, lb=lbl: lb.configure(bg=C_BG))

    def _scroll_to_card(self, card_idx: int) -> None:
        """Scroll the card canvas so the card at card_idx is near the top."""
        # The target card may not be built yet (cards load in batches) — render
        # everything up to it first.
        if card_idx >= self._cards_rendered:
            self._flush_card_batches()
            self.update_idletasks()
        if card_idx >= len(self._cards):
            return
        card = self._cards[card_idx]
        try:
            if not card.winfo_exists():
                return
            y = card.winfo_y()
            total_h = self.games_inner.winfo_reqheight()
            canvas_h = self.games_canvas.winfo_height()
            if total_h > canvas_h:
                fraction = max(0.0, min(1.0, (y - 6) / total_h))
                self.games_canvas.yview_moveto(fraction)
        except tk.TclError:
            pass

    def _refresh_table_view(self, games, open_loans, play_counts) -> None:
        self.games_tree.delete(*self.games_tree.get_children())

        # Apply column sort
        if self._sort_col:
            def _key(g):
                c = self._sort_col
                if   c == "name":    return (g["name"] or "").lower()
                elif c == "year":    return g["year"] or 0
                elif c == "players": return g["min_players"] or 0
                elif c == "time":    return g["playing_time"] or g["max_playtime"] or g["min_playtime"] or 0
                elif c == "weight":  return g["weight"] or 0.0
                elif c == "rating":  return g["avg_rating"] or 0.0
                elif c == "best":    return g["best_players"] or ""
                elif c == "status":  return 0 if g["bgg_id"] in open_loans else 1
                elif c == "plays":   return play_counts.get(g["bgg_id"], 0)
                elif c == "fav":     return 0 if g["is_favorite"] else 1
                elif c == "insert":  return 0 if g["has_insert"] else 1
                return ""
            games = sorted(games, key=_key, reverse=self._sort_rev)

        self._table_games = list(games)

        if not games:
            # Nothing to insert — status bar already describes the state
            return

        for g in games:
            bgg_id  = g["bgg_id"]
            loan    = open_loans.get(bgg_id)
            n_plays = play_counts.get(bgg_id, 0)

            tags: list[str] = []
            if loan:
                tags.append("out")
            if g["is_favorite"]:
                tags.append("favorite")
            if g["is_expansion"]:
                tags.append("expansion")

            exp_prefix = "↳ " if g["is_expansion"] else ""
            self.games_tree.insert(
                "", "end", iid=str(bgg_id),
                tags=tags,
                values=(
                    "★" if g["is_favorite"] else "",
                    "\U0001f4e6" if g["has_insert"] else "",
                    f"{exp_prefix}{g['name']}",
                    g["year"] or "—",
                    fmt_players(g["min_players"], g["max_players"]),
                    fmt_time(g["min_playtime"], g["max_playtime"], g["playing_time"]),
                    f"{g['weight']:.1f}" if g["weight"] else "—",
                    f"{g['avg_rating']:.1f}" if g["avg_rating"] else "—",
                    g["best_players"] or "—",
                    f"Out: {loan['first_name']} {loan['last_name']}" if loan else "Available",
                    n_plays if n_plays else "—",
                ),
            )

    def _sort_table(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        _labels = {
            "fav": "★", "insert": "📦", "name": "Name", "year": "Year",
            "players": "Players", "time": "Time", "weight": "Complexity",
            "rating": "BGG ★", "best": "Best At", "status": "Status", "plays": "Plays",
        }
        for c, lbl in _labels.items():
            arrow = (" ▲" if not self._sort_rev else " ▼") if c == col else ""
            self.games_tree.heading(c, text=lbl + arrow)

        self.refresh_games()

    def _table_selected_game(self) -> Optional[dict]:
        sel = self.games_tree.selection()
        if not sel:
            return None
        bgg_id = int(sel[0])
        return next((g for g in self._table_games if g["bgg_id"] == bgg_id), None)

    def _on_table_double_click(self, event: tk.Event) -> None:
        row = self.games_tree.identify_row(event.y)
        if not row:
            return
        self.games_tree.selection_set(row)
        game = next((g for g in self._table_games if g["bgg_id"] == int(row)), None)
        if game:
            self.show_details(game)

    def _on_table_return(self, event: tk.Event) -> None:
        game = self._table_selected_game()
        if game:
            self.show_details(game)

    def _on_table_right_click(self, event: tk.Event) -> None:
        row = self.games_tree.identify_row(event.y)
        if not row:
            return
        self.games_tree.selection_set(row)
        game = next((g for g in self._table_games if g["bgg_id"] == int(row)), None)
        if not game:
            return

        with db.connect() as c:
            loan = c.execute(
                "SELECT * FROM loans WHERE game_id = ? AND returned_at IS NULL",
                (game["bgg_id"],),
            ).fetchone()

        menu = tk.Menu(self, tearoff=0)
        if loan:
            menu.add_command(label="Check In",  command=lambda: self.on_check_in(game))
        else:
            menu.add_command(label="Check Out", command=lambda: self.on_check_out(game))
        menu.add_command(label="Log Play…",    command=lambda: self.on_log_play(game))
        menu.add_separator()
        menu.add_command(label="Details…",     command=lambda: self.show_details(game))
        menu.add_command(label="Edit Game…",   command=lambda: self.on_edit_game(game))
        menu.add_command(label="Set Image…",   command=lambda: self.on_set_image(game))

        fav_lbl = "Remove from Favorites" if game["is_favorite"] else "Add to Favorites"
        menu.add_command(label=fav_lbl,        command=lambda: self.on_toggle_favorite(game))
        self._add_collection_remove_item(menu, game)
        menu.add_separator()
        menu.add_command(label="Delete Game…", command=lambda: self.on_delete_game(game))
        menu.tk_popup(event.x_root, event.y_root)

    def _build_card(self, game, loan, play_counts: dict) -> tuple:
        """Build one game card per the design-system .card spec.

        Layout, top → bottom:
          • full-width cover image (200px) with the favourite ★ overlaid on the
            cover's top-right corner, and an Expansion ribbon on the bottom-left
          • status badge  (● + word + colour — never colour alone)
          • optional loaned-to line
          • card title (13 bold) + year (11, ink-600)
          • specs row (players · time) and best-at (star colour)
          • insert / plays meta badges
          • ONE filled primary action, then a 2-col Ghost action grid
        """
        SP = self.SP
        out_to = None
        if loan is not None:
            out_to = f"{loan['first_name']} {loan['last_name']}".strip()

        bgg_id    = game["bgg_id"]
        is_fav    = bool(game["is_favorite"])
        has_insert = bool(game["has_insert"])
        n_plays   = play_counts.get(bgg_id, 0)
        due       = loan["due_date"] if loan else None

        # ── status badge (text + dot + colour) ─────────────────────────────────
        if out_to:
            overdue = bool(due and due < datetime.now().strftime("%Y-%m-%d"))
            if overdue:
                badge_txt, badge_bg, badge_fg = "● Overdue", C_DR_BG, C_DR_TEXT
            else:
                badge_txt, badge_bg, badge_fg = "● Checked out", C_WN_BG, C_WN_TEXT
        else:
            badge_txt, badge_bg, badge_fg = "● Available", C_OK_BG, C_OK_TEXT

        overdue = bool(out_to and due and due < datetime.now().strftime("%Y-%m-%d"))

        # ── size config ───────────────────────────────────────────────────────
        _sz   = _CARD_SIZES[self._card_size]
        _IH   = _sz["cover_h"]
        _ts   = _sz["title"]                           # title font pt
        _ss   = _sz["sub"]                             # sub-text font pt
        _wrap = _sz["wrap"]
        _cf   = ("Segoe UI", max(11, _ts - 4), "bold") # cover name overlay font

        # ── card shell ────────────────────────────────────────────────────────
        card = tk.Frame(self.games_inner, bg=C_SURFACE,
                        highlightbackground=C_LINE_200, highlightthickness=1, bd=0)

        # ── cover: gradient placeholder + game-name overlay + star chip ───────
        # Store cover dimensions so the lazy loader can resize to fit exactly.
        img_canvas = tk.Canvas(card, height=_IH, highlightthickness=0, bd=0)
        img_canvas._card_height = _IH
        img_canvas._card_width  = _sz["card_w"]
        img_canvas.pack(fill="x")

        # Gradient placeholder image (replaced when real photo loads)
        ph = self._get_gradient_placeholder(bgg_id)
        _img_id = img_canvas.create_image(130, _IH // 2, anchor="center")
        img_canvas.itemconfigure(_img_id, image=ph)
        img_canvas._card_img_ref = ph

        # Game-name text overlay (uppercase, white, centered on cover)
        # Hidden once a real cover image is loaded
        cover_lines = self._cover_title_lines(game["name"])
        _title_id = img_canvas.create_text(
            130, _IH // 2,
            text="\n".join(cover_lines),
            fill="white", font=_cf,
            anchor="center", justify="center",
        )
        img_canvas._cover_title_id = _title_id  # lazy-loader hides this

        # Keep the cover image + title overlay centred on resize. (The favourite
        # star now lives in the card body, next to the status badge.)
        def _place_overlays(e=None, iid=_img_id, h=_IH):
            w = img_canvas.winfo_width()
            img_canvas.coords(iid, w // 2, h // 2)
            img_canvas.coords(_title_id, w // 2, h // 2)
        img_canvas.bind("<Configure>", _place_overlays)

        # Expansion ribbon — bottom-left of cover, sized to fit the label so it
        # never clips (the text width grows with DPI / card size).
        if game["is_expansion"]:
            _exp_id = img_canvas.create_text(
                SP["sm"], _IH - 12, anchor="w", text="Expansion",
                fill=C_BLUE_800, font=self.FONTS["label"])
            bb = img_canvas.bbox(_exp_id)
            x2 = (bb[2] + SP["sm"]) if bb else 90
            y1 = (bb[1] - 3) if bb else (_IH - 22)
            _exp_bg = img_canvas.create_rectangle(0, y1, x2, _IH,
                                                  fill=C_BLUE_050, outline="")
            img_canvas.tag_lower(_exp_bg, _exp_id)   # behind the text, above the image

        # ── card body ──────────────────────────────────────────────────────────
        _is_sm = self._card_size == "sm"
        body = tk.Frame(card, bg=C_SURFACE,
                        padx=SP["sm"] if _is_sm else SP["lg"], pady=SP["sm"])
        body.pack(fill="both", expand=True)

        # Status badge (left) + favourite star (right) on one row.
        status_row = tk.Frame(body, bg=C_SURFACE)
        status_row.pack(fill="x", pady=(0, SP["xs"]))
        tk.Label(status_row, text=badge_txt, bg=badge_bg, fg=badge_fg,
                 font=("Segoe UI", 12, "bold"), padx=10, pady=4).pack(side="left")
        _star_lbl = tk.Label(
            status_row, text="★" if is_fav else "☆",
            bg=C_SURFACE, fg=C_STAR_FILL if is_fav else C_INK_500,
            font=("Segoe UI", 17, "bold"), cursor="hand2", padx=SP["sm"])
        _star_lbl.pack(side="right")
        _star_lbl.bind("<Button-1>", lambda e, g=game: self.on_toggle_favorite(g))

        # Loaned-to line: "To Name · due Date" (prototype: 13px ink-600)
        if out_to:
            due_txt = f" · due {due}" if due else ""
            tk.Label(body, text=f"To {out_to}{due_txt}",
                     bg=C_SURFACE, fg=C_INK_600,
                     font=self.FONTS["loaned_to"],
                     anchor="w", justify="left").pack(anchor="w", pady=(0, SP["xs"]))

        # Title (prototype: 16px bold) + year (prototype: 13px ink-600)
        tk.Label(body, text=_shorten(game["name"]),
                 bg=C_SURFACE, fg=C_INK_900, font=("Segoe UI", _ts, "bold"),
                 wraplength=_wrap, justify="left", anchor="w").pack(anchor="w")
        if game["year"]:
            tk.Label(body, text=str(game["year"]), bg=C_SURFACE, fg=C_INK_600,
                     font=("Segoe UI", _ss)).pack(anchor="w")

        # Specs row (prototype: 13.5px ink-600)
        info = (
            f"\U0001f465 {fmt_players(game['min_players'], game['max_players'])}  "
            f"⏱ {fmt_time(game['min_playtime'], game['max_playtime'], game['playing_time'])}"
        )
        tk.Label(body, text=info, bg=C_SURFACE, fg=C_INK_600,
                 font=("Segoe UI", _ss)).pack(anchor="w", pady=(SP["xs"], 0))

        # Best-at (prototype: 13px bold, star colour)
        if game["best_players"]:
            tk.Label(body, text=f"★ Best at {game['best_players']}",
                     bg=C_SURFACE, fg=C_STAR_TEXT,
                     font=("Segoe UI", _ss, "bold")).pack(anchor="w")

        # Meta badges: insert / plays
        if has_insert or n_plays:
            badge_row = tk.Frame(body, bg=C_SURFACE)
            badge_row.pack(anchor="w", pady=(SP["xs"], 0))
            if has_insert:
                tk.Label(badge_row, text="📦 Insert", bg=C_BLUE_050, fg=C_BLUE_700,
                         font=("Segoe UI", 9, "bold"), padx=SP["sm"] - 2, pady=1
                         ).pack(side="left", padx=(0, SP["xs"]))
            if n_plays:
                tk.Label(badge_row,
                         text=f"🎮 {n_plays} play{'s' if n_plays != 1 else ''}",
                         bg=C_OK_BG, fg=C_OK_TEXT,
                         font=("Segoe UI", 9, "bold"), padx=SP["sm"] - 2, pady=1
                         ).pack(side="left")

        # ── actions ────────────────────────────────────────────────────────────
        # Expanding spacer pushes buttons to the row's baseline
        tk.Frame(body, bg=C_SURFACE).pack(fill="both", expand=True)

        # Primary button — full width. When a collection has been claimed as
        # "mine", only games from my collection can be checked out, so the
        # Check Out button is hidden for games in other collections.
        my_ids = getattr(self, "_my_collection_ids", None)
        can_checkout = (my_ids is None) or bool(
            self._gc_map.get(bgg_id, set()) & my_ids)
        if out_to:
            ttk.Button(body, text="Check In",
                       command=lambda g=game: self.on_check_in(g)
                       ).pack(fill="x", pady=(0, SP["xs"]))
        elif can_checkout:
            ttk.Button(body, text="Check Out",
                       command=lambda g=game: self.on_check_out(g)
                       ).pack(fill="x", pady=(0, SP["xs"]))
        else:
            tk.Label(body, text="Not in your collection",
                     bg=C_SURFACE, fg=C_INK_500, font=("Segoe UI", 9),
                     pady=4).pack(fill="x", pady=(0, SP["xs"]))

        if not _is_sm:
            sec = tk.Frame(body, bg=C_SURFACE)
            sec.pack(fill="x")
            sec.columnconfigure(0, weight=1)
            sec.columnconfigure(1, weight=1)
            ttk.Button(sec, text="Details", style="Ghost.TButton",
                       command=lambda g=game: self.show_details(g)
                       ).grid(row=0, column=0, sticky="ew", padx=(0, 2))
            if overdue:
                ttk.Button(sec, text="Remind", style="Ghost.TButton",
                           command=lambda g=game: self._remind_borrower(g)
                           ).grid(row=0, column=1, sticky="ew", padx=(2, 0))
            else:
                ttk.Button(sec, text="Log Play", style="Ghost.TButton",
                           command=lambda g=game: self.on_log_play(g)
                           ).grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # Hover: lift card border
        card.bind("<Enter>", lambda e: card.configure(highlightbackground=C_INK_500))
        card.bind("<Leave>", lambda e: card.configure(highlightbackground=C_LINE_200))

        # Right-click context menu
        def _card_right_click(event, g=game):
            self._show_card_context_menu(event, g)
        _rc_targets = [card, img_canvas, body]
        if not _is_sm:
            _rc_targets.append(sec)
        for w in _rc_targets:
            w.bind("<Button-3>", _card_right_click)

        return card, (img_canvas, _img_id, game)

    # ---------- card cover helpers ----------

    def _get_gradient_placeholder(self, bgg_id: int) -> ImageTk.PhotoImage:
        """Return a cached PIL gradient image for this game's palette slot."""
        palette_idx = bgg_id % len(self._COVER_PALETTES)
        if palette_idx not in self._gradient_cache:
            c1, c2 = self._COVER_PALETTES[palette_idx]
            def _parse(h): return (int(h[1:3],16), int(h[3:5],16), int(h[5:7],16))
            r1,g1,b1 = _parse(c1);  r2,g2,b2 = _parse(c2)
            W, H = 300, 200
            # Build a 1-px-wide vertical gradient strip, then resize to full size
            strip = Image.new("RGB", (1, H))
            for y in range(H):
                t = y / (H - 1)
                strip.putpixel((0, y), (
                    int(r1 + (r2-r1)*t),
                    int(g1 + (g2-g1)*t),
                    int(b1 + (b2-b1)*t),
                ))
            img = strip.resize((W, H), Image.NEAREST)
            self._gradient_cache[palette_idx] = ImageTk.PhotoImage(img)
        return self._gradient_cache[palette_idx]

    def _cover_title_lines(self, name: str, max_chars: int = 14) -> list[str]:
        """Split a game name into short uppercase lines for the cover overlay."""
        words = name.upper().split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:4]   # cap at 4 lines so text stays readable

    def _remind_borrower(self, game) -> None:
        """Show a reminder dialog for an overdue game."""
        with db.connect() as c:
            loan = c.execute(
                """SELECT loans.*, users.first_name, users.last_name
                   FROM loans JOIN users ON users.id = loans.user_id
                   WHERE loans.game_id = ? AND loans.returned_at IS NULL""",
                (game["bgg_id"],),
            ).fetchone()
        if not loan:
            return
        name = f"{loan['first_name']} {loan['last_name']}"
        due  = loan["due_date"] or "no due date set"
        messagebox.showinfo(
            "Remind borrower",
            f"\"{game['name']}\" is overdue.\n\n"
            f"Borrower:  {name}\n"
            f"Due date:  {due}\n\n"
            "Contact them to arrange a return.",
        )

    def _show_card_context_menu(self, event: tk.Event, game) -> None:
        """Right-click context menu for a game card — mirrors the table-view menu."""
        with db.connect() as c:
            loan = c.execute(
                "SELECT * FROM loans WHERE game_id = ? AND returned_at IS NULL",
                (game["bgg_id"],),
            ).fetchone()

        menu = tk.Menu(self, tearoff=0)
        if loan:
            menu.add_command(label="Check In",  command=lambda: self.on_check_in(game))
        else:
            menu.add_command(label="Check Out", command=lambda: self.on_check_out(game))
        menu.add_command(label="Log Play…",     command=lambda: self.on_log_play(game))
        menu.add_separator()
        menu.add_command(label="Details…",      command=lambda: self.show_details(game))
        menu.add_command(label="Edit Game…",    command=lambda: self.on_edit_game(game))
        menu.add_command(label="Set Image…",    command=lambda: self.on_set_image(game))
        fav_lbl = "Remove from Favorites" if game["is_favorite"] else "Add to Favorites"
        menu.add_command(label=fav_lbl,         command=lambda: self.on_toggle_favorite(game))
        self._add_collection_remove_item(menu, game)
        menu.add_separator()
        menu.add_command(label="Delete Game…",  command=lambda: self.on_delete_game(game))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_card_image(self, canvas: tk.Canvas, img_id: int, game) -> None:
        path = game["image_path"]
        img = None
        if path and Path(path).exists():
            img = self._load_thumb(path)
        if img is None:
            img = self._get_placeholder()
        canvas.itemconfigure(img_id, image=img)
        canvas._card_img_ref = img  # keep reference so Tkinter doesn't GC it

    def _load_thumb(self, path: str) -> Optional[ImageTk.PhotoImage]:
        if path in self._image_cache:
            return self._image_cache[path]
        try:
            img = Image.open(path)
            img.thumbnail(THUMB_SIZE)
            tk_img = ImageTk.PhotoImage(img)
        except (OSError, ValueError):
            return None
        self._image_cache[path] = tk_img
        return tk_img

    def _get_placeholder(self) -> ImageTk.PhotoImage:
        if self._placeholder_img is None:
            img = Image.new("RGB", THUMB_SIZE, PLACEHOLDER_BG)
            self._placeholder_img = ImageTk.PhotoImage(img)
        return self._placeholder_img

    # ---------- members tab ----------

    def _build_members_tab(self) -> None:
        SP = self.SP
        frame = ttk.Frame(self.members_tab, padding=SP["lg"])
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Members", style="Section.TLabel").pack(anchor="w")
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(SP["xs"], SP["md"]))

        # Add-member form: labelled inputs, one primary + one ghost action
        form = ttk.Frame(frame)
        form.pack(fill="x")
        ttk.Label(form, text="First name", style="Filter.TLabel").pack(side="left", padx=(0, SP["xs"]))
        self.first_name_var = tk.StringVar()
        first_entry = ttk.Entry(form, textvariable=self.first_name_var, width=18)
        first_entry.pack(side="left", padx=(0, SP["md"]))
        first_entry.bind("<Return>", lambda *_: self.on_add_member())
        ttk.Label(form, text="Last name", style="Filter.TLabel").pack(side="left", padx=(0, SP["xs"]))
        self.last_name_var = tk.StringVar()
        last_entry = ttk.Entry(form, textvariable=self.last_name_var, width=18)
        last_entry.pack(side="left", padx=(0, SP["md"]))
        last_entry.bind("<Return>", lambda *_: self.on_add_member())
        ttk.Button(form, text="Add member", command=self.on_add_member).pack(side="left")
        ttk.Button(form, text="Remove selected", style="Ghost.TButton",
                   command=self.on_delete_member).pack(side="left", padx=(SP["sm"], 0))

        cols = ("name", "out", "since")
        self.members_tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.members_tree.heading("name", text="Name")
        self.members_tree.heading("out", text="Currently out")
        self.members_tree.heading("since", text="Member since")
        self.members_tree.column("name", width=240)
        self.members_tree.column("out", width=120, anchor="center")
        self.members_tree.column("since", width=160, anchor="center")
        self.members_tree.pack(fill="both", expand=True, pady=(SP["md"], 0))
        self.members_tree.bind("<Double-1>", self._on_member_double_click)

        ttk.Label(frame, text="Double-click a member to see their checkout history.",
                  style="Muted.TLabel").pack(anchor="w", pady=(SP["xs"], 0))

    def refresh_members(self) -> None:
        self.members_tree.delete(*self.members_tree.get_children())
        with db.connect() as c:
            users = db.list_users(c)
            counts = {
                row["user_id"]: row["n"]
                for row in c.execute(
                    "SELECT user_id, COUNT(*) AS n FROM loans WHERE returned_at IS NULL GROUP BY user_id"
                )
            }
        for u in users:
            self.members_tree.insert(
                "",
                "end",
                iid=str(u["id"]),
                values=(f"{u['first_name']} {u['last_name']}", counts.get(u["id"], 0), fmt_date(u["created_at"])),
            )

    def on_add_member(self) -> None:
        first = self.first_name_var.get().strip()
        last = self.last_name_var.get().strip()
        if not first or not last:
            messagebox.showerror("Missing info", "Both first and last name are required.")
            return
        with db.connect() as c:
            db.add_user(c, first, last)
        self.first_name_var.set("")
        self.last_name_var.set("")
        self.refresh_members()
        self.status(f"Added {first} {last}.")

    def on_delete_member(self) -> None:
        sel = self.members_tree.selection()
        if not sel:
            return
        user_id = int(sel[0])
        name = self.members_tree.item(sel[0], "values")[0]
        with db.connect() as c:
            open_count = c.execute(
                "SELECT COUNT(*) FROM loans WHERE user_id = ? AND returned_at IS NULL",
                (user_id,),
            ).fetchone()[0]
        if open_count:
            messagebox.showerror(
                "Has games out",
                f"{name} still has {open_count} game(s) checked out. Check them in first.",
            )
            return
        if not messagebox.askyesno("Remove member", f"Remove {name} and their loan history?"):
            return
        with db.connect() as c:
            db.delete_user(c, user_id)
        self.refresh_members()
        self.refresh_history()
        self.status(f"Removed {name}.")

    def _on_member_double_click(self, event: tk.Event) -> None:
        row = self.members_tree.identify_row(event.y)
        if not row:
            return
        self.members_tree.selection_set(row)
        self._show_member_checkouts(int(row))

    def _show_member_checkouts(self, user_id: int) -> None:
        """Open a popup showing all loan history for the given member."""
        with db.connect() as c:
            user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            loans = db.loan_history(c, user_id=user_id)
        if not user:
            return

        name = f"{user['first_name']} {user['last_name']}"
        win = tk.Toplevel(self)
        win.title(f"Checkout History — {name}")
        win.geometry("760x440")
        win.minsize(680, 320)
        win.transient(self)
        win.configure(bg=C_BG)

        # ── header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=C_NAVY, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=name, bg=C_NAVY, fg=C_WHITE,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12)
        tk.Label(hdr, text=f"Member since {fmt_date(user['created_at'])}",
                 bg=C_NAVY, fg=C_SKY,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # ── loan table ────────────────────────────────────────────────────────
        frame = ttk.Frame(win, padding=(8, 8, 8, 4))
        frame.pack(fill="both", expand=True)

        cols = ("game", "out", "returned", "notes")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("game",     text="Game")
        tree.heading("out",      text="Checked out")
        tree.heading("returned", text="Returned")
        tree.heading("notes",    text="Notes")
        # Game stretches to fill; the rest are fixed-width to fit their content.
        tree.column("game",     width=220, minwidth=140, anchor="w",      stretch=True)
        tree.column("out",      width=150, minwidth=150, anchor="center", stretch=False)
        tree.column("returned", width=150, minwidth=150, anchor="center", stretch=False)
        tree.column("notes",    width=170, minwidth=120, anchor="w",      stretch=False)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Colour open loans amber
        tree.tag_configure("open", background=C_WN_BG)

        still_out = 0
        for loan in loans:
            is_open = loan["returned_at"] is None
            if is_open:
                still_out += 1
            tree.insert("", "end",
                        tags=("open",) if is_open else (),
                        values=(
                            loan["game_name"],
                            fmt_date(loan["checked_out_at"]),
                            fmt_date(loan["returned_at"]) or "⬤ still out",
                            loan["notes"] or "",
                        ))

        summary = ttk.Label(
            win,
            text=f"{len(loans)} checkout{'s' if len(loans) != 1 else ''} total"
                 + (f"  •  {still_out} currently out" if still_out else ""),
            foreground=C_INK_600,
            font=("Segoe UI", 8),
        )
        summary.pack(anchor="w", padx=10)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(4, 10))
        win.grab_set()

    # ---------- history tab ----------

    def _build_history_tab(self) -> None:
        SP = self.SP
        frame = ttk.Frame(self.history_tab, padding=SP["lg"])
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="History", style="Section.TLabel").pack(anchor="w")
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(SP["xs"], SP["md"]))

        # ── Mode toggle ──────────────────────────────────────────────────────
        top_bar = ttk.Frame(frame)
        top_bar.pack(fill="x", pady=(0, SP["sm"]))
        self.history_mode = tk.StringVar(value="checkouts")
        seg = tk.Frame(top_bar, bg=C_SURFACE,
                       highlightbackground=C_LINE_200, highlightthickness=1, bd=0)
        seg.pack(side="left")

        def _hbtn(text, mode):
            active = self.history_mode.get() == mode
            btn = tk.Button(
                seg, text=text,
                bg=C_BLUE_050 if active else C_SURFACE,
                fg=C_BLUE_800 if active else C_INK_600,
                activebackground=C_BLUE_050, activeforeground=C_BLUE_800,
                relief="flat", bd=0, font=self.FONTS["control"],
                padx=SP["md"], pady=SP["xs"] + 1, cursor="hand2",
                command=lambda m=mode: self._set_history_mode(m),
            )
            btn.pack(side="left")
            return btn

        self._hist_btn_checkouts = _hbtn("Checkouts", "checkouts")
        tk.Frame(seg, bg=C_LINE_200, width=1).pack(side="left", fill="y")
        self._hist_btn_plays = _hbtn("Plays", "plays")

        # ── Checkouts pane ───────────────────────────────────────────────────
        self._hist_checkouts_pane = ttk.Frame(frame)

        controls = ttk.Frame(self._hist_checkouts_pane)
        controls.pack(fill="x")
        ttk.Label(controls, text="Filter", style="Filter.TLabel").pack(side="left", padx=(0, SP["sm"]))
        self.history_filter = tk.StringVar(value="all")
        ttk.Radiobutton(controls, text="All", variable=self.history_filter, value="all",
                        command=self.refresh_history).pack(side="left", padx=SP["xs"])
        ttk.Radiobutton(controls, text="Currently out", variable=self.history_filter, value="open",
                        command=self.refresh_history).pack(side="left", padx=SP["xs"])
        ttk.Radiobutton(controls, text="Returned", variable=self.history_filter, value="closed",
                        command=self.refresh_history).pack(side="left", padx=SP["xs"])

        cols = ("game", "member", "out", "due", "returned", "notes")
        self.history_tree = ttk.Treeview(self._hist_checkouts_pane, columns=cols, show="headings")
        self.history_tree.heading("game",     text="Game")
        self.history_tree.heading("member",   text="Member")
        self.history_tree.heading("out",      text="Checked Out")
        self.history_tree.heading("due",      text="Due")
        self.history_tree.heading("returned", text="Returned")
        self.history_tree.heading("notes",    text="Notes")
        self.history_tree.column("game",     width=220)
        self.history_tree.column("member",   width=150)
        self.history_tree.column("out",      width=110, anchor="center")
        self.history_tree.column("due",      width=90,  anchor="center")
        self.history_tree.column("returned", width=110, anchor="center")
        self.history_tree.column("notes",    width=180)
        self.history_tree.tag_configure("overdue", foreground=C_DR_TEXT,
                                        font=self.FONTS["body_strong"])
        self.history_tree.pack(fill="both", expand=True, pady=(SP["md"], 0))
        self.history_tree.bind("<Double-1>", self._on_history_double_click)
        self.history_tree.bind("<Button-3>", self._on_history_right_click)
        ttk.Label(self._hist_checkouts_pane,
                  text="Double-click or right-click a row to edit check-out / check-in details.",
                  style="Muted.TLabel").pack(anchor="w", pady=(SP["xs"], 0))

        self._hist_checkouts_pane.pack(fill="both", expand=True)

        # ── Plays pane (read-only; log/edit on the Plays tab) ────────────────
        self._hist_plays_pane = ttk.Frame(frame)

        pcols = ("game", "date", "players", "winner", "duration")
        p_tree_row = ttk.Frame(self._hist_plays_pane)
        p_tree_row.pack(fill="both", expand=True, pady=(SP["sm"], 0))
        self.history_plays_tree = ttk.Treeview(
            p_tree_row, columns=pcols, show="headings")
        self.history_plays_tree.heading("game",     text="Game")
        self.history_plays_tree.heading("date",     text="Date")
        self.history_plays_tree.heading("players",  text="Players")
        self.history_plays_tree.heading("winner",   text="Winner")
        self.history_plays_tree.heading("duration", text="Duration")
        self.history_plays_tree.column("game",     width=220, anchor="w")
        self.history_plays_tree.column("date",     width=110, anchor="center", stretch=False)
        self.history_plays_tree.column("players",  width=240, anchor="w")
        self.history_plays_tree.column("winner",   width=150, anchor="center", stretch=False)
        self.history_plays_tree.column("duration", width=90,  anchor="center", stretch=False)
        p_vsb = ttk.Scrollbar(p_tree_row, orient="vertical",
                               command=self.history_plays_tree.yview)
        self.history_plays_tree.configure(yscrollcommand=p_vsb.set)
        self.history_plays_tree.pack(side="left", fill="both", expand=True)
        p_vsb.pack(side="right", fill="y")
        ttk.Label(self._hist_plays_pane,
                  text="Use the Plays tab to log or edit plays.",
                  style="Muted.TLabel").pack(anchor="w", pady=(SP["xs"], 0))
        # not packed — shown when mode == "plays"

    def refresh_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        with db.connect() as c:
            rows = db.loan_history(c)
        today = datetime.now().date()
        f = self.history_filter.get()
        for r in rows:
            if f == "open" and r["returned_at"] is not None:
                continue
            if f == "closed" and r["returned_at"] is None:
                continue
            due_str = r["due_date"] or "—"
            overdue = (
                r["returned_at"] is None
                and r["due_date"]
                and r["due_date"] < str(today)
            )
            if overdue:
                due_str = f"⚠ {r['due_date']}"
            self.history_tree.insert(
                "",
                "end",
                iid=str(r["id"]),
                values=(
                    r["game_name"],
                    f"{r['first_name']} {r['last_name']}",
                    fmt_date(r["checked_out_at"]),
                    due_str,
                    fmt_date(r["returned_at"]) or "⬤ still out",
                    r["notes"] or "",
                ),
                tags=("overdue",) if overdue else (),
            )

    def _set_history_mode(self, mode: str) -> None:
        self.history_mode.set(mode)
        is_plays = mode == "plays"
        for btn, m in [
            (self._hist_btn_checkouts, "checkouts"),
            (self._hist_btn_plays,     "plays"),
        ]:
            active = m == mode
            btn.configure(
                bg=C_BLUE_050 if active else C_SURFACE,
                fg=C_BLUE_800 if active else C_INK_600,
            )
        if is_plays:
            self._hist_checkouts_pane.pack_forget()
            self._hist_plays_pane.pack(fill="both", expand=True)
            self._refresh_history_plays()
        else:
            self._hist_plays_pane.pack_forget()
            self._hist_checkouts_pane.pack(fill="both", expand=True)
            self.refresh_history()

    def _refresh_history_plays(self) -> None:
        self.history_plays_tree.delete(*self.history_plays_tree.get_children())
        with db.connect() as c:
            rows = db.list_plays(c)
        for r in rows:
            duration = f"{r['duration_minutes']} min" if r["duration_minutes"] else "—"
            # Plays are date-only events — drop any midnight time component.
            played = fmt_date(r["played_at"])
            if played.endswith(" 00:00"):
                played = played[:-6]
            self.history_plays_tree.insert(
                "", "end",
                values=(
                    r["game_name"],
                    played,
                    r["player_names"] or "",
                    r["winner"] or "—",
                    duration,
                ),
            )

    def _on_history_double_click(self, event: tk.Event) -> None:
        row = self.history_tree.identify_row(event.y)
        if not row:
            return
        self.history_tree.selection_set(row)
        self._edit_loan(int(row))

    def _on_history_right_click(self, event: tk.Event) -> None:
        row = self.history_tree.identify_row(event.y)
        if not row:
            return
        self.history_tree.selection_set(row)
        loan_id = int(row)
        with db.connect() as c:
            loan = c.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan:
            return
        menu = tk.Menu(self, tearoff=0)
        if loan["returned_at"] is None:
            menu.add_command(
                label="Mark as Returned (now)",
                command=lambda lid=loan_id: self._loan_mark_returned(lid),
            )
        else:
            menu.add_command(
                label="Mark as Still Out",
                command=lambda lid=loan_id: self._loan_mark_out(lid),
            )
        menu.add_command(label="Edit details…", command=lambda lid=loan_id: self._edit_loan(lid))
        menu.tk_popup(event.x_root, event.y_root)

    def _loan_mark_returned(self, loan_id: int) -> None:
        with db.connect() as c:
            c.execute("UPDATE loans SET returned_at = ? WHERE id = ?",
                      (db.now_iso(), loan_id))
        self.refresh_history()
        self.refresh_members()
        self.refresh_games()
        self.status("Loan marked as returned.")

    def _loan_mark_out(self, loan_id: int) -> None:
        with db.connect() as c:
            c.execute("UPDATE loans SET returned_at = NULL WHERE id = ?", (loan_id,))
        self.refresh_history()
        self.refresh_members()
        self.refresh_games()
        self.status("Loan marked as still out.")

    def _edit_loan(self, loan_id: int) -> None:
        """Open a dialog to edit check-out date, return date, and notes for a loan."""
        with db.connect() as c:
            loan = c.execute(
                """SELECT loans.*, games.name AS game_name,
                          users.first_name, users.last_name
                   FROM loans
                   JOIN games ON games.bgg_id = loans.game_id
                   JOIN users ON users.id     = loans.user_id
                   WHERE loans.id = ?""",
                (loan_id,),
            ).fetchone()
        if not loan:
            return

        win = tk.Toplevel(self)
        win.title("Edit Checkout")
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=C_BG)

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both")

        ttk.Label(frame,
                  text=f"Game:    {loan['game_name']}",
                  font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2,
                                                      sticky="w", pady=(0, 2))
        ttk.Label(frame,
                  text=f"Member: {loan['first_name']} {loan['last_name']}",
                  font=("Segoe UI", 9, "bold")).grid(row=1, column=0, columnspan=2,
                                                      sticky="w", pady=(0, 10))

        lpad = {"sticky": "w", "padx": (0, 10), "pady": 4}

        ttk.Label(frame, text="Checked out:").grid(row=2, column=0, **lpad)
        _out_date_str = (loan["checked_out_at"] or "")[:10]
        _out_time_str = (loan["checked_out_at"] or "")[:19][11:] or "00:00:00"
        out_date_var  = tk.StringVar(value=_out_date_str)
        out_time_var  = tk.StringVar(value=_out_time_str)
        _out_f = ttk.Frame(frame)
        _out_f.grid(row=2, column=1, sticky="w")
        _date_entry(_out_f, out_date_var, width=12).pack(side="left")
        ttk.Entry(_out_f, textvariable=out_time_var, width=9).pack(side="left", padx=(4, 0))
        ttk.Button(_out_f, text="Now", style="Quiet.TButton",
                   command=lambda: [out_date_var.set(db.now_iso()[:10]),
                                    out_time_var.set(db.now_iso()[11:19])]
                   ).pack(side="left", padx=(6, 0))

        ttk.Label(frame, text="Returned (blank = still out):").grid(row=3, column=0, **lpad)
        _ret_date_str = (loan["returned_at"] or "")[:10]
        _ret_time_str = (loan["returned_at"] or "")[:19][11:] or "00:00:00"
        ret_date_var  = tk.StringVar(value=_ret_date_str)
        ret_time_var  = tk.StringVar(value=_ret_time_str)
        _ret_f = ttk.Frame(frame)
        _ret_f.grid(row=3, column=1, sticky="w")
        _date_entry(_ret_f, ret_date_var, width=12).pack(side="left")
        ttk.Entry(_ret_f, textvariable=ret_time_var, width=9).pack(side="left", padx=(4, 0))
        ttk.Button(_ret_f, text="Now", style="Quiet.TButton",
                   command=lambda: [ret_date_var.set(db.now_iso()[:10]),
                                    ret_time_var.set(db.now_iso()[11:19])]).pack(side="left", padx=(6, 0))
        ttk.Button(_ret_f, text="Clear", style="Quiet.TButton",
                   command=lambda: [ret_date_var.set(""), ret_time_var.set("")]).pack(side="left")

        ttk.Label(frame, text="Due date:").grid(row=4, column=0, **lpad)
        due_var = tk.StringVar(value=loan["due_date"] or "")
        _date_entry(frame, due_var, width=14).grid(row=4, column=1, sticky="w")

        ttk.Label(frame, text="Notes:").grid(row=5, column=0, **lpad)
        notes_var = tk.StringVar(value=loan["notes"] or "")
        ttk.Entry(frame, textvariable=notes_var, width=32).grid(row=5, column=1, sticky="ew")

        err_var = tk.StringVar()
        ttk.Label(frame, textvariable=err_var, foreground=C_DR_TEXT,
                  font=("Segoe UI", 8)).grid(row=6, column=0, columnspan=2, sticky="w")

        def save() -> None:
            _od = out_date_var.get().strip()
            _ot = out_time_var.get().strip() or "00:00:00"
            out_val = f"{_od}T{_ot}" if _od else None
            _rd = ret_date_var.get().strip()
            _rt = ret_time_var.get().strip() or "00:00:00"
            ret_val   = f"{_rd}T{_rt}" if _rd else None
            due_val   = due_var.get().strip()   or None
            notes_val = notes_var.get().strip() or None
            if not out_val:
                err_var.set("Checked-out date is required.")
                return
            with db.connect() as c:
                c.execute(
                    "UPDATE loans SET checked_out_at=?, returned_at=?, due_date=?, notes=? WHERE id=?",
                    (out_val, ret_val, due_val, notes_val, loan_id),
                )
            win.destroy()
            self.refresh_history()
            self.refresh_members()
            self.refresh_games()
            self.refresh_dashboard()
            self.status("Loan record updated.")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btn_row, text="Cancel", style="Ghost.TButton",
                   command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Save",   command=save).pack(side="left")

        win.grab_set()

    # ---------- settings dialog ----------

    def on_open_settings(self) -> None:
        """Open the Settings dialog from File → Settings…"""
        win = tk.Toplevel(self)
        win.title("Settings")
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=C_BG)
        win.lift()
        win.focus_force()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill="both", expand=True)

        # ── BGG username ──────────────────────────────────────────────────────
        ttk.Label(frame, text="BGG username:").grid(row=0, column=0, sticky="w", pady=4)
        username_var = tk.StringVar(value=self.settings.get("bgg_username", ""))
        self.username_var = username_var          # keep ref for import dialog
        ttk.Entry(frame, textvariable=username_var, width=32).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            frame, text="Used by Library → Sync from BGG… and play sync",
            foreground=C_INK_500,
        ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(0, 8))

        # ── BGG password (keychain) ───────────────────────────────────────────
        ttk.Label(frame, text="BGG password:").grid(row=2, column=0, sticky="w", pady=4)
        pwd_var = tk.StringVar(value=_kr_get_password())
        pwd_entry = ttk.Entry(frame, textvariable=pwd_var, width=32, show="●")
        pwd_entry.grid(row=2, column=1, sticky="w", padx=(8, 0))
        _stored = bool(_kr_get_password())
        _pwd_hint = "✓ Saved securely (DPAPI)" if _stored else "Optional — needed for private collections"
        pwd_hint_var = tk.StringVar(value=_pwd_hint)
        ttk.Label(frame, textvariable=pwd_hint_var, foreground=C_INK_500 if not _stored else C_OK_SOLID,
                  ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(0, 4))
        ttk.Button(
            frame, text="Clear saved password", style="Ghost.TButton",
            command=lambda: [_kr_set_password(""), pwd_var.set(""),
                             pwd_hint_var.set("Cleared — enter a new password to save")]
        ).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 12))

        # ── sync plays toggle ─────────────────────────────────────────────────
        sync_var = tk.BooleanVar(value=bool(self.settings.get("bgg_sync_plays", False)))
        ttk.Checkbutton(
            frame,
            text="Offer to post plays to BGG when logging a play",
            variable=sync_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 4))

        def save() -> None:
            self.settings["bgg_username"] = username_var.get().strip()
            # Preserve the existing token — managed via build secrets, not user-entered
            self.settings.pop("bgg_password", None)   # never in JSON
            self.settings["bgg_sync_plays"] = sync_var.get()
            config.save(self.settings)
            # Save password to DPAPI-encrypted file
            _kr_set_password(pwd_var.get())
            self.status("Settings saved.")
            win.destroy()

        # ── danger zone ───────────────────────────────────────────────────────
        tk.Frame(frame, bg=C_PALE, height=1).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        tk.Label(
            frame, text="Danger zone",
            bg=C_BG, fg=C_DR_TEXT,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=8, column=0, sticky="w", pady=(8, 4))

        tk.Button(
            frame, text="Clear collection…",
            bg=C_DR_SOLID, fg=C_WHITE,
            activebackground="#7f0000", activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=12, pady=4, cursor="hand2",
            command=self.on_clear_collection,
        ).grid(row=9, column=0, sticky="w")
        tk.Label(
            frame,
            text="Removes games and loan history. Play history is kept\n(games with logged plays stay). Members are kept.",
            bg=C_BG, fg=C_INK_500,
            font=("Segoe UI", 8), justify="left",
        ).grid(row=9, column=1, sticky="w", padx=(12, 0))

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=10, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Save", command=save).pack(side="left")

        frame.columnconfigure(1, weight=1)
        win.grab_set()

    def on_clear_collection(self) -> None:
        with db.connect() as c:
            collections = db.list_collections(c)
        if len(collections) >= 2:
            self._clear_collection_picker(collections)
        elif len(collections) == 1:
            self._clear_one_collection(collections[0])
        else:
            self._clear_entire_library()

    def _drop_images(self, bgg_ids) -> None:
        """Delete cached cover files for the given game ids."""
        for gid in bgg_ids:
            for p in IMAGES_DIR.glob(f"{gid}.*"):
                try:
                    p.unlink()
                except OSError:
                    pass

    def _clear_one_collection(self, col) -> None:
        name = col["name"]
        if not messagebox.askyesno(
            "Clear collection",
            f"Remove the collection “{name}” and its games?\n\n"
            "Play history is kept — any game with logged plays stays in your "
            "library. Members and settings are kept.\n\nThis cannot be undone.",
            icon="warning",
        ):
            return
        with db.connect() as c:
            deleted = db.clear_collections(c, [col["id"]])
        self._drop_images(deleted)
        self._image_cache.clear()
        self._gradient_cache.clear()
        self._placeholder_img = None
        self._active_collection = None
        self._collection_sig = None
        self.refresh_all()
        self.status(
            f"Cleared “{name}”; deleted {len(deleted)} game"
            f"{'s' if len(deleted) != 1 else ''} (games with plays kept).")

    def _clear_entire_library(self) -> None:
        if not messagebox.askyesno(
            "Clear library",
            "This will remove all games and loan history. Play history is kept "
            "(games with logged plays stay).\n\nMembers and settings are kept.\n\n"
            "Are you sure?",
            icon="warning",
        ):
            return
        with db.connect() as c:
            # Keep games that have plays so their play history survives.
            deleted = [r["bgg_id"] for r in c.execute(
                "SELECT bgg_id FROM games "
                "WHERE bgg_id NOT IN (SELECT DISTINCT game_id FROM plays)")]
            c.execute("DELETE FROM games "
                      "WHERE bgg_id NOT IN (SELECT DISTINCT game_id FROM plays)")
            c.execute("DELETE FROM collections")
        self._drop_images(deleted)
        self._image_cache.clear()
        self._gradient_cache.clear()
        self._placeholder_img = None
        self._active_collection = None
        self._collection_sig = None
        self.refresh_all()
        self.status(f"Library cleared; {len(deleted)} game"
                    f"{'s' if len(deleted) != 1 else ''} removed (games with plays kept).")

    def _clear_collection_picker(self, collections: list) -> None:
        """Dialog to choose which collection(s) to clear (2+ collections)."""
        win = tk.Toplevel(self)
        win.title("Clear Collections")
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=C_BG)

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Clear collections",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=("Pick the collections to clear. A game is deleted only if it is\n"
                  "not kept by another collection. Play and loan history for\n"
                  "deleted games is removed too. Members are kept."),
            foreground=C_INK_600, font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", pady=(2, 10))

        vars_by_id: dict[int, tk.BooleanVar] = {}
        for col in collections:
            v = tk.BooleanVar(value=False)
            vars_by_id[col["id"]] = v
            ttk.Checkbutton(
                frame,
                text=f'{col["name"]}  ·  {col["game_count"]} game'
                     f'{"s" if col["game_count"] != 1 else ""}',
                variable=v, style="Filter.TCheckbutton",
            ).pack(anchor="w", pady=1)

        def do_clear() -> None:
            sel = [cid for cid, v in vars_by_id.items() if v.get()]
            if not sel:
                messagebox.showinfo("Clear Collections",
                                    "Select at least one collection to clear.",
                                    parent=win)
                return
            names = [c["name"] for c in collections if c["id"] in sel]
            if not messagebox.askyesno(
                "Clear collections",
                f"Permanently clear {len(sel)} collection"
                f"{'s' if len(sel) != 1 else ''}?\n\n• " + "\n• ".join(names)
                + "\n\nGames kept only by these collections will be deleted. "
                  "Play history is kept — any game with logged plays stays.\n"
                  "This cannot be undone.",
                icon="warning", parent=win,
            ):
                return
            with db.connect() as c:
                deleted = db.clear_collections(c, sel)
            # Drop cached image files for deleted games
            for gid in deleted:
                for p in IMAGES_DIR.glob(f"{gid}.*"):
                    try:
                        p.unlink()
                    except OSError:
                        pass
            self._image_cache.clear()
            self._gradient_cache.clear()
            self._placeholder_img = None
            self._active_collection = None
            self._collection_sig = None
            win.destroy()
            self.refresh_all()
            self.status(
                f"Cleared {len(sel)} collection{'s' if len(sel) != 1 else ''}; "
                f"deleted {len(deleted)} game{'s' if len(deleted) != 1 else ''}."
            )

        btn_row = ttk.Frame(frame)
        btn_row.pack(anchor="e", pady=(16, 0))
        ttk.Button(btn_row, text="Cancel", style="Ghost.TButton",
                   command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Clear Selected", style="Danger.TButton",
                   command=do_clear).pack(side="left")
        win.grab_set()

    # ---------- about ----------

    def on_about(self) -> None:
        win = tk.Toplevel(self)
        win.title("About Board Game Library")
        win.resizable(False, False)
        win.transient(self)
        win.configure(bg=C_BG)

        # Navy header banner
        hdr = tk.Frame(win, bg=C_NAVY, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\U0001f3b2", bg=C_NAVY, fg=C_WHITE,
                 font=("Segoe UI", 32)).pack()
        tk.Label(hdr, text="Board Game Library", bg=C_NAVY, fg=C_WHITE,
                 font=("Segoe UI", 16, "bold")).pack()
        tk.Label(hdr, text=f"Version {APP_VERSION}", bg=C_NAVY, fg=C_SKY,
                 font=("Segoe UI", 10)).pack(pady=(2, 0))

        # Info body
        body = tk.Frame(win, bg=C_BG, padx=30, pady=20)
        body.pack()

        rows = [
            ("Version",    APP_VERSION),
            ("Created",    APP_CREATED),
            ("Created by", APP_AUTHOR),
            ("Built with", "Claude Code  •  Python  •  Tkinter  •  SQLite"),
            ("Data source", "BoardGameGeek (boardgamegeek.com)"),
        ]
        for label, value in rows:
            row = tk.Frame(body, bg=C_BG)
            row.pack(anchor="w", pady=3)
            tk.Label(row, text=f"{label}:", bg=C_BG, fg=C_NAVY,
                     font=("Segoe UI", 9, "bold"), width=12, anchor="e").pack(side="left")
            tk.Label(row, text=value, bg=C_BG, fg=C_TEXT,
                     font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))

        # Contact row — clickable mailto link
        contact_row = tk.Frame(body, bg=C_BG)
        contact_row.pack(anchor="w", pady=3)
        tk.Label(contact_row, text="Contact:", bg=C_BG, fg=C_NAVY,
                 font=("Segoe UI", 9, "bold"), width=12, anchor="e").pack(side="left")
        tk.Button(
            contact_row, text=APP_CONTACT,
            bg=C_BG, fg=C_BLUE, relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "underline"),
            command=lambda: _open_url(f"mailto:{APP_CONTACT}"),
        ).pack(side="left", padx=(8, 0))

        # Divider
        tk.Frame(win, bg=C_BLUE, height=1).pack(fill="x", padx=20)

        # Footer
        footer = tk.Frame(win, bg=C_PALE, pady=12)
        footer.pack(fill="x")
        tk.Label(
            footer,
            text="Created by Ballewcifer using Claude Code",
            bg=C_PALE, fg=C_NAVY,
            font=("Segoe UI", 9, "italic"),
        ).pack()

        tk.Button(
            win, text="Close", command=win.destroy,
            bg=C_BLUE, fg=C_WHITE, activebackground=C_NAVY, activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=20, pady=6, cursor="hand2",
        ).pack(pady=(14, 18))

        win.grab_set()

    # ---------- actions ----------

    def status(self, msg: str) -> None:
        self.status_var.set(msg)
        prog = self._parse_progress(msg)
        if prog:
            self._set_progress(*prog)
        elif getattr(self, "_progress_active", False):
            self._clear_progress()
        self.update_idletasks()

    @staticmethod
    def _parse_progress(msg: str) -> Optional[tuple]:
        """Pull an (current, total) pair out of a status message, if present.
        Handles "21-40 of 269", "34/269", and "34 of 269"."""
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)", msg)
        if m:
            return (int(m.group(2)), int(m.group(3)))
        m = re.search(r"(\d+)\s*/\s*(\d+)", msg)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        m = re.search(r"(\d+)\s+of\s+(\d+)", msg)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return None

    def _set_progress(self, current: int, total: int) -> None:
        if total <= 0:
            return
        current = max(0, min(current, total))
        if not getattr(self, "_progress_active", False):
            self._progress_count.pack(side="right")
            self._progress_bar.pack(side="right", padx=(0, self.SP["md"]))
            self._progress_active = True
        self._progress_bar.configure(maximum=total, value=current)
        self._progress_var.set(f"{current} of {total}")

    def _clear_progress(self) -> None:
        if getattr(self, "_progress_active", False):
            self._progress_bar.pack_forget()
            self._progress_count.pack_forget()
            self._progress_var.set("")
            self._progress_active = False

    def on_import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select your BGG collection CSV export",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        csv_path = Path(path)
        self.status(f"Reading {csv_path.name}…")

        def _bg():
            try:
                games = bgg.import_collection_csv(csv_path)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Import failed", f"Could not read CSV:\n{e}"))
                self._post_status("Import failed.")
                return
            if not games:
                self.after(0, lambda: messagebox.showinfo("Nothing imported", "No games were found in that CSV."))
                self._post_status("Nothing to import.")
                return
            self.after(0, lambda g=games: _finish(g))

        def _finish(games):
            self._save_games_to_db(games)
            self.refresh_games()
            self.status(f"Imported {len(games)} games. Downloading thumbnails in the background…")
            threading.Thread(target=self._download_thumbnails_bg, args=(games,), daemon=True).start()

        threading.Thread(target=_bg, daemon=True).start()

    def on_import_from_bgg(self) -> None:
        """Sync collection from BGG.

        If username and password are already saved, syncs immediately without
        a dialog.  If either is missing, shows the credentials dialog first.
        To change saved credentials, use File → Settings.
        """
        username = self.settings.get("bgg_username", "").strip()
        password = _kr_get_password()
        tok      = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "").strip()

        # Always show the Sync dialog (pre-filled) so credentials can be entered
        # or updated right in the sync flow — parity with the mobile app.
        dialog = tk.Toplevel(self)
        dialog.title("Sync with BGG")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(bg=C_BG)
        dialog.lift()
        dialog.focus_force()

        tk.Label(
            dialog,
            text="Sync your BoardGameGeek collection.\n"
                 "Credentials are saved securely for next time.",
            bg=C_BG, fg=C_INK_900, font=("Segoe UI", 9),
            padx=16, justify="left",
        ).pack(anchor="w", pady=(14, 6))

        ttk.Label(dialog, text="BGG username:", padding=(16, 4, 16, 2)).pack(anchor="w")
        uname_var = tk.StringVar(value=username)
        entry = ttk.Entry(dialog, textvariable=uname_var, width=34)
        entry.pack(padx=16, pady=(0, 8))
        entry.focus_set()

        ttk.Label(dialog, text="BGG password (optional):",
                  padding=(16, 4, 16, 2)).pack(anchor="w")
        pwd_var = tk.StringVar(value=password)
        ttk.Entry(dialog, textvariable=pwd_var, width=34, show="●").pack(padx=16, pady=(0, 2))
        tk.Label(
            dialog, text="Only needed for private collections.",
            bg=C_BG, fg="#888", font=("Segoe UI", 8), padx=16, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # Claim this collection as your own — disabled once you've claimed one.
        already_claimed = bool(self.settings.get("claimed_member_id"))
        _state = "disabled" if already_claimed else "normal"
        claim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Claim this collection as my own",
                        variable=claim_var, state=_state).pack(
                            anchor="w", padx=16, pady=(2, 0))
        _name_row = ttk.Frame(dialog)
        _name_row.pack(padx=16, pady=(2, 2), anchor="w")
        first_var = tk.StringVar()
        last_var  = tk.StringVar()
        ttk.Entry(_name_row, textvariable=first_var, width=15,
                  state=_state).pack(side="left")
        ttk.Entry(_name_row, textvariable=last_var, width=16,
                  state=_state).pack(side="left", padx=(6, 0))
        tk.Label(
            dialog,
            text=("You've already claimed a collection."
                  if already_claimed else
                  "Adds you as a member and restricts check-outs so only you can\n"
                  "borrow games from this collection."),
            bg=C_BG, fg="#888", font=("Segoe UI", 8), padx=16, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=16, pady=(4, 14), fill="x")

        def do_import() -> None:
            uname = uname_var.get().strip()
            pwd   = pwd_var.get()
            if not uname:
                messagebox.showerror("Username required", "Enter your BGG username.", parent=dialog)
                return
            owner_first = first_var.get().strip()
            owner_last  = last_var.get().strip()
            claim = claim_var.get()
            if claim and not (owner_first or owner_last):
                messagebox.showerror(
                    "Name required",
                    "Enter your name to claim this collection as your own.",
                    parent=dialog)
                return
            self.settings["bgg_username"] = uname
            self.settings.pop("bgg_password", None)
            config.save(self.settings)
            _kr_set_password(pwd)
            if hasattr(self, "username_var"):
                self.username_var.set(uname)
            dialog.destroy()
            self.status(f"Syncing with BGG for {uname}…")
            threading.Thread(
                target=self._import_from_username_bg,
                args=(uname, tok, pwd or None),
                kwargs={"owner_first": owner_first if claim else "",
                        "owner_last":  owner_last if claim else "",
                        "claim_as_mine": claim},
                daemon=True,
            ).start()

        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(btn_frame, text="Save & Sync", command=do_import).pack(side="right")
        dialog.bind("<Return>", lambda *_: do_import())
        dialog.bind("<Escape>", lambda *_: dialog.destroy())
        dialog.grab_set()

    def _import_from_username_bg(self, username: str, token: str,
                                   password: Optional[str] = None,
                                   owner_first: str = "", owner_last: str = "",
                                   claim_as_mine: bool = False) -> None:
        try:
            opener = None
            pwd = password or _kr_get_password()
            if pwd:
                self._post_status("Logging in to BGG…")
                try:
                    _jar, opener = bgg._bgg_login(username, pwd)
                except ValueError as e:
                    # Wrong credentials — clear stored password so user is prompted again
                    _kr_set_password("")
                    err = str(e)
                    self.after(0, lambda: messagebox.showerror("Login failed", err))
                    return
                except RuntimeError as e:
                    err = str(e)
                    self.after(0, lambda: messagebox.showerror("Login error", err))
                    return
                self._post_status("Login successful. Fetching collection…")

            games = bgg.import_from_username(username, token=token,
                                              on_status=self._post_status, opener=opener)
            if not games:
                self.after(0, lambda: messagebox.showinfo(
                    "Nothing found",
                    f"No owned games found for '{username}'.\n"
                    "Check the username is correct. If your collection is private,\n"
                    "enter your BGG password in the sync dialog.",
                ))
                self._post_status("Import: nothing found.")
                return

            # Detect games that left THIS collection's BGG list (not other collections')
            bgg_ids = {g.bgg_id for g in games}
            with db.connect() as c:
                all_bgl = db.list_games(c, owned_only=False)
                _cid = db.collection_id_for_username(c, username)
                _old = db.collection_game_ids(c, _cid) if _cid else set()
            removed = [g for g in all_bgl if g["bgg_id"] in _old and g["bgg_id"] not in bgg_ids]

            self._save_games_to_db(games, collection_username=username)

            # Optionally add the importer as a member, claim this collection for
            # them, and mark them as this device's owner ("me") so the UI only
            # offers check-outs from their own collection.
            if claim_as_mine and (owner_first or owner_last):
                with db.connect() as c:
                    cid = db.collection_id_for_username(c, username)
                    if cid:
                        existing = next(
                            (u for u in db.list_users(c)
                             if u["first_name"].strip().lower() == owner_first.lower()
                             and u["last_name"].strip().lower() == owner_last.lower()),
                            None,
                        )
                        uid = existing["id"] if existing else db.add_user(
                            c, owner_first, owner_last)
                        db.claim_collection(c, cid, uid)
                        self.settings["claimed_member_id"] = uid
                        config.save(self.settings)
                self.after(0, self.refresh_members)

            self.after(0, self.refresh_games)
            self._post_status(f"Imported {len(games)} games. Downloading images…")
            if removed:
                self.after(0, lambda r=removed, cid=_cid: self._prompt_bgg_removals(r, cid))
            self._download_thumbnails_bg(games)
        except PermissionError as exc:
            self.after(0, lambda err=str(exc): messagebox.showerror(
                "Sync failed", err))
            self._post_status(f"Sync failed: {exc}")
        except Exception as exc:
            traceback.print_exc()
            self.after(0, lambda err=str(exc): messagebox.showerror(
                "Import failed",
                f"Could not import collection for '{username}':\n{err}",
            ))
            self._post_status("Import from BGG failed.")

    def _auto_sync_bgg(self, username: str, token: str) -> None:
        """Silent background sync triggered automatically on startup.

        Uses the same import_from_username path but never shows error dialogs —
        failures are reported only in the status bar so they don't interrupt the user.
        """
        self.status(f"Auto-syncing with BGG for {username}…")
        threading.Thread(
            target=self._auto_sync_bgg_bg,
            args=(username, token),
            daemon=True,
        ).start()

    def _auto_sync_bgg_bg(self, username: str, token: str) -> None:
        try:
            games = bgg.import_from_username(username, token=token, on_status=self._post_status)
            if not games:
                self._post_status("BGG auto-sync: no games found.")
                return
            # Detect games that left THIS collection's BGG list (not other collections')
            bgg_ids = {g.bgg_id for g in games}
            with db.connect() as c:
                all_bgl = db.list_games(c, owned_only=False)
                _cid = db.collection_id_for_username(c, username)
                _old = db.collection_game_ids(c, _cid) if _cid else set()
            removed = [g for g in all_bgl if g["bgg_id"] in _old and g["bgg_id"] not in bgg_ids]
            self._save_games_to_db(games, collection_username=username)
            self.after(0, self.refresh_games)
            n = len(games)
            self._post_status(f"BGG auto-sync complete: {n} game{'s' if n != 1 else ''} updated.")
            if removed:
                self.after(0, lambda r=removed, cid=_cid: self._prompt_bgg_removals(r, cid))
            self._download_thumbnails_bg(games)
        except Exception as exc:
            self._post_status(f"BGG auto-sync failed: {exc}")

    def _prompt_bgg_removals(self, removed: list, collection_id=None) -> None:
        """Main-thread dialog: offer to remove games no longer in the BGG collection.

        With multiple collections, removal unlinks the game from the synced
        collection and only deletes it entirely if it's in no other collection."""
        if not removed:
            return

        win = tk.Toplevel(self)
        win.title("Games No Longer in BGG Collection")
        win.transient(self)
        win.resizable(False, True)
        win.configure(bg=C_BG)

        _n = len(removed)
        _pl = "s" if _n != 1 else ""
        _vb = "are" if _n != 1 else "is"
        ttk.Label(
            win,
            text=(
                f"{_n} game{_pl} in your library {_vb} no longer in your BGG collection.\n"
                "Check the ones you want to remove from Board Game Library."
            ),
            wraplength=380, justify="left",
        ).pack(padx=20, pady=(16, 8), anchor="w")

        # Scrollable checklist
        list_frame = tk.Frame(win, bg=C_BG)
        list_frame.pack(fill="both", expand=True, padx=20)

        vsb = ttk.Scrollbar(list_frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        canvas = tk.Canvas(list_frame, bg=C_BG, highlightthickness=0,
                           yscrollcommand=vsb.set, height=min(len(removed) * 28, 260))
        canvas.pack(side="left", fill="both", expand=True)
        vsb.configure(command=canvas.yview)

        inner = tk.Frame(canvas, bg=C_BG)
        canvas.create_window(0, 0, anchor="nw", window=inner)

        check_vars: list[tuple] = []   # (game_row, BooleanVar)
        for g in removed:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(inner, text=g["name"], variable=var).pack(anchor="w", pady=1)
            check_vars.append((g, var))

        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        def _do_remove() -> None:
            to_del = [g for g, v in check_vars if v.get()]
            if to_del:
                with db.connect() as c:
                    for g in to_del:
                        if collection_id is not None:
                            db.remove_game_from_collection(c, g["bgg_id"], collection_id)
                            remaining = c.execute(
                                "SELECT COUNT(*) FROM game_collections WHERE game_id = ?",
                                (g["bgg_id"],)).fetchone()[0]
                            if remaining == 0:
                                db.delete_game(c, g["bgg_id"])
                        else:
                            db.delete_game(c, g["bgg_id"])
                self.refresh_games()
                n = len(to_del)
                self.status(f"Removed {n} game{'s' if n != 1 else ''} from the library.")
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=12, padx=20, anchor="e")
        ttk.Button(btn_row, text="Keep All", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Remove Selected", command=_do_remove).pack(side="left")

        win.grab_set()

    def _sync_play_to_bgg_bg(
        self,
        username: str,
        password: str,
        bgg_id: int,
        played_at: str,
        player_names: str,
        notes: str,
    ) -> None:
        """Background thread: log a play to BGG and report the result via status bar."""
        try:
            ok, msg = bgg.log_play_to_bgg(
                username, password, bgg_id, played_at, player_names, notes
            )
            self._post_status(f"BGG sync: {msg}")
        except Exception as exc:
            self._post_status(f"BGG sync error: {exc}")

    def on_sync_api(self) -> None:
        token = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "")
        username = self.settings.get("bgg_username", "")
        if not token:
            messagebox.showinfo(
                "Not configured",
                "The app's BGG API token has not been set yet.\n"
                "Contact the library administrator.",
            )
            return
        if not username:
            messagebox.showerror("Username missing", "Set your BGG username in Settings.")
            self.nb.select(self.settings_tab)
            return
        threading.Thread(target=self._sync_api_bg, args=(username, token), daemon=True).start()

    def _sync_api_bg(self, username: str, token: str) -> None:
        try:
            self._post_status(f"Fetching collection for {username}...")
            collection = bgg.fetch_collection(username, token=token, on_status=self._post_status)
            ids = [e.bgg_id for e in collection]
            self._post_status(f"Got {len(ids)} games. Fetching details...")
            details = bgg.fetch_things(ids, token=token, on_status=self._post_status)
            # merge collection-only fields (my_rating, my_comment) into details
            by_id = {d.bgg_id: d for d in details}
            for entry in collection:
                d = by_id.get(entry.bgg_id)
                if d is not None:
                    d.my_rating = entry.my_rating
                    d.my_comment = entry.my_comment

            # Detect games that left THIS collection's BGG list (not other collections')
            bgg_ids = set(by_id.keys())
            with db.connect() as c:
                all_bgl = db.list_games(c, owned_only=False)
                _cid = db.collection_id_for_username(c, username)
                _old = db.collection_game_ids(c, _cid) if _cid else set()
            removed = [g for g in all_bgl if g["bgg_id"] in _old and g["bgg_id"] not in bgg_ids]

            self._save_games_to_db(list(by_id.values()), collection_username=username)
            self._post_status("Saved to database. Downloading thumbnails...")
            self._download_thumbnails_bg(list(by_id.values()))
            self.after(0, self.refresh_games)
            self._post_status(f"Sync complete: {len(by_id)} games.")
            if removed:
                self.after(0, lambda r=removed, cid=_cid: self._prompt_bgg_removals(r, cid))
        except Exception as e:
            traceback.print_exc()
            self.after(0, lambda err=e: messagebox.showerror("Sync failed", str(err)))
            self._post_status("Sync failed.")

    def on_download_images(self) -> None:
        with db.connect() as c:
            rows = c.execute("SELECT bgg_id, image_path FROM games").fetchall()
        # Only fetch games that are actually missing an image file on disk.
        # Best-at data is collected as a bonus during the same page scrape but
        # should NOT trigger hundreds of requests when all images already exist.
        needs_fetch = [
            r["bgg_id"] for r in rows
            if not r["image_path"] or not Path(r["image_path"]).exists()
        ]
        if not needs_fetch:
            messagebox.showinfo("Images", "All games already have images.")
            return
        self.status(f"Downloading images for {len(needs_fetch)} games in the background…")
        threading.Thread(
            target=self._fetch_and_cache_images_bg,
            args=(needs_fetch,),
            daemon=True,
        ).start()

    def on_upgrade_images(self) -> None:
        """Re-download low-resolution cover images at full quality.

        Older syncs stored BGG's tiny ~150 px thumbnails, so the Large card
        size couldn't show a bigger image. This finds every cover whose file is
        smaller than the largest card needs and re-fetches it full-size.
        """
        with db.connect() as c:
            rows = c.execute("SELECT bgg_id, image_path FROM games").fetchall()

        undersized: list[int] = []
        missing = 0
        for r in rows:
            p = r["image_path"]
            if not p or not Path(p).exists():
                missing += 1
                undersized.append(r["bgg_id"])
                continue
            try:
                if max(Image.open(p).size) < 400:
                    undersized.append(r["bgg_id"])
            except Exception:
                undersized.append(r["bgg_id"])

        if not undersized:
            messagebox.showinfo("Upgrade Image Quality",
                                "All cover images are already high-resolution.")
            return

        if not messagebox.askyesno(
            "Upgrade Image Quality",
            f"Re-download {len(undersized)} cover image"
            f"{'s' if len(undersized) != 1 else ''} at full resolution?\n\n"
            "This runs in the background and may take a few minutes "
            "(it's polite to BGG, ~2 per second).",
        ):
            return

        self.status(f"Upgrading {len(undersized)} cover images in the background…")
        threading.Thread(
            target=self._fetch_and_cache_images_bg,
            args=(undersized,),
            kwargs={"force": True},
            daemon=True,
        ).start()

    def on_random_game(self) -> None:
        """Pick a random game from the library, filtered by simple criteria."""
        win = tk.Toplevel(self)
        win.title("Pick a Random Game")
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=C_BG)

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="🎲  Pick a Random Game",
                  font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2,
                                                       sticky="w", pady=(0, 10))

        # ── criteria ──────────────────────────────────────────────────────────
        players_var    = tk.StringVar(value="Any")
        time_var       = tk.StringVar(value="Any")
        complexity_var = tk.StringVar(value="Any")
        available_var  = tk.BooleanVar(value=True)

        def crit_row(r, label, var, values):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            cb = ttk.Combobox(frame, textvariable=var, values=values,
                              state="readonly", width=16)
            cb.grid(row=r, column=1, sticky="w", pady=3)

        crit_row(1, "Players:", players_var,
                 ["Any", "1", "2", "3", "4", "5", "6", "7", "8+"])
        crit_row(2, "Max play time:", time_var,
                 ["Any", "≤ 30 min", "≤ 60 min", "≤ 90 min", "≤ 120 min"])
        crit_row(3, "Complexity:", complexity_var,
                 ["Any", "Light (1–2)", "Medium (2–3)", "Heavy (3–5)"])
        ttk.Checkbutton(frame, text="Only games that are available (not checked out)",
                        variable=available_var,
                        style="Filter.TCheckbutton").grid(row=4, column=0, columnspan=2,
                                                          sticky="w", pady=(6, 0))

        ttk.Separator(frame, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=12)

        # ── result area ───────────────────────────────────────────────────────
        result_name = tk.StringVar(value="Set your criteria, then press Pick.")
        result_meta = tk.StringVar(value="")
        name_lbl = ttk.Label(frame, textvariable=result_name,
                             font=("Segoe UI", 12, "bold"), wraplength=320, justify="left")
        name_lbl.grid(row=6, column=0, columnspan=2, sticky="w")
        meta_lbl = ttk.Label(frame, textvariable=result_meta, foreground=C_INK_600,
                             font=("Segoe UI", 9), wraplength=320, justify="left")
        meta_lbl.grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))

        picked: list = [None]   # holds the current game row

        def _max_time_limit() -> Optional[int]:
            t = time_var.get()
            return {"≤ 30 min": 30, "≤ 60 min": 60,
                    "≤ 90 min": 90, "≤ 120 min": 120}.get(t)

        def _matches(g, open_ids) -> bool:
            if available_var.get() and g["bgg_id"] in open_ids:
                return False
            pv = players_var.get()
            if pv != "Any":
                mn, mx = g["min_players"], g["max_players"]
                if pv == "8+":
                    if not mx or mx < 8:
                        return False
                else:
                    n = int(pv)
                    lo = mn if mn else 1
                    hi = mx if mx else mn
                    if not hi or not (lo <= n <= hi):
                        return False
            lim = _max_time_limit()
            if lim is not None:
                pt = g["playing_time"] or g["max_playtime"] or g["min_playtime"]
                if pt is None or pt > lim:
                    return False
            cv = complexity_var.get()
            if cv != "Any":
                w = g["weight"]
                if w is None:
                    return False
                if cv == "Light (1–2)" and not (1.0 <= w <= 2.0):
                    return False
                if cv == "Medium (2–3)" and not (2.0 < w <= 3.0):
                    return False
                if cv == "Heavy (3–5)" and not (w > 3.0):
                    return False
            return True

        def pick() -> None:
            with db.connect() as c:
                games = db.list_games(c)
                open_ids = {
                    r["game_id"] for r in c.execute(
                        "SELECT game_id FROM loans WHERE returned_at IS NULL")
                }
            pool = [g for g in games
                    if self._collection_pass(g["bgg_id"]) and _matches(g, open_ids)]
            if not pool:
                picked[0] = None
                result_name.set("No games match those criteria.")
                result_meta.set("Try loosening the filters above.")
                open_btn.state(["disabled"])
                return
            g = random.choice(pool)
            picked[0] = g
            result_name.set(g["name"])
            bits = []
            if g["year"]:
                bits.append(str(g["year"]))
            if g["min_players"] and g["max_players"]:
                bits.append(f'{g["min_players"]}–{g["max_players"]} players')
            pt = g["playing_time"] or g["max_playtime"]
            if pt:
                bits.append(f"{pt} min")
            if g["weight"]:
                bits.append(f'Complexity {g["weight"]:.1f}/5')
            if g["bgg_id"] in open_ids:
                bits.append("⬤ checked out")
            result_meta.set(" · ".join(bits))
            open_btn.state(["!disabled"])

        def open_details() -> None:
            if picked[0] is not None:
                win.destroy()
                self.show_details(picked[0])

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btn_row, text="Close", style="Ghost.TButton",
                   command=win.destroy).pack(side="left", padx=(0, 6))
        open_btn = ttk.Button(btn_row, text="Open Details", style="Ghost.TButton",
                              command=open_details)
        open_btn.pack(side="left", padx=(0, 6))
        open_btn.state(["disabled"])
        ttk.Button(btn_row, text="🎲  Pick", command=pick).pack(side="left")

        win.grab_set()

    def on_add_game(self) -> None:
        """Search BGG by title, pick a result, then confirm/edit before saving."""
        dlg = tk.Toplevel(self)
        dlg.title("Add Game")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(bg=C_BG)

        # ── search row ────────────────────────────────────────────────────────
        top = ttk.Frame(dlg, padding=(12, 12, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Game title:", font=("Segoe UI", 9, "bold")).pack(side="left")
        query_var = tk.StringVar()
        query_entry = ttk.Entry(top, textvariable=query_var, width=36)
        query_entry.pack(side="left", padx=(6, 6))
        search_btn = ttk.Button(top, text="Search BGG")
        search_btn.pack(side="left")

        # ── status + results list ─────────────────────────────────────────────
        status_var = tk.StringVar(value="Enter a title and press Search or Enter.")
        ttk.Label(dlg, textvariable=status_var, foreground=C_INK_600,
                  font=("Segoe UI", 8), padding=(12, 2)).pack(anchor="w")

        list_frame = ttk.Frame(dlg, padding=(12, 0, 12, 4))
        list_frame.pack(fill="both", expand=True)
        lb = tk.Listbox(list_frame, width=56, height=12, selectmode="single",
                        font=("Segoe UI", 9), activestyle="none",
                        selectbackground=C_BLUE, selectforeground=C_WHITE)
        sb = ttk.Scrollbar(list_frame, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        # ── buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(dlg, padding=(12, 4, 12, 12))
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side="right", padx=(6, 0))
        add_btn = ttk.Button(btn_frame, text="Add Selected →", state="disabled")
        add_btn.pack(side="right")

        results: list[tuple[int, str, Optional[int]]] = []

        def do_search(*_) -> None:
            q = query_var.get().strip()
            if not q:
                return
            search_btn.configure(state="disabled")
            add_btn.configure(state="disabled")
            status_var.set("Searching BGG…")
            lb.delete(0, "end")
            results.clear()

            def _bg():
                try:
                    tok = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "")
                    found = bgg.search_games(q, token=tok)
                except Exception as exc:
                    self.after(0, lambda: status_var.set(f"Search failed: {exc}"))
                    self.after(0, lambda: search_btn.configure(state="normal"))
                    return
                self.after(0, lambda f=found: _show(f))

            def _show(found):
                results.extend(found)
                for _, name, year in found:
                    lb.insert("end", f"{name}  ({year})" if year else name)
                n = len(found)
                status_var.set(f"{n} result{'s' if n != 1 else ''} — double-click or select and click Add.")
                search_btn.configure(state="normal")
                if found:
                    lb.selection_set(0)
                    add_btn.configure(state="normal")

            threading.Thread(target=_bg, daemon=True).start()

        def on_select(*_):
            if lb.curselection():
                add_btn.configure(state="normal")

        def proceed(*_) -> None:
            sel = lb.curselection()
            if not sel:
                return
            bgg_id, name, year = results[sel[0]]
            dlg.destroy()
            self._fetch_and_open_edit(bgg_id, name, is_new=True)

        lb.bind("<<ListboxSelect>>", on_select)
        lb.bind("<Double-Button-1>", proceed)
        query_entry.bind("<Return>", do_search)
        search_btn.configure(command=do_search)
        add_btn.configure(command=proceed)

        dlg.grab_set()
        query_entry.focus_set()

    def _fetch_and_open_edit(self, bgg_id: int, name: str, *, is_new: bool) -> None:
        """Fetch full BGG details for bgg_id, then open the edit/confirm dialog."""
        wait = tk.Toplevel(self)
        wait.title("Fetching…")
        wait.transient(self)
        wait.resizable(False, False)
        wait.configure(bg=C_BG)
        ttk.Label(wait, text=f'Fetching details for "{name}"...',
                  padding=(24, 16)).pack()
        wait.grab_set()
        wait.update()

        tok = (bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "")).strip() or None

        def _bg():
            details = None
            if tok:
                try:
                    details_list = bgg.fetch_things([bgg_id], token=tok)
                    details = details_list[0] if details_list else None
                except Exception as exc:
                    # Token present but fetch failed — show error and stop
                    err = str(exc)
                    self.after(0, lambda: [wait.destroy(),
                                           messagebox.showerror("Error",
                                               f"Could not fetch game data:\n{err}")])
                    return
            else:
                # No built-in token — fall back to page scrape for public data.
                details = bgg.fetch_game_details_from_page(bgg_id, fallback_name=name)
                if not details:
                    details = bgg.GameDetails(bgg_id=bgg_id, name=name)
            self.after(0, lambda d=details: [wait.destroy(),
                                             self._open_game_edit_dialog(d, is_new=is_new)])

        threading.Thread(target=_bg, daemon=True).start()

    def on_edit_game(self, game) -> None:
        """Open the edit dialog pre-filled from the existing DB row."""
        # Convert sqlite3.Row → GameDetails so the shared dialog can use it
        details = bgg.GameDetails(
            bgg_id       = game["bgg_id"],
            name         = game["name"],
            year         = game["year"],
            image_url    = game["image_url"],
            thumbnail_url= game["thumbnail_url"],
            min_players  = game["min_players"],
            max_players  = game["max_players"],
            min_playtime = game["min_playtime"],
            max_playtime = game["max_playtime"],
            playing_time = game["playing_time"],
            min_age      = game["min_age"],
            weight       = game["weight"],
            avg_rating   = game["avg_rating"],
            description  = game["description"],
            my_rating    = game["my_rating"],
            my_comment   = game["my_comment"],
            best_players = game["best_players"],
        )
        self._open_game_edit_dialog(details, is_new=False)

    def _open_game_edit_dialog(self, details: Optional[bgg.GameDetails], *,
                               is_new: bool) -> None:
        """Editable form pre-filled from a GameDetails object.

        is_new=True  → saves as a new game (or replaces if BGG ID already exists).
        is_new=False → updates an existing game, preserving image_path.
        """
        if details is None:
            messagebox.showerror("Error", "No game data received from BGG.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Add Game — Confirm Details" if is_new else "Edit Game")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(bg=C_BG)

        lpad = {"padx": (12, 4), "pady": 3, "sticky": "e"}
        rpad = {"padx": (4, 12), "pady": 3, "sticky": "we"}

        def row_entry(r, label, value, width=34):
            ttk.Label(dlg, text=label, font=("Segoe UI", 9, "bold")).grid(
                row=r, column=0, **lpad)
            var = tk.StringVar(value=str(value) if value is not None else "")
            ttk.Entry(dlg, textvariable=var, width=width).grid(row=r, column=1, **rpad)
            return var

        d = details
        # Play time: prefer playing_time, fall back to min/max average
        pt = d.playing_time or (
            ((d.min_playtime or 0) + (d.max_playtime or 0)) // 2 or None
        )

        name_var    = row_entry(0, "Name *",           d.name)
        year_var    = row_entry(1, "Year",              d.year,         width=10)
        bgg_id_var  = row_entry(2, "BGG ID",            d.bgg_id,       width=12)
        minp_var    = row_entry(3, "Min players",       d.min_players,  width=8)
        maxp_var    = row_entry(4, "Max players",       d.max_players,  width=8)
        time_var    = row_entry(5, "Play time (min)",   pt,             width=10)
        weight_var  = row_entry(6, "Complexity (1–5)",
                                f"{d.weight:.2f}" if d.weight else "", width=10)
        best_var    = row_entry(7, "Best at (players)",
                                d.best_players or "",         width=16)
        comment_var = row_entry(8, "Comment",           d.my_comment)

        # Tags row — uses existing tags from DB when editing
        ttk.Label(dlg, text="Tags", font=("Segoe UI", 9, "bold")).grid(row=9, column=0, **lpad)
        existing_tags = ""
        if not is_new:
            with db.connect() as c:
                _row = db.get_game(c, d.bgg_id)
                if _row:
                    existing_tags = _row["tags"] or ""
        with db.connect() as c:
            _existing_tag_list = ["Any"] + db.all_tags(c)
        tags_var = tk.StringVar(value=existing_tags)
        _AutocompleteEntry(dlg, _existing_tag_list, textvariable=tags_var,
                           width=34).grid(row=9, column=1, **rpad)
        ttk.Label(dlg, text="Comma-separated, e.g. Party, Family, Filler",
                  foreground=C_INK_500, font=("Segoe UI", 7),
                  ).grid(row=10, column=1, sticky="w", padx=(4, 12), pady=(0, 2))

        ttk.Label(dlg, text="Description",
                  font=("Segoe UI", 9, "bold")).grid(row=11, column=0, **lpad)
        desc_box = tk.Text(dlg, width=38, height=5, font=("Segoe UI", 9),
                           wrap="word", relief="solid", bd=1)
        desc_box.grid(row=11, column=1, padx=(4, 12), pady=3, sticky="we")
        if d.description:
            desc_box.insert("1.0", d.description)

        _current_insert = False
        if not is_new and d and d.bgg_id and d.bgg_id > 0:
            with db.connect() as c:
                _gi = db.get_game(c, d.bgg_id)
                if _gi:
                    _current_insert = bool(_gi["has_insert"])
        insert_var = tk.BooleanVar(value=_current_insert)
        ttk.Label(dlg, text="3D Insert",
                  font=("Segoe UI", 9, "bold")).grid(row=12, column=0, **lpad)
        ttk.Checkbutton(dlg, text="Has 3D printed insert",
                        variable=insert_var).grid(row=12, column=1, sticky="w",
                                                   padx=(4, 12), pady=3)

        err_var = tk.StringVar()
        ttk.Label(dlg, textvariable=err_var, foreground=C_DR_TEXT,
                  font=("Segoe UI", 8)).grid(
            row=13, column=0, columnspan=2, padx=12, sticky="w")

        # --- lock-status row (editing an existing game only) ---
        _FIELD_DISPLAY = {
            "name": "Name", "year": "Year",
            "min_players": "Min players", "max_players": "Max players",
            "playing_time": "Play time", "min_playtime": "Play time",
            "max_playtime": "Play time",
            "weight": "Complexity", "description": "Description",
            "my_comment": "Comment", "best_players": "Best at",
        }
        lock_lbl_var = tk.StringVar()
        lock_frame = ttk.Frame(dlg)
        lock_frame.grid(row=14, column=0, columnspan=2,
                        padx=12, pady=(0, 2), sticky="w")
        ttk.Label(lock_frame, textvariable=lock_lbl_var,
                  foreground=C_INK_600, font=("Segoe UI", 8)).pack(side="left")

        def _refresh_lock_label() -> None:
            if is_new:
                return
            with db.connect() as c:
                mf = db.get_manual_fields(c, d.bgg_id)
            if mf:
                names = sorted({_FIELD_DISPLAY.get(f, f) for f in mf},
                               key=str.casefold)
                lock_lbl_var.set(f"🔒 Protected from sync: {', '.join(names)}")
                _clear_btn.pack(side="left", padx=(6, 0))
            else:
                lock_lbl_var.set("")
                _clear_btn.pack_forget()

        def _clear_locks() -> None:
            with db.connect() as c:
                db.set_manual_fields(c, d.bgg_id, set())
            _refresh_lock_label()

        _clear_btn = ttk.Button(lock_frame, text="Clear overrides",
                                command=_clear_locks)
        if not is_new:
            _refresh_lock_label()

        def save() -> None:
            name = name_var.get().strip()
            if not name:
                err_var.set("Name is required.")
                return

            def _i(v):
                s = v.get().strip()
                try: return int(s) if s else None
                except ValueError: return None

            def _f(v):
                s = v.get().strip()
                try: return float(s) if s else None
                except ValueError: return None

            bgg_id_s = bgg_id_var.get().strip()
            if bgg_id_s:
                try:
                    bgg_id = int(bgg_id_s)
                except ValueError:
                    err_var.set("BGG ID must be a whole number.")
                    return
            else:
                with db.connect() as c:
                    r = c.execute("SELECT MIN(bgg_id) FROM games").fetchone()
                    lowest = r[0] if r[0] is not None else 0
                bgg_id = min(lowest, 0) - 1

            pt_val = _i(time_var)

            # Preserve image_path / image_url if we're updating an existing game
            existing_image_path = None
            existing_image_url  = None
            existing_thumb_url  = None
            existing            = None
            with db.connect() as c:
                existing = db.get_game(c, bgg_id)
                if existing:
                    existing_image_path = existing["image_path"]
                    existing_image_url  = existing["image_url"]
                    existing_thumb_url  = existing["thumbnail_url"]

            game_row = {
                "bgg_id":        bgg_id,
                "name":          name,
                "year":          _i(year_var),
                "image_url":     existing_image_url  or d.image_url,
                "thumbnail_url": existing_thumb_url  or d.thumbnail_url,
                "image_path":    existing_image_path,
                "min_players":   _i(minp_var),
                "max_players":   _i(maxp_var),
                "min_playtime":  pt_val,
                "max_playtime":  pt_val,
                "playing_time":  pt_val,
                "min_age":       d.min_age,
                "weight":        _f(weight_var),
                "avg_rating":    d.avg_rating,
                "my_rating":     d.my_rating,
                "description":   desc_box.get("1.0", "end-1c").strip() or None,
                "categories":    ", ".join(d.categories) if d.categories else None,
                "mechanics":     ", ".join(d.mechanics)  if d.mechanics  else None,
                "designers":     ", ".join(d.designers)  if d.designers  else None,
                "publishers":    ", ".join(d.publishers) if d.publishers else None,
                "best_players":  best_var.get().strip() or None,
                "my_comment":    comment_var.get().strip() or None,
                "own":           1,
                "last_synced":   db.now_iso(),
            }
            with db.connect() as c:
                # Auto-lock any fields the user explicitly changed vs the DB.
                if not is_new and existing:
                    manual = db.get_manual_fields(c, bgg_id)
                    field_checks = [
                        ("name",         game_row["name"],         existing["name"]),
                        ("year",         game_row["year"],          existing["year"]),
                        ("min_players",  game_row["min_players"],   existing["min_players"]),
                        ("max_players",  game_row["max_players"],   existing["max_players"]),
                        ("best_players", game_row["best_players"],  existing["best_players"]),
                        ("description",  game_row["description"],   existing["description"]),
                        ("my_comment",   game_row["my_comment"],    existing["my_comment"]),
                    ]
                    for field, new_val, old_val in field_checks:
                        if new_val != old_val:
                            manual.add(field)
                    # Weight: round to 2 dp to avoid float-precision false positives.
                    new_w = game_row["weight"]
                    old_w = existing["weight"]
                    if (new_w is None) != (old_w is None) or (
                        new_w is not None and old_w is not None
                        and round(new_w, 2) != round(old_w, 2)
                    ):
                        manual.add("weight")
                    # Playtime: all three columns move together.
                    old_pt = (existing["playing_time"]
                              if existing["playing_time"] is not None
                              else existing["min_playtime"])
                    if pt_val != old_pt:
                        manual.update({"playing_time", "min_playtime", "max_playtime"})
                    db.set_manual_fields(c, bgg_id, manual)

                db.upsert_game(c, game_row)
                # Save tags separately (not part of upsert to avoid clobbering on sync)
                db.set_tags(c, bgg_id, tags_var.get().strip())
                db.set_insert(c, bgg_id, bool(insert_var.get()))

            dlg.destroy()
            self.refresh_games()
            verb = "Added" if is_new else "Updated"
            self.status(f"{verb} \"{name}\".")
            if is_new and game_row.get("image_url"):
                threading.Thread(
                    target=self._fetch_and_cache_images_bg,
                    args=([bgg_id],),
                    daemon=True,
                ).start()

        btn_row = ttk.Frame(dlg, padding=(12, 4, 12, 12))
        btn_row.grid(row=15, column=0, columnspan=2, sticky="e")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Save Game" if is_new else "Save Changes",
                   command=save).pack(side="left")

        dlg.columnconfigure(1, weight=1)
        dlg.grab_set()

    def _fetch_and_cache_images_bg(self, bgg_ids: list[int], force: bool = False) -> None:
        """Download box-art for every game that is missing an image.

        Image URL priority:
          1. image_url / thumbnail_url already stored in the DB (from CSV import)
          2. BGG HTML page scrape via get_bgg_page_data (browser UA, no token)
             — also collects Best-at data in the same request.
        The /xmlapi2/thing endpoint is no longer used here as it now
        requires a Bearer token.

        When *force* is True, existing on-disk images are re-downloaded (used to
        upgrade old low-resolution thumbnails to full-size box art).
        """
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        total = len(bgg_ids)
        done = 0
        img_ok = 0
        img_failed = 0
        last_error = ""

        for bgg_id in bgg_ids:
            self._post_status(f"Downloading images {done + 1}/{total}…")

            with db.connect() as c:
                row = db.get_game(c, bgg_id)

            need_image = force or not (row and row["image_path"] and Path(row["image_path"]).exists())

            # ── image download ────────────────────────────────────────────────
            if need_image:
                # 1. Use URL already in the DB (populated from CSV import).
                #    Prefer the full-resolution image over the tiny thumbnail.
                url = (
                    (row["image_url"]     if row else None)
                    or (row["thumbnail_url"] if row else None)
                )
                if url:
                    ext  = Path(url.split("?", 1)[0]).suffix or ".jpg"
                    dest = IMAGES_DIR / f"{bgg_id}{ext}"
                    try:
                        bgg.download_image(url, dest)
                        self._cap_image_file(str(dest))
                        with db.connect() as c:
                            db.set_image_path(c, bgg_id, str(dest))
                        img_ok += 1
                    except Exception as exc:
                        img_failed += 1
                        last_error = str(exc)
                    # skip the page scrape below — we already got the image
                    done += 1
                    time.sleep(0.5)
                    continue

            # ── BGG page scrape: image URL + best-at in one request ───────────
            need_best = not (row and row["best_players"])
            if need_image or need_best:
                try:
                    page = bgg.get_bgg_page_data(bgg_id)

                    if need_image and page.image_url:
                        url = page.image_url
                        ext  = Path(url.split("?", 1)[0]).suffix or ".jpg"
                        dest = IMAGES_DIR / f"{bgg_id}{ext}"
                        try:
                            bgg.download_image(url, dest)
                            self._cap_image_file(str(dest))
                            with db.connect() as c:
                                db.set_image_path(c, bgg_id, str(dest))
                            img_ok += 1
                        except Exception as exc:
                            img_failed += 1
                            last_error = str(exc)
                    elif need_image:
                        img_failed += 1
                        last_error = f"No image URL found for game #{bgg_id}"

                    if need_best and page.best_players:
                        with db.connect() as c:
                            c.execute(
                                "UPDATE games SET best_players = ? WHERE bgg_id = ?",
                                (page.best_players, bgg_id),
                            )
                except Exception as exc:
                    if need_image:
                        img_failed += 1
                        last_error = f"#{bgg_id}: {exc}"
                    # best-at is a bonus — never block on failure

            done += 1
            time.sleep(0.5)  # be polite to BGG

        self.after(0, self.refresh_games)
        msg = f"Done — {img_ok} of {total} images downloaded."
        if img_failed:
            msg += f"  {img_failed} failed."
        self._post_status(msg)
        self.after(0, self._clear_progress)

    def _post_status(self, msg: str) -> None:
        self.after(0, self.status, msg)

    def _save_games_to_db(self, games: list[bgg.GameDetails],
                          collection_username: Optional[str] = None,
                          collection_name: Optional[str] = None) -> None:
        with db.connect() as c:
            for g in games:
                row = {
                    "bgg_id": g.bgg_id,
                    "name": g.name,
                    "year": g.year,
                    "image_url": g.image_url,
                    "thumbnail_url": g.thumbnail_url,
                    "image_path": None,
                    "min_players": g.min_players,
                    "max_players": g.max_players,
                    "min_playtime": g.min_playtime,
                    "max_playtime": g.max_playtime,
                    "playing_time": g.playing_time,
                    "min_age": g.min_age,
                    "weight": g.weight,
                    "avg_rating": g.avg_rating,
                    "my_rating": g.my_rating,
                    "description": g.description,
                    "categories": ", ".join(g.categories) if g.categories else None,
                    "mechanics": ", ".join(g.mechanics) if g.mechanics else None,
                    "designers": ", ".join(g.designers) if g.designers else None,
                    "publishers": ", ".join(g.publishers) if g.publishers else None,
                    "best_players": g.best_players,
                    "my_comment": g.my_comment,
                    "own": 1,
                    "last_synced": db.now_iso(),
                    "is_expansion": int(g.is_expansion),
                }
                # Don't clobber image_path or manually-locked fields on re-sync.
                existing = db.get_game(c, g.bgg_id)
                skip: set = set()
                if existing:
                    if existing["image_path"]:
                        row["image_path"] = existing["image_path"]
                    skip = db.get_manual_fields(c, g.bgg_id)
                db.upsert_game(c, row, skip_fields=skip)

            # Link these games to their collection (one collection per synced BGG
            # username); the collection's membership becomes exactly this set.
            if collection_username:
                cid = db.get_or_create_collection(
                    c, collection_username, collection_name or collection_username)
                db.replace_collection_games(c, cid, [g.bgg_id for g in games])

    # Largest card cover is 260 px tall; store covers a bit bigger so they look
    # crisp at the Large size, but cap to keep image files small on disk.
    IMAGE_MAX_PX = 700

    def _cap_image_file(self, path: str, max_px: int = IMAGE_MAX_PX) -> None:
        """Downscale an on-disk image in place if it exceeds *max_px* on a side."""
        try:
            im = Image.open(path)
            if max(im.size) <= max_px:
                return
            im.thumbnail((max_px, max_px), Image.LANCZOS)
            if im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            im.save(path, quality=90)
        except Exception:
            pass

    def _download_thumbnails_bg(self, games: list[bgg.GameDetails]) -> None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        ok = 0
        failed = 0
        last_error = ""
        total = len(games)
        for i, g in enumerate(games, 1):
            self._post_status(f"Downloading images {i} of {total}…")
            # Prefer the full-resolution image so Large cards stay crisp; the
            # tiny BGG thumbnail is only a fallback.
            url = g.image_url or g.thumbnail_url
            if not url:
                continue
            with db.connect() as c:
                row = db.get_game(c, g.bgg_id)
                if row and row["image_path"] and Path(row["image_path"]).exists():
                    continue
            ext = Path(url.split("?", 1)[0]).suffix or ".jpg"
            dest = IMAGES_DIR / f"{g.bgg_id}{ext}"
            try:
                bgg.download_image(url, dest)
                self._cap_image_file(str(dest))
                with db.connect() as c:
                    db.set_image_path(c, g.bgg_id, str(dest))
                ok += 1
            except Exception as exc:
                failed += 1
                last_error = str(exc)
        self.after(0, self.refresh_games)
        msg = f"Done — {ok} of {total} images downloaded."
        if failed:
            msg += f" {failed} failed."
        self._post_status(msg)
        self.after(0, self._clear_progress)

    # ---------- check in / out ----------

    def on_check_out(self, game) -> None:
        with db.connect() as c:
            all_users = db.list_users(c)
            allowed = db.members_allowed_to_checkout(c, game["bgg_id"])
        if not all_users:
            messagebox.showinfo("No members", "Add a member on the Members tab first.")
            self.nb.select(self.members_tab)
            return

        # Members who have claimed a different collection can only check out
        # their own games, so they're hidden from this game's list.
        users = [u for u in all_users if u["id"] in allowed]
        if not users:
            messagebox.showinfo(
                "Not available to anyone",
                f"\"{game['name']}\" isn't in any member's claimed collection, so "
                "no eligible member can check it out.\n\n"
                "Members who haven't claimed a collection can borrow any game.",
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Check Out")
        dialog.transient(self)
        dialog.resizable(False, False)
        ttk.Label(dialog, text=f"Check out \"{game['name']}\" to:").grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6), sticky="w")

        names = [f"{u['first_name']} {u['last_name']}" for u in users]
        member_var = tk.StringVar(value=names[0])
        ttk.Combobox(dialog, textvariable=member_var, values=names, state="readonly", width=30).grid(row=1, column=0, columnspan=2, padx=12, sticky="we")

        ttk.Label(dialog, text="Due date (optional):").grid(row=2, column=0, columnspan=2, padx=12, pady=(8, 0), sticky="w")
        due_var = tk.StringVar()
        _date_entry(dialog, due_var, width=14).grid(row=3, column=0, padx=12, pady=(2, 4), sticky="w")

        ttk.Label(dialog, text="Notes (optional):").grid(row=4, column=0, columnspan=2, padx=12, pady=(4, 0), sticky="w")
        notes_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=notes_var, width=34).grid(row=5, column=0, columnspan=2, padx=12, pady=(2, 8), sticky="we")

        def confirm() -> None:
            idx = names.index(member_var.get())
            user_id = users[idx]["id"]
            due = due_var.get().strip() or None
            try:
                with db.connect() as c:
                    if not db.user_can_checkout(c, user_id, game["bgg_id"]):
                        messagebox.showerror(
                            "Not in their collection",
                            f"{member_var.get()} has claimed a collection and can only "
                            f"check out games from it.\n\"{game['name']}\" isn't in it.")
                        return
                    db.check_out(c, game["bgg_id"], user_id, notes_var.get().strip(), due_date=due)
            except ValueError as e:
                messagebox.showerror("Cannot check out", str(e))
                return
            dialog.destroy()
            self.refresh_games()
            self.refresh_members()
            self.refresh_history()
            self.refresh_dashboard()
            self.status(f"Checked out \"{game['name']}\" to {member_var.get()}.")

        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(row=6, column=0, padx=12, pady=(0, 12), sticky="we")
        ttk.Button(dialog, text="Check Out", command=confirm).grid(row=6, column=1, padx=12, pady=(0, 12), sticky="we")
        dialog.grab_set()

    def on_check_in(self, game) -> None:
        if not messagebox.askyesno("Check in", f"Mark \"{game['name']}\" as returned?"):
            return
        try:
            with db.connect() as c:
                db.check_in(c, game["bgg_id"])
        except ValueError as e:
            messagebox.showerror("Cannot check in", str(e))
            return
        self.refresh_games()
        self.refresh_members()
        self.refresh_history()
        self.refresh_dashboard()
        self.status(f"Checked in \"{game['name']}\".")

    # ---------- delete game ----------

    def on_delete_game(self, game) -> None:
        name = game["name"]
        if not messagebox.askyesno(
            "Remove from Library?",
            f'Remove "{name}" from Board Game Library?\n\n'
            "This will delete its check-out history and play logs from this app only.\n\n"
            "⚠  This does NOT delete the game from BGG. If it is still in your BGG\n"
            "collection, it will be added back the next time you sync.",
            icon="warning",
        ):
            return
        with db.connect() as c:
            db.delete_game(c, game["bgg_id"])
        self.refresh_games()
        self.refresh_history()
        self.status(f'Deleted "{name}".')

    def _add_collection_remove_item(self, menu, game) -> None:
        """Add 'Remove from <collection>' when a specific collection tab is active
        and this game belongs to it."""
        cid = self._active_collection
        if len(self._collections) < 2 or cid is None:
            return
        if cid not in self._gc_map.get(game["bgg_id"], set()):
            return
        cname = next((col["name"] for col in self._collections if col["id"] == cid), "collection")
        menu.add_command(label=f"Remove from “{cname}”",
                         command=lambda: self.on_remove_from_collection(game))

    def on_remove_from_collection(self, game) -> None:
        cid = self._active_collection
        if cid is None:
            return
        cname = next((col["name"] for col in self._collections if col["id"] == cid), "this collection")
        if not messagebox.askyesno(
            "Remove from collection",
            f'Remove "{game["name"]}" from the "{cname}" collection?\n\n'
            "The game stays in your library and in any other collections — it's just "
            "unlinked from this one. (A future sync of this collection may re-add it.)",
        ):
            return
        with db.connect() as c:
            db.remove_game_from_collection(c, game["bgg_id"], cid)
        self.refresh_games()
        self.status(f'Removed "{game["name"]}" from {cname}.')

    # ---------- favorite / insert toggles ----------

    def on_toggle_favorite(self, game) -> None:
        new_val = not bool(game["is_favorite"])
        with db.connect() as c:
            db.set_favorite(c, game["bgg_id"], new_val)
        self.refresh_games()

    # ---------- plays tab ----------

    def _build_plays_tab(self) -> None:
        SP = self.SP
        frame = ttk.Frame(self.plays_tab, padding=SP["lg"])
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Plays", style="Section.TLabel").pack(anchor="w")
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(SP["xs"], SP["md"]))

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, SP["sm"]))

        # Primary action first; everything else is Ghost / Quiet
        ttk.Button(controls, text="Log Play…", command=lambda: self.on_log_play(
            {"name": self.plays_game_var.get()}
            if self.plays_game_var.get() != "All games" else None
        )).pack(side="left")
        ttk.Button(controls, text="Edit selected", style="Ghost.TButton",
                   command=self.on_edit_play).pack(side="left", padx=(SP["sm"], 0))

        ttk.Label(controls, text="FILTER BY GAME", style="Filter.TLabel"
                  ).pack(side="left", padx=(SP["md"], SP["xs"]))
        self.plays_game_var = tk.StringVar(value="All games")
        self.plays_game_cb = ttk.Combobox(
            controls, textvariable=self.plays_game_var, width=30, state="readonly",
        )
        self.plays_game_cb.pack(side="left")
        self.plays_game_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_plays())

        ttk.Button(controls, text="Clear filter", style="Quiet.TButton",
                   command=lambda: [self.plays_game_var.set("All games"), self.refresh_plays()]
                   ).pack(side="left", padx=(SP["xs"], 0))

        self._lb_showing = False
        self._lb_btn = ttk.Button(controls, text="🏆 Leaderboard", style="Ghost.TButton",
                                  command=self._toggle_leaderboard)
        self._lb_btn.pack(side="left", padx=(SP["sm"], 0))

        ttk.Button(controls, text="Delete selected", style="Danger.TButton",
                   command=self.on_delete_play).pack(side="right")

        # ── Play log pane ────────────────────────────────────────────────
        self._plays_pane = ttk.Frame(frame)
        self._plays_pane.pack(fill="both", expand=True)

        cols = ("game", "date", "players", "winner", "duration", "scores", "notes")
        self.plays_tree = ttk.Treeview(self._plays_pane, columns=cols, show="headings")
        self.plays_tree.heading("game",     text="Game")
        self.plays_tree.heading("date",     text="Date")
        self.plays_tree.heading("players",  text="Players")
        self.plays_tree.heading("winner",   text="Winner")
        self.plays_tree.heading("duration", text="Duration")
        self.plays_tree.heading("scores",   text="Scores")
        self.plays_tree.heading("notes",    text="Notes")
        self.plays_tree.column("game",     width=190)
        self.plays_tree.column("date",     width=100, anchor="center")
        self.plays_tree.column("players",  width=160)
        self.plays_tree.column("winner",   width=110, anchor="center")
        self.plays_tree.column("duration", width=80,  anchor="center")
        self.plays_tree.column("scores",   width=150, anchor="center")
        self.plays_tree.column("notes",    width=150)

        vsb = ttk.Scrollbar(self._plays_pane, orient="vertical",
                             command=self.plays_tree.yview)
        self.plays_tree.configure(yscrollcommand=vsb.set)
        self.plays_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.plays_tree.bind("<Double-1>", lambda *_: self.on_edit_play())

        # ── Leaderboard pane (hidden until toggled) ──────────────────────
        self._lb_pane = ttk.Frame(frame)
        # Not packed yet — shown on toggle

        lb_vsb2 = ttk.Scrollbar(self._lb_pane, orient="vertical")
        lb_vsb2.pack(side="right", fill="y")
        self._lb_canvas = tk.Canvas(self._lb_pane, bg=C_BG, highlightthickness=0,
                                    yscrollcommand=lb_vsb2.set)
        self._lb_canvas.pack(side="left", fill="both", expand=True)
        lb_vsb2.configure(command=self._lb_canvas.yview)
        self._lb_inner = ttk.Frame(self._lb_canvas)
        _lb_win = self._lb_canvas.create_window((0, 0), window=self._lb_inner, anchor="nw")
        self._lb_canvas.bind("<Configure>",
                             lambda e: self._lb_canvas.itemconfigure(_lb_win, width=e.width))
        self._lb_inner.bind("<Configure>",
                            lambda e: self._lb_canvas.configure(
                                scrollregion=self._lb_canvas.bbox("all")))
        # Ribbon image cache keyed by (rank, size) so different sizes don't collide
        if not hasattr(self, '_ribbon_photos'):
            self._ribbon_photos: dict = {}

    def _toggle_leaderboard(self) -> None:
        self._lb_showing = not self._lb_showing
        if self._lb_showing:
            self._plays_pane.pack_forget()
            self._lb_pane.pack(fill="both", expand=True)
            self._lb_btn.configure(text="📋 Play Log")
            self._refresh_leaderboard()
        else:
            self._lb_pane.pack_forget()
            self._plays_pane.pack(fill="both", expand=True)
            self._lb_btn.configure(text="🏆 Leaderboard")

    def _make_ribbon_photo(self, rank: int, size: int = 56) -> ImageTk.PhotoImage:
        """Render a circular rosette badge (no tails) for rank 0/1/2 using Pillow.

        The badge is a square image of *size* × *size* pixels containing:
          • Scalloped outer ring (alternating body/dark petals)
          • Solid backing disc
          • Gold ring border
          • Dark centre circle
          • Bold gold rank text
        """
        import math as _math
        COLORS = {
            0: ((26, 35, 126),  (13, 20, 87)),   # navy   1st
            1: ((183, 28, 28),  (127, 0, 0)),     # red    2nd
            2: ((27, 94, 32),   (0, 51, 0)),      # green  3rd
        }
        LABELS = {0: "1st", 1: "2nd", 2: "3rd"}
        GOLD = (240, 192, 80)
        body, dark = COLORS[rank]

        S  = 4            # oversample factor for AA
        W  = size
        w  = W * S
        cx = cy = w // 2

        PETALS    = 20
        OUTER_R   = int(w * 0.46)
        SCALLOP_R = int(w * 0.10)
        RING_R    = int(w * 0.36)
        INNER_R   = int(w * 0.29)

        img  = Image.new("RGBA", (w, w), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Scalloped petals
        for i in range(PETALS):
            a  = (i / PETALS) * 2 * _math.pi - _math.pi / 2
            sx = cx + OUTER_R * _math.cos(a)
            sy = cy + OUTER_R * _math.sin(a)
            c  = body if i % 2 == 0 else dark
            draw.ellipse([(sx - SCALLOP_R, sy - SCALLOP_R),
                          (sx + SCALLOP_R, sy + SCALLOP_R)], fill=c)

        # Solid backing disc (covers petal centres)
        draw.ellipse([(cx - RING_R - 2*S, cy - RING_R - 2*S),
                      (cx + RING_R + 2*S, cy + RING_R + 2*S)], fill=body)

        # Gold ring
        draw.ellipse([(cx - RING_R, cy - RING_R),
                      (cx + RING_R, cy + RING_R)],
                     outline=GOLD, width=max(3, S // 1))

        # Dark centre
        draw.ellipse([(cx - INNER_R, cy - INNER_R),
                      (cx + INNER_R, cy + INNER_R)], fill=dark)

        # Rank text
        label    = LABELS[rank]
        font_sz  = max(8, int(w * 0.22))
        font     = None
        for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(name, font_sz)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        # Account for font bearing so text is visually centred in the circle
        bbox = draw.textbbox((0, 0), label, font=font)
        tx   = cx - (bbox[0] + bbox[2]) // 2
        ty   = cy - (bbox[1] + bbox[3]) // 2
        draw.text((tx, ty), label, fill=GOLD, font=font)

        img = img.resize((W, W), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _refresh_leaderboard(self) -> None:
        for w in self._lb_inner.winfo_children():
            w.destroy()
        self._lb_canvas.yview_moveto(0)

        with db.connect() as c:
            rows = db.top_winners(c, limit=9999)

        if not rows:
            ttk.Label(self._lb_inner, text="No wins recorded yet.",
                      foreground=C_INK_500).pack(padx=20, pady=20)
            return

        max_wins = rows[0]["win_count"] if rows else 1
        ROW_COLORS = {0: "#fff8d6", 1: "#f2f2f2", 2: "#fdf0e6"}
        IMG_SIZE   = 44

        for i, r in enumerate(rows):
            bg = ROW_COLORS.get(i, C_BG)
            row = tk.Frame(self._lb_inner, bg=bg, padx=8, pady=4)
            row.pack(fill="x", padx=6, pady=2)

            # Ribbon image or plain number
            if i < 3:
                key = (i, IMG_SIZE)
                if key not in self._ribbon_photos:
                    self._ribbon_photos[key] = self._make_ribbon_photo(i, IMG_SIZE)
                ph = self._ribbon_photos[key]
                tk.Label(row, image=ph, bg=bg).pack(side="left", padx=(0, 8))
            else:
                tk.Label(row, text=str(i + 1), bg=bg,
                         font=("Segoe UI", 11, "bold"),
                         foreground=C_INK_500, width=4,
                         anchor="center").pack(side="left", padx=(0, 8))

            # Name
            tk.Label(row, text=r["winner"], bg=bg,
                     font=("Segoe UI", 11, "bold" if i < 3 else "normal"),
                     anchor="w").pack(side="left", expand=True, fill="x")

            # Win count + bar
            info = tk.Frame(row, bg=bg)
            info.pack(side="right", padx=(8, 0))
            wins = r["win_count"]
            tk.Label(info, text=f"{wins} win{'s' if wins != 1 else ''}",
                     bg=bg, font=("Segoe UI", 9),
                     foreground=C_INK_600).pack(anchor="e")
            bar_bg = tk.Frame(info, bg=C_LINE_200, height=5, width=120)
            bar_bg.pack(anchor="e")
            bar_bg.pack_propagate(False)
            pct = int((wins / max_wins) * 120)
            bar_colors = {0: "#d4a017", 1: "#8a9ba8", 2: "#a0522d"}
            fill_color = bar_colors.get(i, C_NAVY_900)
            tk.Frame(bar_bg, bg=fill_color, width=pct, height=5).place(x=0, y=0)

    def refresh_plays(self) -> None:
        self.plays_tree.delete(*self.plays_tree.get_children())

        # Refresh the game-filter combobox list.
        with db.connect() as c:
            games = db.list_games(c, owned_only=False)
            game_names = ["All games"] + [g["name"] for g in games]
            self._plays_game_map = {g["name"]: g["bgg_id"] for g in games}

        self.plays_game_cb["values"] = game_names
        if self.plays_game_var.get() not in game_names:
            self.plays_game_var.set("All games")

        chosen = self.plays_game_var.get()
        game_id = self._plays_game_map.get(chosen) if chosen != "All games" else None

        with db.connect() as c:
            rows = db.list_plays(c, game_id=game_id)

        for r in rows:
            dur = f"{r['duration_minutes']} min" if r["duration_minutes"] else ""
            self.plays_tree.insert(
                "", "end",
                iid=str(r["id"]),
                values=(
                    r["game_name"],
                    r["played_at"][:10],
                    r["player_names"] or "",
                    r["winner"] or "",
                    dur,
                    r["scores"] or "",
                    r["notes"] or "",
                ),
            )

        # Keep leaderboard in sync if it's currently visible
        if getattr(self, "_lb_showing", False):
            self._refresh_leaderboard()

    def on_log_play(self, game, *, play=None) -> None:
        """Open the Log Play dialog.

        game  — pre-select this game in the dropdown (or None for first game).
        play  — if given (a plays DB row), pre-fill all fields for editing.
        """
        with db.connect() as c:
            all_games = db.list_games(c, owned_only=False)
            all_users = db.list_users(c)
        if not all_games:
            messagebox.showinfo("No games", "Import your collection first.")
            return
        member_names = [f"{u['first_name']} {u['last_name']}" for u in all_users]

        editing = play is not None

        dialog = tk.Toplevel(self)
        dialog.title("Edit Play" if editing else "Log a Play")
        dialog.transient(self)
        dialog.resizable(False, False)

        pad = {"padx": 12, "pady": 4, "sticky": "w"}

        ttk.Label(dialog, text="Game:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, **pad)
        game_names = [g["name"] for g in all_games]
        game_id_map = {g["name"]: g["bgg_id"] for g in all_games}
        if editing:
            initial = next((g["name"] for g in all_games if g["bgg_id"] == play["game_id"]),
                           game_names[0] if game_names else "")
        else:
            initial = game["name"] if game else (game_names[0] if game_names else "")
        game_var = tk.StringVar(value=initial)
        game_cb = ttk.Combobox(dialog, textvariable=game_var, values=game_names,
                                state="readonly", width=28)
        game_cb.grid(row=0, column=1, sticky="w", padx=(12, 4), pady=4)

        def _find_on_bgg() -> None:
            """Search BGG for the typed/selected name, add result to DB, update list."""
            q = game_var.get().strip() or ""
            q = tk.simpledialog.askstring(
                "Search BGG", "Game name to search on BGG:", initialvalue=q, parent=dialog)
            if not q:
                return
            tok = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "")
            try:
                results = bgg.search_games(q, token=tok)
            except Exception as exc:
                messagebox.showerror("BGG search failed", str(exc), parent=dialog)
                return
            if not results:
                messagebox.showinfo("No results", f"No BGG results for '{q}'.", parent=dialog)
                return
            # Let user pick from results
            names = [f"{r[1]} ({r[2]})" if r[2] else r[1] for r in results[:15]]
            picked = tk.simpledialog.askinteger(
                "Pick a result",
                "\n".join(f"{i+1}. {n}" for i, n in enumerate(names)) +
                "\n\nEnter number:",
                minvalue=1, maxvalue=len(names), parent=dialog,
            )
            if not picked:
                return
            bgg_id, name, year = results[picked - 1]
            # Fetch full details and add with own=0 (play-log only)
            try:
                detail_list = bgg.fetch_things([bgg_id], token=tok)
                d = detail_list[0] if detail_list else None
            except Exception:
                d = None
            with db.connect() as c:
                db.upsert_game(c, {
                    "bgg_id": bgg_id, "name": name, "year": year,
                    "image_url": d.image_url if d else None,
                    "thumbnail_url": d.thumbnail_url if d else None,
                    "image_path": None,
                    "min_players": d.min_players if d else None,
                    "max_players": d.max_players if d else None,
                    "min_playtime": d.min_playtime if d else None,
                    "max_playtime": d.max_playtime if d else None,
                    "playing_time": d.playing_time if d else None,
                    "min_age": d.min_age if d else None,
                    "weight": d.weight if d else None,
                    "avg_rating": d.avg_rating if d else None,
                    "my_rating": None, "description": d.description if d else None,
                    "categories": ", ".join(d.categories) if d and d.categories else None,
                    "mechanics":  ", ".join(d.mechanics)  if d and d.mechanics  else None,
                    "designers":  ", ".join(d.designers)  if d and d.designers  else None,
                    "publishers": ", ".join(d.publishers) if d and d.publishers else None,
                    "best_players": d.best_players if d else None,
                    "my_comment": None, "own": 0, "last_synced": db.now_iso(),
                    "is_expansion": int(d.is_expansion) if d else 0,
                })
            # Refresh game list in combobox
            game_id_map[name] = bgg_id
            if name not in game_names:
                game_names.append(name)
                game_cb["values"] = sorted(game_names)
            game_var.set(name)

        ttk.Button(dialog, text="Find on BGG…", command=_find_on_bgg).grid(
            row=0, column=2, padx=(0, 12), pady=4, sticky="w")

        ttk.Label(dialog, text="Date played:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, **pad)
        date_val = play["played_at"][:10] if editing else datetime.now().strftime("%Y-%m-%d")
        date_var = tk.StringVar(value=date_val)
        _date_entry(dialog, date_var, width=14).grid(row=1, column=1, sticky="w", padx=12, pady=4)

        ttk.Label(dialog, text="Players (comma-separated):", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, **pad)
        players_var = tk.StringVar(value=play["player_names"] or "" if editing else "")
        _AutocompleteEntry(dialog, member_names, textvariable=players_var,
                           width=36).grid(row=2, column=1, **pad)

        ttk.Label(dialog, text="Winner:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, **pad)
        winner_var = tk.StringVar(value=play["winner"] or "" if editing else "")
        _AutocompleteEntry(dialog, ["All", "None"] + member_names,
                           textvariable=winner_var,
                           width=36).grid(row=3, column=1, **pad)

        ttk.Label(dialog, text="Duration (minutes):", font=("Segoe UI", 9, "bold")).grid(row=4, column=0, **pad)
        dur_val = str(play["duration_minutes"]) if editing and play["duration_minutes"] else ""
        dur_var = tk.StringVar(value=dur_val)
        ttk.Entry(dialog, textvariable=dur_var, width=8).grid(row=4, column=1, sticky="w", padx=12, pady=4)

        ttk.Label(dialog, text="Scores:", font=("Segoe UI", 9, "bold")).grid(row=5, column=0, **pad)
        scores_val = play["scores"] or "" if editing else ""
        scores_var = tk.StringVar(value=scores_val)
        scores_entry = ttk.Entry(dialog, textvariable=scores_var, width=36)
        scores_entry.grid(row=5, column=1, **pad)
        ttk.Label(dialog, text='e.g. "Alice: 45, Bob: 37" — highest score auto-sets winner',
                  foreground=C_INK_500, font=("Segoe UI", 7),
                  ).grid(row=6, column=1, sticky="w", padx=12, pady=(0, 2))

        def _auto_winner_from_scores(*_) -> None:
            """Parse scores field and fill winner with the highest scorer."""
            raw = scores_var.get()
            if not raw.strip():
                return
            best_name, best_score = "", None
            for part in raw.split(","):
                part = part.strip()
                if ":" in part:
                    name, _, val = part.partition(":")
                    try:
                        score = float(val.strip())
                        if best_score is None or score > best_score:
                            best_score, best_name = score, name.strip()
                    except ValueError:
                        pass
            if best_name:
                winner_var.set(best_name)
        scores_var.trace_add("write", _auto_winner_from_scores)

        ttk.Label(dialog, text="Notes (optional):", font=("Segoe UI", 9, "bold")).grid(row=7, column=0, **pad)
        notes_var = tk.StringVar(value=play["notes"] or "" if editing else "")
        ttk.Entry(dialog, textvariable=notes_var, width=36).grid(row=7, column=1, **pad)

        # ── optional BGG play sync ────────────────────────────────────────────
        # Only shown for new plays (not edits) when sync is enabled in Settings.
        bgg_username = self.settings.get("bgg_username", "").strip()
        bgg_post_var = tk.BooleanVar(value=False)
        bgg_pw_var   = tk.StringVar()
        _bgg_pw_label: Optional[ttk.Label] = None
        _bgg_pw_entry: Optional[ttk.Entry] = None

        if not editing and bgg_username and self.settings.get("bgg_sync_plays"):
            ttk.Separator(dialog, orient="horizontal").grid(
                row=8, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 2))

            ttk.Checkbutton(
                dialog,
                text=f"Also post this play to BGG  ({bgg_username})",
                variable=bgg_post_var,
            ).grid(row=9, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 2))

            _bgg_pw_label = ttk.Label(dialog, text="BGG password:")
            _bgg_pw_label.grid(row=10, column=0, **pad)
            _bgg_pw_entry = ttk.Entry(dialog, textvariable=bgg_pw_var, show="●", width=26)
            _bgg_pw_entry.grid(row=10, column=1, **pad)
            # Start hidden; reveal when checkbox is ticked
            _bgg_pw_label.grid_remove()
            _bgg_pw_entry.grid_remove()

            def _toggle_pw_row(*_) -> None:
                if bgg_post_var.get():
                    _bgg_pw_label.grid()
                    _bgg_pw_entry.grid()
                    _bgg_pw_entry.focus_set()
                else:
                    _bgg_pw_label.grid_remove()
                    _bgg_pw_entry.grid_remove()

            bgg_post_var.trace_add("write", _toggle_pw_row)
            btn_row_idx = 11
        else:
            btn_row_idx = 8

        def save_play() -> None:
            gid = game_id_map.get(game_var.get())
            if not gid:
                messagebox.showerror("Error", "Select a game.")
                return
            played = date_var.get().strip()
            if not played:
                messagebox.showerror("Error", "Enter a date.")
                return
            players = players_var.get().strip()
            notes   = notes_var.get().strip()
            scores  = scores_var.get().strip() or None
            try:
                dur = int(dur_var.get().strip()) if dur_var.get().strip() else None
            except ValueError:
                dur = None
            with db.connect() as c:
                if editing:
                    db.update_play(c, play["id"], gid, played,
                                   players,
                                   winner_var.get().strip(),
                                   notes,
                                   duration_minutes=dur,
                                   scores=scores)
                else:
                    db.log_play(c, gid, played,
                                players,
                                winner_var.get().strip(),
                                notes,
                                duration_minutes=dur,
                                scores=scores)
            # Capture BGG fields before destroying the dialog
            post_to_bgg = bgg_post_var.get()
            bgg_pw      = bgg_pw_var.get()
            dialog.destroy()
            self.refresh_plays()
            self.refresh_games()   # update play-count badges
            self.refresh_dashboard()
            action = "Updated" if editing else "Logged"
            self.status(f"{action} play for {game_var.get()}.")
            # Optionally sync to BGG — password is used once and never stored
            if not editing and post_to_bgg and bgg_username:
                if bgg_pw:
                    threading.Thread(
                        target=self._sync_play_to_bgg_bg,
                        args=(bgg_username, bgg_pw, gid, played, players, notes),
                        daemon=True,
                    ).start()
                else:
                    self.status("BGG sync skipped — no password entered.")

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=btn_row_idx, column=0, columnspan=2, pady=(8, 12), padx=12, sticky="e")
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Save Changes" if editing else "Save Play",
                   command=save_play).pack(side="left")

        dialog.grab_set()

    def on_edit_play(self) -> None:
        """Edit the currently selected play log entry."""
        sel = self.plays_tree.selection()
        if not sel:
            return
        play_id = int(sel[0])
        with db.connect() as c:
            play = db.get_play(c, play_id)
        if play:
            self.on_log_play(None, play=play)

    def on_delete_play(self) -> None:
        sel = self.plays_tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Delete play", "Delete this play log entry?"):
            return
        with db.connect() as c:
            db.delete_play(c, int(sel[0]))
        self.refresh_plays()
        self.refresh_games()
        self.refresh_dashboard()

    # ---------- details ----------

    def show_details(self, game) -> None:
        win = tk.Toplevel(self)
        win.title(game["name"])
        win.geometry("660x600")
        win.minsize(500, 440)
        win.transient(self)

        # ── fixed bottom section — always visible regardless of scroll position ─
        bottom = ttk.Frame(win)
        bottom.pack(side="bottom", fill="x")

        toggles = ttk.Frame(bottom, padding=(10, 6))
        toggles.pack(fill="x")

        insert_var = tk.BooleanVar(value=bool(game["has_insert"]))
        def on_insert_toggle() -> None:
            with db.connect() as c:
                db.set_insert(c, game["bgg_id"], insert_var.get())
            self.refresh_games()
        ttk.Checkbutton(
            toggles, text="📦 Has 3D printed insert",
            variable=insert_var, command=on_insert_toggle,
        ).pack(side="left")

        fav_var = tk.BooleanVar(value=bool(game["is_favorite"]))
        def on_fav_toggle() -> None:
            with db.connect() as c:
                db.set_favorite(c, game["bgg_id"], fav_var.get())
            self.refresh_games()
        ttk.Checkbutton(
            toggles, text="★ Favorite",
            variable=fav_var, command=on_fav_toggle,
        ).pack(side="left", padx=(20, 0))

        tk.Frame(bottom, bg=C_PALE, height=1).pack(fill="x")
        action_row = ttk.Frame(bottom, padding=(8, 6))
        action_row.pack(fill="x")
        ttk.Button(action_row, text="Log Play",
                   command=lambda: self.on_log_play(game)).pack(side="left", padx=(2, 4))
        ttk.Button(action_row, text="Set Image…",
                   command=lambda: self.on_set_image(game, refresh_callback=win.destroy)
                   ).pack(side="left")
        ttk.Button(action_row, text="Close",
                   command=win.destroy).pack(side="right", padx=(0, 2))

        # ── scrollable content area ────────────────────────────────────────────
        canvas = tk.Canvas(win, highlightthickness=0, bg=C_BG)
        vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        content = ttk.Frame(canvas, padding=10)
        cw_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        content.bind("<Configure>", _on_content_configure)

        def _on_canvas_configure(e):
            canvas.itemconfigure(cw_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            if win.winfo_exists():
                canvas.yview_scroll(int(-e.delta / 120), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        content.bind("<MouseWheel>", _on_mousewheel)

        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # ── image + title row ─────────────────────────────────────────────────
        top = ttk.Frame(content)
        top.pack(fill="x", pady=(0, 6))

        if game["image_path"] and Path(game["image_path"]).exists():
            try:
                img = Image.open(game["image_path"])
                img.thumbnail((200, 200))
                tk_img = ImageTk.PhotoImage(img)
                lbl = ttk.Label(top, image=tk_img)
                lbl.image = tk_img
                lbl.pack(side="left", padx=(0, 14))
            except (OSError, ValueError):
                pass

        info = ttk.Frame(top)
        info.pack(side="left", fill="both", expand=True)
        name_lbl = ttk.Label(info, text=game["name"], font=("Segoe UI", 13, "bold"))
        name_lbl.pack(anchor="w")
        if game["is_expansion"]:
            tk.Label(info, text="Expansion", bg=C_BLUE_050, fg=C_BLUE_800,
                     font=("Segoe UI", 8), padx=6, pady=2).pack(anchor="w", pady=(2, 0))
        if game["year"]:
            ttk.Label(info, text=f"Published {game['year']}", foreground=C_INK_600).pack(anchor="w")

        detail_rows: list[tuple[str, str]] = []
        detail_rows.append(("Players",     fmt_players(game["min_players"], game["max_players"])))
        detail_rows.append(("Playing time", fmt_time(game["min_playtime"], game["max_playtime"], game["playing_time"])))
        if game["min_age"]:
            detail_rows.append(("Min age",    f"{game['min_age']}+"))
        if game["best_players"]:
            detail_rows.append(("Best at",    f"{game['best_players']} players"))
        if game["weight"]:
            detail_rows.append(("Complexity", f"{game['weight']:.2f} / 5"))
        if game["avg_rating"]:
            detail_rows.append(("BGG rating", f"{game['avg_rating']:.2f}"))
        if game["my_rating"]:
            detail_rows.append(("My rating",  f"{game['my_rating']:.1f}"))
        if game["categories"]:
            detail_rows.append(("Categories", game["categories"]))
        if game["mechanics"]:
            detail_rows.append(("Mechanics",  game["mechanics"]))
        if game["designers"]:
            detail_rows.append(("Designers",  game["designers"]))
        if game["publishers"]:
            detail_rows.append(("Publishers", game["publishers"]))

        grid = ttk.Frame(info)
        grid.pack(anchor="w", pady=(8, 0), fill="x")
        for i, (k, v) in enumerate(detail_rows):
            ttk.Label(grid, text=f"{k}:", font=("Segoe UI", 9, "bold")).grid(
                row=i, column=0, sticky="nw", padx=(0, 8))
            ttk.Label(grid, text=v, wraplength=320, justify="left").grid(
                row=i, column=1, sticky="w")

        if game["tags"]:
            ttk.Label(content, text="Tags:",
                      font=("Segoe UI", 9, "bold"), padding=(0, 6, 0, 0)).pack(anchor="w")
            tag_row = tk.Frame(content, bg=C_BG)
            tag_row.pack(anchor="w", pady=(2, 4))
            for tag in [t.strip() for t in game["tags"].split(",") if t.strip()]:
                tk.Label(tag_row, text=tag, bg=C_BLUE_050, fg=C_BLUE_700,
                         font=("Segoe UI", 8), padx=6, pady=2, relief="flat",
                         ).pack(side="left", padx=(0, 4))

        if game["my_comment"]:
            ttk.Label(content, text="Your note:",
                      font=("Segoe UI", 9, "bold"), padding=(0, 6, 0, 0)).pack(anchor="w")
            ttk.Label(content, text=game["my_comment"],
                      wraplength=600, justify="left").pack(anchor="w")

        # ── play statistics ────────────────────────────────────────────────────
        with db.connect() as c:
            play_stats = db.game_play_stats(c, game["bgg_id"])

        if play_stats["count"] > 0:
            ttk.Separator(content, orient="horizontal").pack(fill="x", pady=(10, 6))
            ttk.Label(content, text="Play Statistics",
                      font=("Segoe UI", 10, "bold")).pack(anchor="w")
            stats_grid = ttk.Frame(content)
            stats_grid.pack(anchor="w", pady=(4, 0))

            stat_items = [
                ("Times played",  str(play_stats["count"])),
                ("Last played",   play_stats["last_played"]),
            ]
            if play_stats["avg_duration"]:
                stat_items.append(("Avg duration", f"{play_stats['avg_duration']} min"))
            for i, (k, v) in enumerate(stat_items):
                ttk.Label(stats_grid, text=f"{k}:", font=("Segoe UI", 9, "bold")).grid(
                    row=i, column=0, sticky="w", padx=(0, 8))
                ttk.Label(stats_grid, text=v).grid(row=i, column=1, sticky="w")

            if play_stats["win_counts"]:
                ttk.Label(content, text="Win counts:",
                          font=("Segoe UI", 9, "bold"), padding=(0, 6, 0, 2)).pack(anchor="w")
                wins_frame = ttk.Frame(content)
                wins_frame.pack(anchor="w")
                sorted_wins = sorted(play_stats["win_counts"].items(), key=lambda x: -x[1])
                for name, count in sorted_wins:
                    ttk.Label(wins_frame,
                              text=f"{'🏆' if count == sorted_wins[0][1] else '  '}  {name}: {count}",
                              font=("Segoe UI", 9)).pack(anchor="w")

        if game["description"]:
            ttk.Label(content, text="Description:",
                      font=("Segoe UI", 9, "bold"), padding=(0, 6, 0, 0)).pack(anchor="w")
            text_box = tk.Text(content, wrap="word", height=10,
                               font=("Segoe UI", 9), relief="flat",
                               bg=C_BG, bd=0)
            text_box.insert("1.0", game["description"])
            text_box.configure(state="disabled")
            text_box.pack(fill="x", pady=(0, 6))
            text_box.bind("<MouseWheel>", _on_mousewheel)

        win.grab_set()

    # ---------- set image ----------

    def on_set_image(self, game, refresh_callback=None) -> None:
        """Open a dialog to set or replace the cover image for a game.

        Accepts either a URL (e.g. right-click any box art on boardgamegeek.com
        → 'Copy image address') or a local file picked from disk.
        """
        bgg_id = game["bgg_id"]

        dialog = tk.Toplevel(self)
        dialog.title(f"Set Image — {game['name']}")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(bg=C_BG)

        # ── URL input ────────────────────────────────────────────────────────
        ttk.Label(dialog, text="Image URL:", padding=(14, 14, 14, 2)).pack(anchor="w")
        url_var = tk.StringVar()
        url_entry = ttk.Entry(dialog, textvariable=url_var, width=52)
        url_entry.pack(padx=14, pady=(0, 2))
        url_entry.focus_set()
        url_entry.bind("<Return>", lambda *_: confirm())

        tk.Label(
            dialog,
            text=(
                "💡  On boardgamegeek.com, right-click the game's box art\n"
                "    and choose 'Copy image address', then paste it above."
            ),
            bg=C_BG, fg=C_INK_600, font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        # ── divider ──────────────────────────────────────────────────────────
        div = ttk.Frame(dialog)
        div.pack(fill="x", padx=14, pady=(0, 8))
        ttk.Separator(div, orient="horizontal").pack(side="left", fill="x", expand=True)
        ttk.Label(div, text="  or  ", foreground=C_INK_500).pack(side="left")
        ttk.Separator(div, orient="horizontal").pack(side="left", fill="x", expand=True)

        # ── local file picker ────────────────────────────────────────────────
        ttk.Label(dialog, text="Local image file:", padding=(14, 0, 14, 2)).pack(anchor="w")
        file_row = ttk.Frame(dialog)
        file_row.pack(padx=14, fill="x")
        file_var = tk.StringVar()
        ttk.Entry(file_row, textvariable=file_var, width=40,
                  state="readonly").pack(side="left", fill="x", expand=True)

        def browse() -> None:
            path = filedialog.askopenfilename(
                title="Choose an image",
                filetypes=[
                    ("Image files", "*.jpg *.jpeg *.png *.gif *.webp *.bmp"),
                    ("All files", "*.*"),
                ],
            )
            if path:
                file_var.set(path)
                url_var.set("")   # clear URL if a file is chosen
                confirm()         # apply immediately and close

        ttk.Button(file_row, text="Browse…", command=browse).pack(side="left", padx=(6, 0))

        # ── confirm / cancel ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=14, pady=(12, 14), fill="x")

        def confirm() -> None:
            url   = url_var.get().strip()
            local = file_var.get().strip()

            if not url and not local:
                messagebox.showerror("No image", "Paste a URL or pick a file.", parent=dialog)
                return

            IMAGES_DIR.mkdir(parents=True, exist_ok=True)

            if url:
                ext  = Path(url.split("?", 1)[0]).suffix.lower() or ".jpg"
                dest = IMAGES_DIR / f"{bgg_id}{ext}"
                try:
                    bgg.download_image(url, dest)
                except Exception as exc:
                    messagebox.showerror("Download failed",
                                         f"Could not download image:\n{exc}", parent=dialog)
                    return
            else:
                ext  = Path(local).suffix.lower() or ".jpg"
                dest = IMAGES_DIR / f"{bgg_id}{ext}"
                try:
                    shutil.copy2(local, dest)
                except Exception as exc:
                    messagebox.showerror("Copy failed",
                                         f"Could not copy file:\n{exc}", parent=dialog)
                    return

            # Invalidate cached thumbnail so the new image is loaded
            old_path = game["image_path"] or ""
            self._image_cache.pop(old_path, None)

            with db.connect() as c:
                db.set_image_path(c, bgg_id, str(dest))
                if url:
                    c.execute("UPDATE games SET image_url = ? WHERE bgg_id = ?",
                              (url, bgg_id))

            dialog.destroy()
            self.refresh_games()
            if refresh_callback:
                refresh_callback()
            self.status(f"Image updated for {game['name']}.")

        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(btn_frame, text="Set Image", command=confirm).pack(side="right")
        dialog.bind("<Return>", lambda *_: confirm())
        dialog.grab_set()

    # ---------- BGG play history import ----------

    def on_import_bgg_plays(self) -> None:
        """Import play history from the user's BGG profile (skips duplicates)."""
        username = self.settings.get("bgg_username", "").strip()
        if not username:
            messagebox.showerror("Username missing",
                                 "Set your BGG username in Settings first.")
            return
        if not messagebox.askyesno(
            "Import BGG Plays",
            f"Import all plays logged on BGG for '{username}'?\n\n"
            "Plays for games not in your library will be skipped.\n"
            "Duplicate plays (same game + same date) will not be re-imported.",
        ):
            return
        self.status(f"Importing BGG plays for {username}…")
        token = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "")
        threading.Thread(
            target=self._import_bgg_plays_bg,
            args=(username, token),
            daemon=True,
        ).start()

    def _import_bgg_plays_bg(self, username: str, token: str) -> None:
        try:
            plays = bgg.fetch_plays(username, token=token, on_status=self._post_status)
            if not plays:
                self._post_status("No plays found on BGG.")
                return
            imported = skipped_game = skipped_dup = 0
            with db.connect() as c:
                # Build lookup: set of (game_id, date) already in DB
                existing = {
                    (r["game_id"], r["played_at"][:10])
                    for r in c.execute("SELECT game_id, played_at FROM plays").fetchall()
                }
                # Build set of known bgg_ids in library
                known_ids = {r["bgg_id"] for r in db.list_games(c, owned_only=False)}

                for p in plays:
                    if p["bgg_id"] not in known_ids:
                        skipped_game += 1
                        continue
                    key = (p["bgg_id"], p["played_at"])
                    if key in existing:
                        skipped_dup += 1
                        continue
                    db.log_play(c, p["bgg_id"], p["played_at"],
                                p["player_names"], "", p["notes"])
                    existing.add(key)
                    imported += 1

            self.after(0, self.refresh_plays)
            self.after(0, self.refresh_games)
            self.after(0, self.refresh_dashboard)
            msg = f"BGG plays imported: {imported} new"
            if skipped_dup:
                msg += f", {skipped_dup} already existed"
            if skipped_game:
                msg += f", {skipped_game} skipped (game not in library)"
            self._post_status(msg)
        except Exception as exc:
            self._post_status(f"BGG play import failed: {exc}")

    # ---------- CSV exports ----------

    def on_export_plays_csv(self) -> None:
        """Export the full play log to a CSV file chosen by the user."""
        import csv as _csv
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="plays_export.csv",
            title="Export Plays to CSV",
        )
        if not path:
            return
        with db.connect() as c:
            rows = db.list_plays(c)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = _csv.writer(f)
                writer.writerow(["Game", "Date", "Players", "Winner",
                                 "Duration (min)", "Scores", "Notes"])
                for r in rows:
                    writer.writerow([
                        r["game_name"],
                        r["played_at"][:10],
                        r["player_names"] or "",
                        r["winner"] or "",
                        r["duration_minutes"] or "",
                        r["scores"] or "",
                        r["notes"] or "",
                    ])
            self.status(f"Exported {len(rows)} plays to {Path(path).name}")
        except OSError as e:
            messagebox.showerror("Export failed", str(e))

    def on_export_loans_csv(self) -> None:
        """Export the full loan history to a CSV file chosen by the user."""
        import csv as _csv
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="loans_export.csv",
            title="Export Loan History to CSV",
        )
        if not path:
            return
        with db.connect() as c:
            rows = db.loan_history(c)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = _csv.writer(f)
                writer.writerow(["Game", "Member", "Checked Out", "Due Date",
                                 "Returned", "Notes"])
                for r in rows:
                    writer.writerow([
                        r["game_name"],
                        f"{r['first_name']} {r['last_name']}".strip(),
                        r["checked_out_at"][:10],
                        r["due_date"] or "",
                        r["returned_at"][:10] if r["returned_at"] else "",
                        r["notes"] or "",
                    ])
            self.status(f"Exported {len(rows)} loan records to {Path(path).name}")
        except OSError as e:
            messagebox.showerror("Export failed", str(e))

    # ---------- export / import library ----------

    def on_export_data(self) -> None:
        """Export the entire library (database + images + settings) to a ZIP file."""
        import zipfile as _zf

        default_name = f"BoardGameLibrary-{datetime.now():%Y%m%d-%H%M%S}.zip"
        dest_path = filedialog.asksaveasfilename(
            title="Export Board Game Library",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
            initialfile=default_name,
        )
        if not dest_path:
            return

        def _bg():
            try:
                imgs = list(IMAGES_DIR.iterdir()) if IMAGES_DIR.exists() else []
                total = len(imgs)
                with _zf.ZipFile(dest_path, "w", _zf.ZIP_DEFLATED) as zf:
                    # Sentinel so we can validate on import
                    zf.writestr("boardgamelibrary.marker", "Board Game Library Backup v1")
                    if DB_PATH.exists():
                        zf.write(DB_PATH, "library.db")
                    if CONFIG_PATH.exists():
                        zf.write(CONFIG_PATH, "settings.json")
                    for i, img in enumerate(imgs):
                        if img.is_file():
                            self._post_status(f"Exporting image {i + 1}/{total}…")
                            zf.write(img, f"images/{img.name}")

                p = dest_path
                self.after(0, lambda: [
                    self.status(f"Exported to {Path(p).name}."),
                    messagebox.showinfo(
                        "Export complete",
                        f"Library exported successfully:\n{p}",
                    ),
                ])
            except Exception as exc:
                e = str(exc)
                self.after(0, lambda: [
                    messagebox.showerror("Export failed", f"Could not export library:\n{e}"),
                    self.status("Export failed."),
                ])

        self.status("Exporting library…")
        threading.Thread(target=_bg, daemon=True).start()

    def on_import_data(self) -> None:
        """Import a library ZIP created by Export Library…, replacing all local data."""
        import zipfile as _zf

        src_path = filedialog.askopenfilename(
            title="Import Board Game Library",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
        )
        if not src_path:
            return

        # Validate the ZIP before asking for confirmation
        try:
            with _zf.ZipFile(src_path, "r") as zf:
                if "boardgamelibrary.marker" not in zf.namelist():
                    messagebox.showerror(
                        "Invalid file",
                        "This doesn't appear to be a Board Game Library backup.\n"
                        "Use File → Export Library… to create one.",
                    )
                    return
        except Exception as exc:
            messagebox.showerror("Invalid file", f"Could not open the file:\n{exc}")
            return

        if not messagebox.askyesno(
            "Import Library",
            "This will REPLACE all current data:\n\n"
            "  • Games, members, loans and play history\n"
            "  • Downloaded images\n"
            "  • Settings (username)\n\n"
            "This cannot be undone. Continue?",
            icon="warning",
        ):
            return

        def _bg():
            try:
                with _zf.ZipFile(src_path, "r") as zf:
                    entries = [n for n in zf.namelist() if n != "boardgamelibrary.marker"]
                    total = len(entries)
                    for i, name in enumerate(entries):
                        self._post_status(f"Importing {i + 1}/{total}: {Path(name).name}…")
                        dest = DATA_DIR / name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(name))

                # Remap absolute image_path values to this machine's IMAGES_DIR.
                # The source machine may have a different APPDATA / home directory.
                with db.connect() as c:
                    rows = c.execute(
                        "SELECT bgg_id, image_path FROM games WHERE image_path IS NOT NULL"
                    ).fetchall()
                    for row in rows:
                        local = IMAGES_DIR / Path(row["image_path"]).name
                        if local.exists():
                            c.execute(
                                "UPDATE games SET image_path = ? WHERE bgg_id = ?",
                                (str(local), row["bgg_id"]),
                            )
                        else:
                            c.execute(
                                "UPDATE games SET image_path = NULL WHERE bgg_id = ?",
                                (row["bgg_id"],),
                            )

                def _finish():
                    self._image_cache.clear()
                    self._placeholder_img = None
                    self.settings = config.load()
                    db.init_db()          # apply any pending migrations
                    self.refresh_all()
                    self.status("Library imported successfully.")
                    messagebox.showinfo(
                        "Import complete",
                        "Library imported successfully — all data has been refreshed.",
                    )

                self.after(0, _finish)
            except Exception as exc:
                e = str(exc)
                self.after(0, lambda: [
                    messagebox.showerror("Import failed", f"Could not import library:\n{e}"),
                    self.status("Import failed."),
                ])

        self.status("Importing library…")
        threading.Thread(target=_bg, daemon=True).start()

    def on_export_for_mobile(self) -> None:
        """Export members, plays, loans and customisations as a JSON file
        that can be imported on the mobile app via Dashboard → Import Backup."""
        import json as _json

        default_name = f"bgl-backup-{datetime.now():%Y-%m-%d}.json"
        dest_path = filedialog.asksaveasfilename(
            title="Export for Mobile",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not dest_path:
            return

        with db.connect() as c:
            members = [dict(r) for r in c.execute(
                "SELECT * FROM users ORDER BY id").fetchall()]

            plays = [dict(r) for r in c.execute(
                """SELECT plays.*, games.name AS game_name
                   FROM plays
                   LEFT JOIN games ON games.bgg_id = plays.game_id
                   ORDER BY plays.played_at DESC""").fetchall()]

            loans = [dict(r) for r in c.execute(
                """SELECT loans.*, games.name AS game_name,
                          users.first_name, users.last_name
                   FROM loans
                   LEFT JOIN games ON games.bgg_id = loans.game_id
                   LEFT JOIN users ON users.id = loans.user_id
                   ORDER BY loans.checked_out_at DESC""").fetchall()]

            customisations = [dict(r) for r in c.execute(
                """SELECT bgg_id, name, tags, is_favorite, has_insert,
                          my_comment, my_rating, manual_fields
                   FROM games
                   WHERE tags IS NOT NULL OR is_favorite = 1 OR has_insert = 1
                      OR my_comment IS NOT NULL OR my_rating IS NOT NULL
                   """).fetchall()]

        payload = {
            "version": 1,
            "exported_at": db.now_iso(),
            "members": members,
            "plays": plays,
            "loans": loans,
            "customisations": customisations,
        }

        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                _json.dump(payload, f, indent=2, default=str)
            n_m = len(members)
            n_p = len(plays)
            n_l = len(loans)
            p = dest_path
            self.status(f"Exported for mobile: {Path(p).name}")
            messagebox.showinfo(
                "Export complete",
                f"Saved: {p}\n\n"
                f"  {n_m} member{'s' if n_m != 1 else ''}\n"
                f"  {n_p} play record{'s' if n_p != 1 else ''}\n"
                f"  {n_l} loan record{'s' if n_l != 1 else ''}\n\n"
                "Transfer this file to your phone, then open the\n"
                "mobile app → Dashboard → Import Backup.",
            )
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    # ---------- refresh ----------

    def refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_games()
        self.refresh_members()
        self.refresh_history()
        self.refresh_plays()


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        # Declare the process DPI-aware BEFORE Tk starts, so Windows renders the
        # window (and its taskbar icon) at native resolution instead of drawing
        # at 96 DPI and bitmap-stretching it (blurry) on high-DPI displays.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()    # system (older OS)
            except Exception:
                pass
        # Explicit AppUserModelID so the taskbar shows *our* icon (not pythonw).
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Ballewcifer.BoardGameLibrary")
        except Exception:
            pass
    App().mainloop()
