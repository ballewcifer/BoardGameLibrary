"""Board Game Library — Tkinter GUI."""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

import bgg
import config
import db
from paths import DATA_DIR, DB_PATH, CONFIG_PATH, IMAGES_DIR
from version import __version__ as APP_VERSION

THUMB_SIZE = (140, 140)
PLACEHOLDER_BG = "#dcdcdc"
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

# ── colour palette ────────────────────────────────────────────────────────────
C_NAVY    = "#1a3a5c"   # dark navy  – header bar, treeview headings
C_BLUE    = "#2471a3"   # medium blue – buttons, active tab
C_SKY     = "#5dade2"   # lighter blue – hover / accent highlights
C_PALE    = "#eaf4fd"   # very light blue – filter bar background
C_BG      = "#f4f7fb"   # near-white with a blue tint – main background
C_WHITE   = "#ffffff"
C_TEXT    = "#1c2833"   # near-black body text
C_GOLD    = "#d4a017"   # darker gold for best-at labels (replaces #b8860b)


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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Board Game Library")
        self.geometry("1280x720")
        self.minsize(900, 520)

        db.init_db()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = config.load()
        self._image_cache: dict[str, ImageTk.PhotoImage] = {}
        self._placeholder_img: Optional[ImageTk.PhotoImage] = None
        self._search_after_id: Optional[str] = None
        self._view_mode: str = self.settings.get("view_mode", "cards")
        self._sort_col: Optional[str] = None
        self._sort_rev: bool = False
        self._table_games: list = []
        self._lazy_generation: int = 0   # incremented each refresh to cancel stale loaders

        self._apply_style()
        self.configure(bg=C_BG)
        self._build_menubar()
        self._build_header()
        self._build_toolbar()
        self._build_tabs()
        self._build_status_bar()

        self.refresh_all()

        # Show first-run setup guide if this is a fresh install
        if not self.settings.get("welcome_shown"):
            self.after(300, self._show_welcome_dialog)

        # Auto-sync with BGG on startup if a username is configured
        username = self.settings.get("bgg_username", "").strip()
        token    = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "").strip()
        if username and token:
            self.after(1500, lambda: self._auto_sync_bgg(username, token))

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
                 bg=C_BG, fg="#888", font=("Segoe UI", 9, "italic")).pack(anchor="w")
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
            bg=C_NAVY, fg=C_WHITE, activebackground=C_BLUE, activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=14, pady=5, cursor="hand2",
            command=close,
        ).pack(side="right")

        win.grab_set()

    # ---------- style / theme ----------

    def _apply_style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")   # clam supports colour overrides on Windows

        s.configure(".",
            background=C_BG, foreground=C_TEXT,
            font=("Segoe UI", 9))

        # Frames
        s.configure("TFrame",     background=C_BG)
        s.configure("TLabelframe", background=C_BG)
        s.configure("TLabelframe.Label", background=C_BG, foreground=C_NAVY,
                    font=("Segoe UI", 9, "bold"))

        # Labels
        s.configure("TLabel", background=C_BG, foreground=C_TEXT)

        # Buttons – blue pill style
        s.configure("TButton",
            background=C_BLUE, foreground=C_WHITE,
            font=("Segoe UI", 9, "bold"),
            padding=[8, 4], relief="flat", borderwidth=0)
        s.map("TButton",
            background=[("active", C_NAVY), ("pressed", C_NAVY)],
            foreground=[("active", C_WHITE)])

        # Notebook tabs
        s.configure("TNotebook", background=C_NAVY, borderwidth=0)
        s.configure("TNotebook.Tab",
            background=C_BLUE, foreground=C_WHITE,
            font=("Segoe UI", 9, "bold"),
            padding=[14, 6])
        s.map("TNotebook.Tab",
            background=[("selected", C_NAVY), ("active", C_SKY)],
            foreground=[("selected", C_WHITE), ("active", C_WHITE)])

        # Entry / Combobox
        s.configure("TEntry",
            fieldbackground=C_WHITE, foreground=C_TEXT,
            insertcolor=C_NAVY, bordercolor=C_BLUE)
        s.configure("TCombobox",
            fieldbackground=C_WHITE, foreground=C_TEXT,
            selectbackground=C_BLUE, selectforeground=C_WHITE)

        # Checkbutton / Radiobutton
        s.configure("TCheckbutton", background=C_PALE, foreground=C_TEXT)
        s.map("TCheckbutton", background=[("active", C_PALE)])
        s.configure("TRadiobutton", background=C_BG, foreground=C_TEXT)
        s.map("TRadiobutton", background=[("active", C_BG)])

        # Treeview
        s.configure("Treeview",
            background=C_WHITE, fieldbackground=C_WHITE,
            foreground=C_TEXT, rowheight=24)
        s.configure("Treeview.Heading",
            background=C_NAVY, foreground=C_WHITE,
            font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview.Heading",
            background=[("active", C_BLUE)])
        s.map("Treeview",
            background=[("selected", C_BLUE)],
            foreground=[("selected", C_WHITE)])

        # Scrollbar
        s.configure("TScrollbar",
            background=C_PALE, troughcolor=C_BG,
            arrowcolor=C_NAVY, borderwidth=0)

        # Separator
        s.configure("TSeparator", background=C_BLUE)

        # Filter-bar specific frame tag
        s.configure("Filter.TFrame", background=C_PALE)
        s.configure("Filter.TLabel", background=C_PALE, foreground=C_NAVY,
                    font=("Segoe UI", 9, "bold"))
        s.configure("Filter.TCheckbutton", background=C_PALE, foreground=C_TEXT)
        s.map("Filter.TCheckbutton", background=[("active", C_PALE)])

        # Status bar
        s.configure("Status.TFrame", background=C_NAVY)
        s.configure("Status.TLabel", background=C_NAVY, foreground=C_WHITE,
                    font=("Segoe UI", 8))

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
        file_menu.add_separator()
        file_menu.add_command(label="Export Library…",        command=self.on_export_data)
        file_menu.add_command(label="Import Library…",        command=self.on_import_data)
        file_menu.add_separator()
        file_menu.add_command(label="Settings…",             command=self.on_open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",                   command=self.destroy)

        # ── Library ───────────────────────────────────────────────────────────
        lib_menu = tk.Menu(menubar)
        menubar.add_cascade(label="Library", menu=lib_menu)
        lib_menu.add_command(label="Add Game…", command=self.on_add_game)

        # ── Help ──────────────────────────────────────────────────────────────
        help_menu = tk.Menu(menubar)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About…", command=self.on_about)

        self.config(menu=menubar)

    def _build_header(self) -> None:
        """Navy banner at the very top with the app title."""
        hdr = tk.Frame(self, bg=C_NAVY, pady=6)
        hdr.pack(side="top", fill="x")

        tk.Label(
            hdr, text="  \U0001f3b2  Board Game Library",
            bg=C_NAVY, fg=C_WHITE,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(8, 0))

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side="top", fill="x")

        # ── search ────────────────────────────────────────────────────────────
        ttk.Label(bar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        def _on_search_changed(*_):
            if self._search_after_id:
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(250, self.refresh_games)
        self.search_var.trace_add("write", _on_search_changed)
        entry = ttk.Entry(bar, textvariable=self.search_var, width=30)
        entry.pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Clear", command=lambda: self.search_var.set("")).pack(side="left", padx=(4, 0))

        # ── view toggle ───────────────────────────────────────────────────────
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="View:").pack(side="left")

        def _view_btn(text, mode):
            active = self._view_mode == mode
            btn = tk.Button(
                bar, text=text,
                bg=C_NAVY if active else C_WHITE,
                fg=C_WHITE if active else C_NAVY,
                activebackground=C_BLUE, activeforeground=C_WHITE,
                relief="solid", bd=1,
                font=("Segoe UI", 9, "bold"),
                padx=10, pady=3, cursor="hand2",
                command=lambda m=mode: self._set_view(m),
            )
            btn.pack(side="left", padx=(4, 0))
            return btn

        self._btn_cards = _view_btn("⊞  Cards", "cards")
        self._btn_table = _view_btn("≡  Table", "table")

        # --- filter bar (second row, light-blue background) ---
        fbar = ttk.Frame(self, style="Filter.TFrame", padding=(8, 4, 8, 6))
        fbar.pack(side="top", fill="x")

        def flabel(text): return ttk.Label(fbar, text=text, style="Filter.TLabel")
        def fcheck(text, var, cmd): return ttk.Checkbutton(fbar, text=text, variable=var,
                                                           command=cmd, style="Filter.TCheckbutton")

        # ── left-aligned filter widgets ───────────────────────────────────────
        flabel("Players:").pack(side="left")
        self.players_var = tk.StringVar(value="Any")
        players_cb = ttk.Combobox(
            fbar, textvariable=self.players_var, width=6, state="readonly",
            values=["Any", "1", "2", "3", "4", "5", "6", "7", "8+"],
        )
        players_cb.pack(side="left", padx=(4, 4))
        players_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.exact_players_var = tk.BooleanVar(value=False)
        fcheck("Exact only", self.exact_players_var, self.refresh_games).pack(side="left", padx=(0, 8))

        flabel("Best at:").pack(side="left")
        self.best_at_var = tk.StringVar(value="Any")
        best_at_cb = ttk.Combobox(
            fbar, textvariable=self.best_at_var, width=6, state="readonly",
            values=["Any", "1", "2", "3", "4", "5", "6", "7", "8+"],
        )
        best_at_cb.pack(side="left", padx=(4, 12))
        best_at_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        flabel("Play time:").pack(side="left")
        self.time_var = tk.StringVar(value="Any")
        time_cb = ttk.Combobox(
            fbar, textvariable=self.time_var, width=12, state="readonly",
            values=["Any", "≤ 30 min", "31–60 min", "61–90 min", "91–120 min", "121+ min"],
        )
        time_cb.pack(side="left", padx=(4, 12))
        time_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        flabel("Complexity:").pack(side="left")
        self.weight_var = tk.StringVar(value="Any")
        weight_cb = ttk.Combobox(
            fbar, textvariable=self.weight_var, width=12, state="readonly",
            values=["Any", "Light (1–2)", "Medium (2–3)", "Heavy (3–5)"],
        )
        weight_cb.pack(side="left", padx=(4, 12))
        weight_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        flabel("Status:").pack(side="left")
        self.status_filter_var = tk.StringVar(value="Any")
        status_cb = ttk.Combobox(
            fbar, textvariable=self.status_filter_var, width=12, state="readonly",
            values=["Any", "Available", "Checked out"],
        )
        status_cb.pack(side="left", padx=(4, 12))
        status_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_games())

        self.favorites_var = tk.BooleanVar(value=False)
        fcheck("Favorites only", self.favorites_var, self.refresh_games).pack(side="left", padx=(0, 12))

        ttk.Button(fbar, text="Reset filters", command=self._reset_filters).pack(side="left")

        # ── game count — left-aligned after Reset filters, not floating right ──
        ttk.Separator(fbar, orient="vertical").pack(side="left", fill="y", padx=10)
        self._count_label = ttk.Label(fbar, text="", style="Filter.TLabel")
        self._count_label.pack(side="left")

    def _build_tabs(self) -> None:
        self.nb = ttk.Notebook(self)
        self.nb.pack(side="top", fill="both", expand=True)

        self.games_tab = ttk.Frame(self.nb)
        self.members_tab = ttk.Frame(self.nb)
        self.history_tab = ttk.Frame(self.nb)
        self.plays_tab = ttk.Frame(self.nb)

        self.nb.add(self.games_tab, text="Games")
        self.nb.add(self.members_tab, text="Members")
        self.nb.add(self.history_tab, text="History")
        self.nb.add(self.plays_tab, text="Plays")

        self._build_games_tab()
        self._build_members_tab()
        self._build_history_tab()
        self._build_plays_tab()

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready.")
        bar = ttk.Frame(self, style="Status.TFrame")
        bar.pack(side="bottom", fill="x")
        ttk.Label(
            bar, textvariable=self.status_var, anchor="w",
            style="Status.TLabel", padding=(10, 4),
        ).pack(side="left", fill="x", expand=True)

    # ---------- games tab ----------

    def _build_games_tab(self) -> None:
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

        self.games_canvas = tk.Canvas(self._card_frame, highlightthickness=0, background="#f5f5f5",
                                      yscrollcommand=scroll.set)
        scroll.configure(command=self.games_canvas.yview)
        self.games_canvas.pack(side="left", fill="both", expand=True)

        self.games_inner = ttk.Frame(self.games_canvas)
        self.games_window_id = self.games_canvas.create_window((0, 0), window=self.games_inner, anchor="nw")
        self.games_inner.bind("<Configure>", lambda e: self.games_canvas.configure(scrollregion=self.games_canvas.bbox("all")))
        self.games_canvas.bind("<Configure>", self._reflow_games)
        self.games_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

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
            ("year",    "Year",         54, "center"),
            ("players", "Players",      72, "center"),
            ("time",    "Time",         84, "center"),
            ("weight",  "Complexity",   84, "center"),
            ("rating",  "BGG ★",        62, "center"),
            ("best",    "Best At",      72, "center"),
            ("status",  "Status",      140, "center"),
            ("plays",   "Plays",        50, "center"),
        ]
        # All columns use stretch=False so Tkinter never overrides a manual
        # column resize.  We auto-size the name column ourselves below.
        self._fixed_col_ids = [c for c, *_ in col_defs if c != "name"]
        for cid, heading, width, anchor in col_defs:
            self.games_tree.heading(cid, text=heading,
                                    command=lambda c=cid: self._sort_table(c))
            self.games_tree.column(cid, width=width, anchor=anchor, stretch=False,
                                   minwidth=30 if cid != "name" else 80)

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.games_tree.yview)
        self.games_tree.configure(yscrollcommand=vsb.set)
        self.games_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Auto-resize the name column when the *window* width changes.
        # We skip Configure events that come from column drags (those don't
        # change the Treeview's overall width) by checking event.width.
        self._tree_last_width: int = 0

        def _on_tree_configure(event: tk.Event) -> None:
            w = event.width
            if w == self._tree_last_width:
                return           # column drag or unrelated event — leave it alone
            self._tree_last_width = w
            fixed = sum(self.games_tree.column(c, "width") for c in self._fixed_col_ids)
            name_w = max(80, w - fixed - 4)   # 4 = border fudge
            self.games_tree.column("name", width=name_w)

        self.games_tree.bind("<Configure>", _on_tree_configure)

        self.games_tree.bind("<Double-1>",  self._on_table_double_click)
        self.games_tree.bind("<Return>",    self._on_table_return)
        self.games_tree.bind("<Button-3>",  self._on_table_right_click)

        # Row colour tags
        self.games_tree.tag_configure("out",      background="#fff8e1")
        self.games_tree.tag_configure("favorite", foreground=C_GOLD)

    def _set_view(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self.settings["view_mode"] = mode
        config.save(self.settings)
        # Update button colours
        for btn, m in ((self._btn_cards, "cards"), (self._btn_table, "table")):
            active = (m == mode)
            btn.configure(bg=C_NAVY if active else C_WHITE,
                           fg=C_WHITE if active else C_NAVY)
        if mode == "table":
            self._card_frame.pack_forget()
            self._table_frame.pack(fill="both", expand=True)
        else:
            self._table_frame.pack_forget()
            self._card_frame.pack(fill="both", expand=True)
        self.refresh_games()

    def _on_mousewheel(self, event: tk.Event) -> None:
        # Only scroll the card canvas when the Games tab is active and in card view
        if self.nb.index(self.nb.select()) != 0:
            return
        if self._view_mode == "cards":
            self.games_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _reflow_games(self, event: tk.Event) -> None:
        self.games_canvas.itemconfigure(self.games_window_id, width=event.width)
        self._layout_cards(event.width)

    def _layout_cards(self, container_width: int) -> None:
        if not self._cards:
            return
        card_w = 180
        gap = 12
        cols = max(1, (container_width - gap) // (card_w + gap))
        rows_used = 0
        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            rows_used = max(rows_used, r + 1)
            card.grid(row=r, column=c, padx=gap // 2, pady=gap // 2, sticky="nsew")
        for c in range(cols):
            self.games_inner.grid_columnconfigure(c, weight=1)
        # Give each row uniform weight so cards in the same row share a height
        for r in range(rows_used):
            self.games_inner.grid_rowconfigure(r, weight=0)

    def _reset_filters(self) -> None:
        self.players_var.set("Any")
        self.exact_players_var.set(False)
        self.best_at_var.set("Any")
        self.time_var.set("Any")
        self.weight_var.set("Any")
        self.status_filter_var.set("Any")
        self.favorites_var.set(False)
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

            # --- availability filter ---
            if status_val == "Available" and g["bgg_id"] in open_loans:
                continue
            if status_val == "Checked out" and g["bgg_id"] not in open_loans:
                continue

            # --- favorites filter ---
            if self.favorites_var.get() and not g["is_favorite"]:
                continue

            out.append(g)
        return out

    def refresh_games(self) -> None:
        with db.connect() as c:
            games = db.list_games(c, self.search_var.get().strip())
            total_count = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
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

        games = self._apply_filters(list(games), open_loans)

        # Update count label
        shown = len(games)
        if self._filters_active():
            self._count_label.configure(text=f"{shown} of {total_count} games")
        else:
            self._count_label.configure(text=f"{total_count} game{'s' if total_count != 1 else ''}")

        if self._view_mode == "table":
            self._refresh_table_view(games, open_loans, play_counts)
        else:
            self._refresh_card_view(games, open_loans, play_counts)

    def _filters_active(self) -> bool:
        return (
            any(v != "Any" for v in [self.players_var.get(), self.best_at_var.get(),
                                      self.time_var.get(), self.weight_var.get(),
                                      self.status_filter_var.get()])
            or self.exact_players_var.get()
            or self.favorites_var.get()
            or bool(self.search_var.get())
        )

    def _refresh_card_view(self, games, open_loans, play_counts) -> None:
        # Hide the canvas window during the destroy+create loop so the
        # geometry manager doesn't recalculate layout on every widget change.
        self.games_canvas.itemconfigure(self.games_window_id, state="hidden")

        for card in self._cards:
            card.destroy()
        self._cards.clear()

        if not games:
            msg = (
                "No games match your filters."
                if self._filters_active()
                else 'No games yet. Use File → Import from BGG… or Import collection CSV… to get started.'
            )
            empty = ttk.Label(self.games_inner, text=msg, padding=20)
            empty.grid(row=0, column=0)
            self._cards.append(empty)
            self.games_canvas.itemconfigure(self.games_window_id, state="normal")
            return

        lazy_queue: list[tuple] = []
        for game in games:
            card, lazy = self._build_card(game, open_loans.get(game["bgg_id"]), play_counts)
            self._cards.append(card)
            lazy_queue.append(lazy)

        self._layout_cards(self.games_canvas.winfo_width())
        self.games_canvas.itemconfigure(self.games_window_id, state="normal")

        # Kick off lazy image loading and rebuild the A-Z bar
        self._lazy_generation += 1
        threading.Thread(
            target=self._lazy_load_images,
            args=(lazy_queue, self._lazy_generation),
            daemon=True,
        ).start()
        self.after(80, lambda g=games: self._update_alpha_bar(g))

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

            # If already cached (from a previous render) just reuse it
            if path in self._image_cache:
                tk_img = self._image_cache[path]
                self.after(0, lambda c=canvas, i=img_id, im=tk_img:
                           self._apply_lazy_image(c, i, im))
                continue

            # Disk I/O + PIL resize in the background
            try:
                pil_img = Image.open(path)
                pil_img.thumbnail(THUMB_SIZE)
            except (OSError, ValueError):
                continue

            self.after(0, lambda c=canvas, i=img_id, p=pil_img, pa=path:
                       self._apply_lazy_image_from_pil(c, i, p, pa))

    def _apply_lazy_image(self, canvas: tk.Canvas, img_id: int,
                          tk_img: ImageTk.PhotoImage) -> None:
        """Main thread: update a card's canvas with an already-created PhotoImage."""
        try:
            if canvas.winfo_exists():
                canvas.itemconfigure(img_id, image=tk_img)
                canvas._card_img_ref = tk_img
        except tk.TclError:
            pass

    def _apply_lazy_image_from_pil(self, canvas: tk.Canvas, img_id: int,
                                    pil_img: "Image.Image", path: str) -> None:
        """Main thread: convert a PIL Image → PhotoImage, cache it, show it."""
        try:
            if not canvas.winfo_exists():
                return
            tk_img = ImageTk.PhotoImage(pil_img)
            self._image_cache[path] = tk_img
            canvas.itemconfigure(img_id, image=tk_img)
            canvas._card_img_ref = tk_img
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
                fg=C_BLUE if active else "#ccc",
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

            self.games_tree.insert(
                "", "end", iid=str(bgg_id),
                tags=tags,
                values=(
                    "★" if g["is_favorite"] else "",
                    "\U0001f4e6" if g["has_insert"] else "",
                    g["name"],
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
        menu.add_separator()
        menu.add_command(label="Delete Game…", command=lambda: self.on_delete_game(game))
        menu.tk_popup(event.x_root, event.y_root)

    def _build_card(self, game, loan, play_counts: dict) -> tuple:
        out_to = None
        if loan is not None:
            out_to = f"{loan['first_name']} {loan['last_name']}".strip()

        bgg_id = game["bgg_id"]
        is_fav = bool(game["is_favorite"])
        has_insert = bool(game["has_insert"])
        n_plays = play_counts.get(bgg_id, 0)

        card = ttk.Frame(self.games_inner, padding=8, relief="solid", borderwidth=1)
        card.configure(width=180)

        # --- header row: star sits right-aligned above the image ---
        #     Using tk.Frame (not ttk) so bg=C_BG matches perfectly.
        header = tk.Frame(card, bg=C_BG)
        header.pack(fill="x")
        star_lbl = tk.Label(
            header,
            text="★" if is_fav else "☆",
            font=("Segoe UI", 13),
            fg="#f5a623" if is_fav else "#aaa",
            bg=C_BG, cursor="hand2",
        )
        star_lbl.pack(side="right", padx=(0, 0), pady=(0, 0))
        star_lbl.bind("<Button-1>", lambda e, g=game: self.on_toggle_favorite(g))

        # --- image canvas (fixed size, centred in card) ---
        _CW, _CH = THUMB_SIZE[0], THUMB_SIZE[1]  # 140 × 140
        img_canvas = tk.Canvas(
            card, width=_CW, height=_CH,
            bg=C_BG, highlightthickness=0, bd=0,
        )
        img_canvas.pack(anchor="center")  # centred in card, not stretched

        _img_id = img_canvas.create_image(_CW // 2, _CH // 2, anchor="center")
        # Always start with a placeholder; the lazy loader will fill in the real image
        ph = self._get_placeholder()
        img_canvas.itemconfigure(_img_id, image=ph)
        img_canvas._card_img_ref = ph

        # --- name + year ---
        ttk.Label(
            card,
            text=_shorten(game["name"]),
            wraplength=160,
            justify="center",
            font=("Segoe UI", 9, "bold"),
        ).pack(pady=(6, 0))

        year_text = f"({game['year']})" if game["year"] else ""
        ttk.Label(card, text=year_text, foreground="#666").pack()

        # --- player count + time ---
        info = (
            f"\U0001f465 {fmt_players(game['min_players'], game['max_players'])}   "
            f"⏱ {fmt_time(game['min_playtime'], game['max_playtime'], game['playing_time'])}"
        )
        ttk.Label(card, text=info, foreground="#444").pack(pady=(4, 0))

        # --- best-at line (always present so all cards are the same height) ---
        ttk.Label(
            card,
            text=f"★ Best at {game['best_players']}" if game["best_players"] else "",
            foreground="#b8860b",
            font=("Segoe UI", 8),
        ).pack()

        # --- badges row: insert + play count ---
        badge_row = ttk.Frame(card)
        badge_row.pack(pady=(3, 0))
        if has_insert:
            tk.Label(
                badge_row, text="\U0001f4e6 Insert",
                bg="#d0e8ff", fg="#1a5276",
                font=("Segoe UI", 8), padx=4, pady=1,
            ).pack(side="left", padx=(0, 4))
        if n_plays:
            plays_lbl = tk.Label(
                badge_row, text=f"\U0001f3ae {n_plays} play{'s' if n_plays != 1 else ''}",
                bg="#e8f5e9", fg="#2e7d32",
                font=("Segoe UI", 8), padx=4, pady=1,
            )
            plays_lbl.pack(side="left")

        # --- availability status ---
        if out_to:
            tk.Label(
                card, text=f"Out: {out_to}",
                bg="#f0c674", font=("Segoe UI", 8), padx=6, pady=2,
            ).pack(pady=(6, 0), fill="x")
        else:
            tk.Label(
                card, text="Available",
                bg="#b5d6a7", font=("Segoe UI", 8), padx=6, pady=2,
            ).pack(pady=(6, 0), fill="x")

        # --- action buttons (2 per row keeps them wide enough to read) ---
        btn_row = ttk.Frame(card)
        btn_row.pack(pady=(6, 0), fill="x")
        if out_to:
            ttk.Button(btn_row, text="Check In",
                       command=lambda g=game: self.on_check_in(g)).pack(side="left", expand=True, fill="x")
        else:
            ttk.Button(btn_row, text="Check Out",
                       command=lambda g=game: self.on_check_out(g)).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_row, text="Details",
                   command=lambda g=game: self.show_details(g)).pack(side="left", expand=True, fill="x", padx=(2, 0))

        btn_row2 = ttk.Frame(card)
        btn_row2.pack(pady=(3, 0), fill="x")
        ttk.Button(btn_row2, text="Edit",
                   command=lambda g=game: self.on_edit_game(g)).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_row2, text="Log Play",
                   command=lambda g=game: self.on_log_play(g)).pack(side="left", expand=True, fill="x", padx=(2, 0))

        # Right-click anywhere on the card for the full action menu (incl. Delete)
        def _card_right_click(event, g=game):
            self._show_card_context_menu(event, g)
        for widget in (card, header, img_canvas, btn_row, btn_row2):
            widget.bind("<Button-3>", _card_right_click)

        return card, (img_canvas, _img_id, game)

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
        frame = ttk.Frame(self.members_tab, padding=8)
        frame.pack(fill="both", expand=True)

        form = ttk.Frame(frame)
        form.pack(fill="x")
        ttk.Label(form, text="First name:").pack(side="left")
        self.first_name_var = tk.StringVar()
        first_entry = ttk.Entry(form, textvariable=self.first_name_var, width=18)
        first_entry.pack(side="left", padx=(4, 8))
        first_entry.bind("<Return>", lambda *_: self.on_add_member())
        ttk.Label(form, text="Last name:").pack(side="left")
        self.last_name_var = tk.StringVar()
        last_entry = ttk.Entry(form, textvariable=self.last_name_var, width=18)
        last_entry.pack(side="left", padx=(4, 8))
        last_entry.bind("<Return>", lambda *_: self.on_add_member())
        ttk.Button(form, text="Add member", command=self.on_add_member).pack(side="left")
        ttk.Button(form, text="Remove selected", command=self.on_delete_member).pack(side="left", padx=(8, 0))

        cols = ("name", "out", "since")
        self.members_tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.members_tree.heading("name", text="Name")
        self.members_tree.heading("out", text="Currently out")
        self.members_tree.heading("since", text="Member since")
        self.members_tree.column("name", width=240)
        self.members_tree.column("out", width=120, anchor="center")
        self.members_tree.column("since", width=160, anchor="center")
        self.members_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.members_tree.bind("<Double-1>", self._on_member_double_click)

        tip = ttk.Label(frame, text="Double-click a member to see their checkout history.",
                        foreground="#888", font=("Segoe UI", 8))
        tip.pack(anchor="w", pady=(4, 0))

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
        win.geometry("640x420")
        win.minsize(500, 300)
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
        tree.column("game",     width=240)
        tree.column("out",      width=140, anchor="center")
        tree.column("returned", width=140, anchor="center")
        tree.column("notes",    width=150)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        # Colour open loans amber
        tree.tag_configure("open", background="#fff8e1")

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
            foreground="#555",
            font=("Segoe UI", 8),
        )
        summary.pack(anchor="w", padx=10)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(4, 10))
        win.grab_set()

    # ---------- history tab ----------

    def _build_history_tab(self) -> None:
        frame = ttk.Frame(self.history_tab, padding=8)
        frame.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="Filter:").pack(side="left")
        self.history_filter = tk.StringVar(value="all")
        ttk.Radiobutton(controls, text="All", variable=self.history_filter, value="all", command=self.refresh_history).pack(side="left", padx=4)
        ttk.Radiobutton(controls, text="Currently out", variable=self.history_filter, value="open", command=self.refresh_history).pack(side="left", padx=4)
        ttk.Radiobutton(controls, text="Returned", variable=self.history_filter, value="closed", command=self.refresh_history).pack(side="left", padx=4)

        cols = ("game", "member", "out", "returned", "notes")
        self.history_tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.history_tree.heading("game", text="Game")
        self.history_tree.heading("member", text="Member")
        self.history_tree.heading("out", text="Checked out")
        self.history_tree.heading("returned", text="Returned")
        self.history_tree.heading("notes", text="Notes")
        self.history_tree.column("game", width=260)
        self.history_tree.column("member", width=180)
        self.history_tree.column("out", width=140, anchor="center")
        self.history_tree.column("returned", width=140, anchor="center")
        self.history_tree.column("notes", width=200)
        self.history_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.history_tree.bind("<Double-1>",  self._on_history_double_click)
        self.history_tree.bind("<Button-3>",  self._on_history_right_click)

        tip2 = ttk.Label(frame, text="Double-click or right-click a row to edit check-out / check-in details.",
                         foreground="#888", font=("Segoe UI", 8))
        tip2.pack(anchor="w", pady=(4, 0))

    def refresh_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        with db.connect() as c:
            rows = db.loan_history(c)
        f = self.history_filter.get()
        for r in rows:
            if f == "open" and r["returned_at"] is not None:
                continue
            if f == "closed" and r["returned_at"] is None:
                continue
            self.history_tree.insert(
                "",
                "end",
                iid=str(r["id"]),   # loan primary key so we can edit the row
                values=(
                    r["game_name"],
                    f"{r['first_name']} {r['last_name']}",
                    fmt_date(r["checked_out_at"]),
                    fmt_date(r["returned_at"]) or "⬤ still out",
                    r["notes"] or "",
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

        ttk.Label(frame, text="Checked out (ISO date/time):").grid(row=2, column=0, **lpad)
        out_var = tk.StringVar(value=(loan["checked_out_at"] or "")[:19])
        ttk.Entry(frame, textvariable=out_var, width=22).grid(row=2, column=1, sticky="w")

        ttk.Label(frame, text="Returned (leave blank if still out):").grid(row=3, column=0, **lpad)
        ret_var = tk.StringVar(value=(loan["returned_at"] or "")[:19])
        ttk.Entry(frame, textvariable=ret_var, width=22).grid(row=3, column=1, sticky="w")

        ttk.Label(frame, text="Notes:").grid(row=4, column=0, **lpad)
        notes_var = tk.StringVar(value=loan["notes"] or "")
        ttk.Entry(frame, textvariable=notes_var, width=32).grid(row=4, column=1, sticky="w")

        err_var = tk.StringVar()
        ttk.Label(frame, textvariable=err_var, foreground="red",
                  font=("Segoe UI", 8)).grid(row=5, column=0, columnspan=2, sticky="w")

        def save() -> None:
            out_val   = out_var.get().strip()   or None
            ret_val   = ret_var.get().strip()   or None
            notes_val = notes_var.get().strip() or None
            if not out_val:
                err_var.set("Checked-out date is required.")
                return
            with db.connect() as c:
                c.execute(
                    "UPDATE loans SET checked_out_at=?, returned_at=?, notes=? WHERE id=?",
                    (out_val, ret_val, notes_val, loan_id),
                )
            win.destroy()
            self.refresh_history()
            self.refresh_members()
            self.refresh_games()
            self.status("Loan record updated.")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
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
            frame,
            text="Used by File → Import from BGG…",
            foreground="#888",
        ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        # ── BGG password ──────────────────────────────────────────────────────
        ttk.Label(frame, text="BGG password:").grid(row=2, column=0, sticky="w", pady=4)
        password_var = tk.StringVar(value=self.settings.get("bgg_password", ""))
        pw_entry = ttk.Entry(frame, textvariable=password_var, width=32, show="●")
        pw_entry.grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            frame,
            text="Required for syncing plays to BGG",
            foreground="#888",
        ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        # ── sync plays toggle ─────────────────────────────────────────────────
        sync_var = tk.BooleanVar(value=bool(self.settings.get("bgg_sync_plays", False)))
        sync_cb = ttk.Checkbutton(
            frame,
            text="Post plays to BGG when logging a play",
            variable=sync_var,
        )
        sync_cb.grid(row=4, column=0, columnspan=2, sticky="w", padx=(0, 0), pady=(0, 12))

        def save() -> None:
            self.settings["bgg_username"] = username_var.get().strip()
            self.settings["bgg_password"] = password_var.get()   # keep as-is (may be empty)
            self.settings["bgg_sync_plays"] = sync_var.get()
            config.save(self.settings)
            self.status("Settings saved.")
            win.destroy()

        # ── danger zone ───────────────────────────────────────────────────────
        tk.Frame(frame, bg=C_PALE, height=1).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        tk.Label(
            frame, text="Danger zone",
            bg=C_BG, fg="#b71c1c",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=6, column=0, sticky="w", pady=(8, 4))

        tk.Button(
            frame, text="Clear collection…",
            bg="#b71c1c", fg=C_WHITE,
            activebackground="#7f0000", activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=12, pady=4, cursor="hand2",
            command=self.on_clear_collection,
        ).grid(row=7, column=0, sticky="w")
        tk.Label(
            frame,
            text="Removes all games, images, play logs,\nand loan history. Members are kept.",
            bg=C_BG, fg="#888",
            font=("Segoe UI", 8), justify="left",
        ).grid(row=7, column=1, sticky="w", padx=(12, 0))

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Save", command=save).pack(side="left")

        frame.columnconfigure(1, weight=1)
        win.grab_set()

    def on_clear_collection(self) -> None:
        if not messagebox.askyesno(
            "Clear collection",
            "This will permanently delete ALL games, play logs, and loan history.\n\n"
            "Members and settings will be kept.\n\n"
            "Are you sure?",
            icon="warning",
        ):
            return
        # Second confirmation — hard to click through by accident
        if not messagebox.askyesno(
            "Are you sure?",
            "This cannot be undone. Delete the entire collection?",
            icon="warning",
        ):
            return
        with db.connect() as c:
            c.execute("DELETE FROM plays")
            c.execute("DELETE FROM loans")
            c.execute("DELETE FROM games")
        # Remove all cached images
        try:
            if IMAGES_DIR.exists():
                shutil.rmtree(IMAGES_DIR)
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._image_cache.clear()
        self._placeholder_img = None
        self.refresh_all()
        self.status("Collection cleared.")

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
        self.update_idletasks()

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
        """Show a dialog asking for a BGG username, then import the collection."""
        username = self.settings.get("bgg_username", "").strip()

        dialog = tk.Toplevel(self)
        dialog.title("Import from BGG")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(bg=C_BG)
        dialog.lift()
        dialog.focus_force()

        ttk.Label(dialog, text="BGG username:", padding=(16, 14, 16, 2)).pack(anchor="w")
        uname_var = tk.StringVar(value=username)
        entry = ttk.Entry(dialog, textvariable=uname_var, width=34)
        entry.pack(padx=16, pady=(0, 8))
        entry.focus_set()
        entry.select_range(0, "end")

        tk.Label(
            dialog,
            text="Your BGG collection must be set to public.",
            bg=C_BG, fg="#555", font=("Segoe UI", 9),
            padx=16,
        ).pack(anchor="w")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=16, pady=(8, 14), fill="x")

        def do_import() -> None:
            uname = uname_var.get().strip()
            if not uname:
                messagebox.showerror("Username required", "Enter your BGG username.", parent=dialog)
                return
            tok = bgg.BGG_APP_TOKEN or self.settings.get("bgg_token", "").strip()
            if not tok:
                messagebox.showerror(
                    "Not configured",
                    "The app's BGG API token has not been set yet.\n"
                    "Please contact the library administrator.",
                    parent=dialog,
                )
                return
            self.settings["bgg_username"] = uname
            config.save(self.settings)
            if hasattr(self, "username_var"):
                self.username_var.set(uname)
            dialog.destroy()
            self.status(f"Importing collection for {uname}…")
            threading.Thread(
                target=self._import_from_username_bg,
                args=(uname, tok),
                daemon=True,
            ).start()

        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(btn_frame, text="Import", command=do_import).pack(side="right")
        dialog.bind("<Return>", lambda *_: do_import())
        dialog.grab_set()

    def _import_from_username_bg(self, username: str, token: str) -> None:
        try:
            games = bgg.import_from_username(username, token=token, on_status=self._post_status)
            if not games:
                self.after(0, lambda: messagebox.showinfo(
                    "Nothing found",
                    f"No owned games found for '{username}'.\n"
                    "Check the username is correct and your BGG collection is set to public.",
                ))
                self._post_status("Import: nothing found.")
                return
            self._save_games_to_db(games)
            self.after(0, self.refresh_games)
            self._post_status(f"Imported {len(games)} games. Downloading images…")
            self._download_thumbnails_bg(games)
        except PermissionError as exc:
            self.after(0, lambda err=str(exc): messagebox.showerror(
                "Token rejected",
                f"BGG rejected the API token:\n{err}\n\n"
                "The built-in token may have expired. Contact the library administrator.",
            ))
            self._post_status("Import failed: token rejected.")
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
            self._save_games_to_db(games)
            self.after(0, self.refresh_games)
            n = len(games)
            self._post_status(f"BGG auto-sync complete: {n} game{'s' if n != 1 else ''} updated.")
            # Download any missing images in the background
            needs_img = [g for g in games
                         if not g.thumbnail_url and not g.image_url]
            if any(not g.thumbnail_url and not g.image_url for g in games):
                pass  # nothing to do
            self._download_thumbnails_bg(games)
        except Exception as exc:
            self._post_status(f"BGG auto-sync failed: {exc}")

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

            self._save_games_to_db(list(by_id.values()))
            self._post_status("Saved to database. Downloading thumbnails...")
            self._download_thumbnails_bg(list(by_id.values()))
            self.after(0, self.refresh_games)
            self._post_status(f"Sync complete: {len(by_id)} games.")
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
        ttk.Label(dlg, textvariable=status_var, foreground="#555",
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
                    found = bgg.search_games(q)
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
        comment_var = row_entry(7, "Comment",           d.my_comment)

        ttk.Label(dlg, text="Description",
                  font=("Segoe UI", 9, "bold")).grid(row=8, column=0, **lpad)
        desc_box = tk.Text(dlg, width=38, height=5, font=("Segoe UI", 9),
                           wrap="word", relief="solid", bd=1)
        desc_box.grid(row=8, column=1, padx=(4, 12), pady=3, sticky="we")
        if d.description:
            desc_box.insert("1.0", d.description)

        err_var = tk.StringVar()
        ttk.Label(dlg, textvariable=err_var, foreground="red",
                  font=("Segoe UI", 8)).grid(
            row=9, column=0, columnspan=2, padx=12, sticky="w")

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
                "best_players":  d.best_players,
                "my_comment":    comment_var.get().strip() or None,
                "own":           1,
                "last_synced":   db.now_iso(),
            }
            with db.connect() as c:
                db.upsert_game(c, game_row)

            dlg.destroy()
            self.refresh_games()
            verb = "Added" if is_new else "Updated"
            self.status(f"{verb} \"{name}\".")

        btn_row = ttk.Frame(dlg, padding=(12, 4, 12, 12))
        btn_row.grid(row=10, column=0, columnspan=2, sticky="e")
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Save Game" if is_new else "Save Changes",
                   command=save).pack(side="left")

        dlg.columnconfigure(1, weight=1)
        dlg.grab_set()

    def _fetch_and_cache_images_bg(self, bgg_ids: list[int]) -> None:
        """Download box-art for every game that is missing an image.

        Image URL priority:
          1. image_url / thumbnail_url already stored in the DB (from CSV import)
          2. BGG HTML page scrape via get_bgg_page_data (browser UA, no token)
             — also collects Best-at data in the same request.
        The /xmlapi2/thing endpoint is no longer used here as it now
        requires a Bearer token.
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

            need_image = not (row and row["image_path"] and Path(row["image_path"]).exists())

            # ── image download ────────────────────────────────────────────────
            if need_image:
                # 1. Use URL already in the DB (populated from CSV import)
                url = (
                    (row["image_url"]     if row else None)
                    or (row["thumbnail_url"] if row else None)
                )
                if url:
                    ext  = Path(url.split("?", 1)[0]).suffix or ".jpg"
                    dest = IMAGES_DIR / f"{bgg_id}{ext}"
                    try:
                        bgg.download_image(url, dest)
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
        msg = f"Done: {img_ok}/{total} images downloaded."
        if img_failed:
            msg += f"  {img_failed} failed — last error: {last_error}"
        self._post_status(msg)

    def _post_status(self, msg: str) -> None:
        self.after(0, self.status, msg)

    def _save_games_to_db(self, games: list[bgg.GameDetails]) -> None:
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
                # Don't clobber image_path on a re-sync.
                existing = db.get_game(c, g.bgg_id)
                if existing and existing["image_path"]:
                    row["image_path"] = existing["image_path"]
                db.upsert_game(c, row)

    def _download_thumbnails_bg(self, games: list[bgg.GameDetails]) -> None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        ok = 0
        failed = 0
        last_error = ""
        for g in games:
            url = g.thumbnail_url or g.image_url
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
                with db.connect() as c:
                    db.set_image_path(c, g.bgg_id, str(dest))
                ok += 1
            except Exception as exc:
                failed += 1
                last_error = str(exc)
        self.after(0, self.refresh_games)
        msg = f"Thumbnails downloaded: {ok} ok."
        if failed:
            msg += f" {failed} failed — last error: {last_error}"
        self._post_status(msg)

    # ---------- check in / out ----------

    def on_check_out(self, game) -> None:
        with db.connect() as c:
            users = db.list_users(c)
        if not users:
            messagebox.showinfo("No members", "Add a member on the Members tab first.")
            self.nb.select(self.members_tab)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Check Out")
        dialog.transient(self)
        dialog.resizable(False, False)
        ttk.Label(dialog, text=f"Check out \"{game['name']}\" to:").grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6), sticky="w")

        names = [f"{u['first_name']} {u['last_name']}" for u in users]
        member_var = tk.StringVar(value=names[0])
        ttk.Combobox(dialog, textvariable=member_var, values=names, state="readonly", width=30).grid(row=1, column=0, columnspan=2, padx=12, sticky="we")

        ttk.Label(dialog, text="Notes (optional):").grid(row=2, column=0, columnspan=2, padx=12, pady=(8, 0), sticky="w")
        notes_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=notes_var, width=34).grid(row=3, column=0, columnspan=2, padx=12, pady=(2, 8), sticky="we")

        def confirm() -> None:
            idx = names.index(member_var.get())
            user_id = users[idx]["id"]
            try:
                with db.connect() as c:
                    db.check_out(c, game["bgg_id"], user_id, notes_var.get().strip())
            except ValueError as e:
                messagebox.showerror("Cannot check out", str(e))
                return
            dialog.destroy()
            self.refresh_games()
            self.refresh_members()
            self.refresh_history()
            self.status(f"Checked out \"{game['name']}\" to {member_var.get()}.")

        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(row=4, column=0, padx=12, pady=(0, 12), sticky="we")
        ttk.Button(dialog, text="Check Out", command=confirm).grid(row=4, column=1, padx=12, pady=(0, 12), sticky="we")
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
        self.status(f"Checked in \"{game['name']}\".")

    # ---------- delete game ----------

    def on_delete_game(self, game) -> None:
        name = game["name"]
        if not messagebox.askyesno(
            "Delete Game",
            f'Remove "{name}" from your library?\n\n'
            "This will also delete all check-out history and play logs for this game.",
            icon="warning",
        ):
            return
        with db.connect() as c:
            db.delete_game(c, game["bgg_id"])
        self.refresh_games()
        self.refresh_history()
        self.status(f'Deleted "{name}".')

    # ---------- favorite / insert toggles ----------

    def on_toggle_favorite(self, game) -> None:
        new_val = not bool(game["is_favorite"])
        with db.connect() as c:
            db.set_favorite(c, game["bgg_id"], new_val)
        self.refresh_games()

    # ---------- plays tab ----------

    def _build_plays_tab(self) -> None:
        frame = ttk.Frame(self.plays_tab, padding=8)
        frame.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 6))

        ttk.Button(controls, text="Log Play...", command=lambda: self.on_log_play(None)).pack(side="left")
        ttk.Button(controls, text="Edit selected",
                   command=self.on_edit_play).pack(side="left", padx=(6, 0))

        ttk.Label(controls, text="  Filter by game:").pack(side="left")
        self.plays_game_var = tk.StringVar(value="All games")
        self.plays_game_cb = ttk.Combobox(
            controls, textvariable=self.plays_game_var, width=30, state="readonly",
        )
        self.plays_game_cb.pack(side="left", padx=(4, 0))
        self.plays_game_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh_plays())

        ttk.Button(controls, text="Clear filter",
                   command=lambda: [self.plays_game_var.set("All games"), self.refresh_plays()]
                   ).pack(side="left", padx=(4, 0))

        ttk.Button(controls, text="Delete selected",
                   command=self.on_delete_play).pack(side="right")

        cols = ("game", "date", "players", "winner", "notes")
        self.plays_tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.plays_tree.heading("game", text="Game")
        self.plays_tree.heading("date", text="Date played")
        self.plays_tree.heading("players", text="Players")
        self.plays_tree.heading("winner", text="Winner")
        self.plays_tree.heading("notes", text="Notes")
        self.plays_tree.column("game", width=220)
        self.plays_tree.column("date", width=130, anchor="center")
        self.plays_tree.column("players", width=200)
        self.plays_tree.column("winner", width=140)
        self.plays_tree.column("notes", width=180)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.plays_tree.yview)
        self.plays_tree.configure(yscrollcommand=vsb.set)
        self.plays_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.plays_tree.bind("<Double-1>", lambda *_: self.on_edit_play())

    def refresh_plays(self) -> None:
        self.plays_tree.delete(*self.plays_tree.get_children())

        # Refresh the game-filter combobox list.
        with db.connect() as c:
            games = db.list_games(c)
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
            self.plays_tree.insert(
                "", "end",
                iid=str(r["id"]),
                values=(
                    r["game_name"],
                    r["played_at"][:10],        # date part only
                    r["player_names"] or "",
                    r["winner"] or "",
                    r["notes"] or "",
                ),
            )

    def on_log_play(self, game, *, play=None) -> None:
        """Open the Log Play dialog.

        game  — pre-select this game in the dropdown (or None for first game).
        play  — if given (a plays DB row), pre-fill all fields for editing.
        """
        with db.connect() as c:
            all_games = db.list_games(c)
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
                           game_names[0])
        else:
            initial = game["name"] if game else game_names[0]
        game_var = tk.StringVar(value=initial)
        ttk.Combobox(dialog, textvariable=game_var, values=game_names,
                     state="readonly", width=34).grid(row=0, column=1, **pad)

        ttk.Label(dialog, text="Date played:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, **pad)
        date_val = play["played_at"][:10] if editing else datetime.now().strftime("%Y-%m-%d")
        date_var = tk.StringVar(value=date_val)
        ttk.Entry(dialog, textvariable=date_var, width=14).grid(row=1, column=1, sticky="w", padx=12, pady=4)

        ttk.Label(dialog, text="Players (comma-separated):", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, **pad)
        players_var = tk.StringVar(value=play["player_names"] or "" if editing else "")
        _AutocompleteEntry(dialog, member_names, textvariable=players_var,
                           width=36).grid(row=2, column=1, **pad)

        ttk.Label(dialog, text="Winner:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, **pad)
        winner_var = tk.StringVar(value=play["winner"] or "" if editing else "")
        _AutocompleteEntry(dialog, member_names, textvariable=winner_var,
                           width=36).grid(row=3, column=1, **pad)

        ttk.Label(dialog, text="Notes (optional):", font=("Segoe UI", 9, "bold")).grid(row=4, column=0, **pad)
        notes_var = tk.StringVar(value=play["notes"] or "" if editing else "")
        ttk.Entry(dialog, textvariable=notes_var, width=36).grid(row=4, column=1, **pad)

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
            with db.connect() as c:
                if editing:
                    db.update_play(c, play["id"], gid, played,
                                   players,
                                   winner_var.get().strip(),
                                   notes)
                else:
                    db.log_play(c, gid, played,
                                players,
                                winner_var.get().strip(),
                                notes)
            dialog.destroy()
            self.refresh_plays()
            self.refresh_games()   # update play-count badges
            action = "Updated" if editing else "Logged"
            self.status(f"{action} play for {game_var.get()}.")
            # Optionally sync to BGG (new plays only, not edits)
            if not editing and self.settings.get("bgg_sync_plays"):
                uname = self.settings.get("bgg_username", "").strip()
                pwd   = self.settings.get("bgg_password", "")
                if uname and pwd:
                    threading.Thread(
                        target=self._sync_play_to_bgg_bg,
                        args=(uname, pwd, gid, played, players, notes),
                        daemon=True,
                    ).start()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(8, 12), padx=12, sticky="e")
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
        ttk.Label(info, text=game["name"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        if game["year"]:
            ttk.Label(info, text=f"Published {game['year']}", foreground="#666").pack(anchor="w")

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

        if game["my_comment"]:
            ttk.Label(content, text="Your note:",
                      font=("Segoe UI", 9, "bold"), padding=(0, 6, 0, 0)).pack(anchor="w")
            ttk.Label(content, text=game["my_comment"],
                      wraplength=600, justify="left").pack(anchor="w")

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

        tk.Label(
            dialog,
            text=(
                "💡  On boardgamegeek.com, right-click the game's box art\n"
                "    and choose 'Copy image address', then paste it above."
            ),
            bg=C_BG, fg="#555", font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        # ── divider ──────────────────────────────────────────────────────────
        div = ttk.Frame(dialog)
        div.pack(fill="x", padx=14, pady=(0, 8))
        ttk.Separator(div, orient="horizontal").pack(side="left", fill="x", expand=True)
        ttk.Label(div, text="  or  ", foreground="#888").pack(side="left")
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

    # ---------- refresh ----------

    def refresh_all(self) -> None:
        self.refresh_games()
        self.refresh_members()
        self.refresh_history()
        self.refresh_plays()


if __name__ == "__main__":
    App().mainloop()
