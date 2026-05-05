"""Board Game Library — Tkinter GUI."""
from __future__ import annotations

import re
import shutil
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
from paths import IMAGES_DIR
from version import __version__ as APP_VERSION

THUMB_SIZE = (140, 140)
PLACEHOLDER_BG = "#dcdcdc"
APP_CREATED   = "April 30, 2026"
APP_AUTHOR    = "Ballewcifer"

# ── colour palette ────────────────────────────────────────────────────────────
C_NAVY    = "#1a3a5c"   # dark navy  – header bar, treeview headings
C_BLUE    = "#2471a3"   # medium blue – buttons, active tab
C_SKY     = "#5dade2"   # lighter blue – hover / accent highlights
C_PALE    = "#eaf4fd"   # very light blue – filter bar background
C_BG      = "#f4f7fb"   # near-white with a blue tint – main background
C_WHITE   = "#ffffff"
C_TEXT    = "#1c2833"   # near-black body text
C_GOLD    = "#d4a017"   # darker gold for best-at labels (replaces #b8860b)


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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Board Game Library")
        self.geometry("1100x720")
        self.minsize(820, 520)

        db.init_db()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = config.load()
        self._image_cache: dict[str, ImageTk.PhotoImage] = {}
        self._placeholder_img: Optional[ImageTk.PhotoImage] = None
        self._view_mode: str = self.settings.get("view_mode", "cards")
        self._sort_col: Optional[str] = None
        self._sort_rev: bool = False
        self._table_games: list = []

        self._apply_style()
        self.configure(bg=C_BG)
        self._build_header()
        self._build_toolbar()
        self._build_tabs()
        self._build_status_bar()

        self.refresh_all()

        # Show first-run setup guide if this is a fresh install
        if not self.settings.get("welcome_shown"):
            self.after(300, self._show_welcome_dialog)

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
                command=lambda u=url: __import__("webbrowser").open(u),
            ).pack(anchor="w", padx=(16, 0))

        # ── Step 1 ────────────────────────────────────────────────────────────
        section(body, "1", "Get a free BGG API token  (recommended)")
        bullet(body, "Log into BoardGameGeek, then visit the link below.")
        bullet(body, 'Click "Register a new application", give it any name, submit.')
        bullet(body, "Copy the Bearer token shown on that page.")
        bullet(body, 'Open the Settings tab → paste the token → click Save.')
        link_btn(body, "boardgamegeek.com/applications", "https://boardgamegeek.com/applications")

        # divider
        tk.Frame(body, bg=C_PALE, height=1).pack(fill="x", pady=(14, 0))
        tk.Label(body, text="  — OR —",
                 bg=C_BG, fg="#888", font=("Segoe UI", 9, "italic")).pack(anchor="w")
        tk.Frame(body, bg=C_PALE, height=1).pack(fill="x", pady=(0, 4))

        # ── Step 1 alt ────────────────────────────────────────────────────────
        section(body, "1b", "Export your collection as a CSV  (no token needed)")
        bullet(body, "Log into BoardGameGeek and open your collection.")
        bullet(body, 'Click the export / download icon → choose CSV format.')
        bullet(body, 'Use "Import collection CSV..." on the toolbar to load it.')
        bullet(body, "Note: your CSV may not include image URLs — you'll need the API token above to download images afterward.")
        link_btn(body, "boardgamegeek.com/collection/user/YOUR_USERNAME",
                 "https://boardgamegeek.com/collection/user/Ballewcifer")

        # ── Step 2 ────────────────────────────────────────────────────────────
        section(body, "2", "Import your collection")
        bullet(body, 'With a token: click "Import from BGG..." on the toolbar, enter your username.')
        bullet(body, 'With a CSV: click "Import collection CSV..." and select the file.')
        bullet(body, "Images download automatically — no extra steps needed.")

        # ── Step 3 ────────────────────────────────────────────────────────────
        section(body, "3", "You're done!")
        bullet(body, "Browse your games, check them out to members, and log plays.")
        bullet(body, 'Use the Settings tab any time to update your username or token.')

        # ── footer ────────────────────────────────────────────────────────────
        tk.Frame(win, bg=C_BLUE, height=1).pack(fill="x")
        footer = tk.Frame(win, bg=C_PALE, pady=10, padx=28)
        footer.pack(fill="x")

        def close(go_settings: bool = False) -> None:
            self.settings["welcome_shown"] = True
            config.save(self.settings)
            win.destroy()
            if go_settings:
                self.nb.select(self.settings_tab)

        tk.Button(
            footer, text="Open Settings to add my token",
            bg=C_BLUE, fg=C_WHITE, activebackground=C_NAVY, activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=14, pady=5, cursor="hand2",
            command=lambda: close(go_settings=True),
        ).pack(side="left")

        tk.Button(
            footer, text="Get Started",
            bg=C_NAVY, fg=C_WHITE, activebackground=C_BLUE, activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9, "bold"),
            padx=14, pady=5, cursor="hand2",
            command=lambda: close(go_settings=False),
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

    def _build_header(self) -> None:
        """Navy banner at the very top with app title and About button."""
        hdr = tk.Frame(self, bg=C_NAVY, pady=6)
        hdr.pack(side="top", fill="x")

        tk.Label(
            hdr, text="  \U0001f3b2  Board Game Library",
            bg=C_NAVY, fg=C_WHITE,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            hdr, text="About",
            bg=C_BLUE, fg=C_WHITE, activebackground=C_SKY, activeforeground=C_WHITE,
            relief="flat", font=("Segoe UI", 9),
            cursor="hand2", padx=10, pady=2,
            command=self.on_about,
        ).pack(side="right", padx=10)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="Import collection CSV...", command=self.on_import_csv).pack(side="left")
        ttk.Button(bar, text="Import from BGG...", command=self.on_import_from_bgg).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Download Images", command=self.on_download_images).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_games())
        entry = ttk.Entry(bar, textvariable=self.search_var, width=30)
        entry.pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Clear", command=lambda: self.search_var.set("")).pack(side="left", padx=(4, 0))

        # --- filter bar (second row, light-blue background) ---
        fbar = ttk.Frame(self, style="Filter.TFrame", padding=(8, 4, 8, 6))
        fbar.pack(side="top", fill="x")

        def flabel(text): return ttk.Label(fbar, text=text, style="Filter.TLabel")
        def fcheck(text, var, cmd): return ttk.Checkbutton(fbar, text=text, variable=var,
                                                           command=cmd, style="Filter.TCheckbutton")

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

        # ── view toggle (right-aligned) ───────────────────────────────────────
        ttk.Separator(fbar, orient="vertical").pack(side="right", fill="y", padx=(8, 4))

        def _view_btn(text, mode):
            active = self._view_mode == mode
            btn = tk.Button(
                fbar, text=text,
                bg=C_NAVY if active else C_PALE,
                fg=C_WHITE if active else C_NAVY,
                activebackground=C_BLUE, activeforeground=C_WHITE,
                relief="flat", font=("Segoe UI", 9, "bold"),
                padx=8, pady=2, cursor="hand2",
                command=lambda m=mode: self._set_view(m),
            )
            btn.pack(side="right", padx=(0, 2))
            return btn

        self._btn_table = _view_btn("≡  Table", "table")
        self._btn_cards = _view_btn("⊞  Cards", "cards")

    def _build_tabs(self) -> None:
        self.nb = ttk.Notebook(self)
        self.nb.pack(side="top", fill="both", expand=True)

        self.games_tab = ttk.Frame(self.nb)
        self.members_tab = ttk.Frame(self.nb)
        self.history_tab = ttk.Frame(self.nb)
        self.plays_tab = ttk.Frame(self.nb)
        self.settings_tab = ttk.Frame(self.nb)

        self.nb.add(self.games_tab, text="Games")
        self.nb.add(self.members_tab, text="Members")
        self.nb.add(self.history_tab, text="History")
        self.nb.add(self.plays_tab, text="Plays")
        self.nb.add(self.settings_tab, text="Settings")

        self._build_games_tab()
        self._build_members_tab()
        self._build_history_tab()
        self._build_plays_tab()
        self._build_settings_tab()

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
        self.games_canvas = tk.Canvas(self._card_frame, highlightthickness=0, background="#f5f5f5")
        scroll = ttk.Scrollbar(self._card_frame, orient="vertical", command=self.games_canvas.yview)
        self.games_canvas.configure(yscrollcommand=scroll.set)
        self.games_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
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
            ("fav",     "★",           34,  "center", False),
            ("insert",  "\U0001f5f3",  34,  "center", False),
            ("name",    "Name",        260, "w",      True),
            ("year",    "Year",         54, "center", False),
            ("players", "Players",      72, "center", False),
            ("time",    "Time",         84, "center", False),
            ("weight",  "Complexity",   84, "center", False),
            ("rating",  "BGG ★",        62, "center", False),
            ("best",    "Best At",      72, "center", False),
            ("status",  "Status",      140, "center", False),
            ("plays",   "Plays",        50, "center", False),
        ]
        for cid, heading, width, anchor, stretch in col_defs:
            self.games_tree.heading(cid, text=heading,
                                    command=lambda c=cid: self._sort_table(c))
            self.games_tree.column(cid, width=width, anchor=anchor, stretch=stretch)

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.games_tree.yview)
        self.games_tree.configure(yscrollcommand=vsb.set)
        self.games_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

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
            btn.configure(bg=C_NAVY if active else C_PALE,
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
        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            card.grid(row=r, column=c, padx=gap // 2, pady=gap // 2, sticky="n")
        for c in range(cols):
            self.games_inner.grid_columnconfigure(c, weight=1)

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
        for card in self._cards:
            card.destroy()
        self._cards.clear()

        if not games:
            msg = (
                "No games match your filters."
                if self._filters_active()
                else 'No games yet. Use "Import from BGG..." or "Import collection CSV..." to get started.'
            )
            empty = ttk.Label(self.games_inner, text=msg, padding=20)
            empty.grid(row=0, column=0)
            self._cards.append(empty)
            return

        for game in games:
            self._cards.append(self._build_card(game, open_loans.get(game["bgg_id"]), play_counts))
        self._layout_cards(self.games_canvas.winfo_width())

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
                    "\U0001f5f3" if g["has_insert"] else "",
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
            "fav": "★", "insert": "\U0001f5f3", "name": "Name", "year": "Year",
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
        menu.add_command(label="Set Image…",   command=lambda: self.on_set_image(game))
        fav_lbl = "Remove from Favorites" if game["is_favorite"] else "Add to Favorites"
        menu.add_command(label=fav_lbl,        command=lambda: self.on_toggle_favorite(game))
        menu.tk_popup(event.x_root, event.y_root)

    def _build_card(self, game, loan, play_counts: dict) -> ttk.Frame:
        out_to = None
        if loan is not None:
            out_to = f"{loan['first_name']} {loan['last_name']}".strip()

        bgg_id = game["bgg_id"]
        is_fav = bool(game["is_favorite"])
        has_insert = bool(game["has_insert"])
        n_plays = play_counts.get(bgg_id, 0)

        card = ttk.Frame(self.games_inner, padding=8, relief="solid", borderwidth=1)
        card.configure(width=180)

        # --- top row: image + star in top-right corner ---
        img_frame = ttk.Frame(card)
        img_frame.pack(fill="x")

        img_label = ttk.Label(img_frame, anchor="center")
        img_label.pack(side="left", expand=True)
        self._set_card_image(img_label, game)

        star_text = "★" if is_fav else "☆"          # filled / outline star
        star_btn = tk.Button(
            img_frame,
            text=star_text,
            font=("Segoe UI", 14),
            fg="#f5a623" if is_fav else "#aaa",
            relief="flat",
            cursor="hand2",
            bd=0,
            highlightthickness=0,
            command=lambda g=game: self.on_toggle_favorite(g),
        )
        star_btn.pack(side="right", anchor="n", padx=(0, 2), pady=2)

        # --- name + year ---
        ttk.Label(
            card,
            text=game["name"],
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

        # --- best-at line ---
        if game["best_players"]:
            ttk.Label(
                card,
                text=f"★ Best at {game['best_players']}",
                foreground="#b8860b",
                font=("Segoe UI", 8),
            ).pack()

        # --- badges row: insert + play count ---
        badge_row = ttk.Frame(card)
        badge_row.pack(pady=(3, 0))
        if has_insert:
            tk.Label(
                badge_row, text="\U0001f5f3 Insert",
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

        # --- action buttons ---
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
        ttk.Button(btn_row2, text="Log Play",
                   command=lambda g=game: self.on_log_play(g)).pack(fill="x")

        return card

    def _set_card_image(self, label: ttk.Label, game) -> None:
        path = game["image_path"]
        if path and Path(path).exists():
            img = self._load_thumb(path)
            if img is not None:
                label.configure(image=img)
                label.image = img  # keep reference
                return
        label.configure(image=self._get_placeholder(), text="")
        label.image = self._get_placeholder()

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
                values=(
                    r["game_name"],
                    f"{r['first_name']} {r['last_name']}",
                    fmt_date(r["checked_out_at"]),
                    fmt_date(r["returned_at"]) or "(out)",
                    r["notes"] or "",
                ),
            )

    # ---------- settings tab ----------

    def _build_settings_tab(self) -> None:
        frame = ttk.Frame(self.settings_tab, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="BGG username:").grid(row=0, column=0, sticky="w", pady=4)
        self.username_var = tk.StringVar(value=self.settings.get("bgg_username", ""))
        ttk.Entry(frame, textvariable=self.username_var, width=30).grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text="BGG API token:").grid(row=1, column=0, sticky="w", pady=4)
        self.token_var = tk.StringVar(value=self.settings.get("bgg_token", ""))
        ttk.Entry(frame, textvariable=self.token_var, width=60, show="•").grid(row=1, column=1, sticky="w")

        # How-to-get-a-token help block
        help_frame = tk.Frame(frame, bg="#eaf4fd", relief="solid", bd=1)
        help_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0), ipadx=10, ipady=8)

        tk.Label(
            help_frame,
            text="How to get a free BGG API token",
            bg="#eaf4fd", fg=C_NAVY,
            font=("Segoe UI", 9, "bold"),
            justify="left",
        ).pack(anchor="w")

        tk.Label(
            help_frame,
            text=(
                "BGG's XML API (used by 'Import from BGG...' and 'Download Images') now requires\n"
                "a Bearer token.  Getting one is free and takes about 2 minutes:\n\n"
                "  1.  Log into BoardGameGeek in your browser.\n"
                "  2.  Go to:  boardgamegeek.com/applications\n"
                "  3.  Click 'Register a new application'.\n"
                "  4.  Fill in a name (e.g. 'My Library') and any description.  Submit.\n"
                "  5.  Copy the Bearer token shown and paste it into the field above.\n"
                "  6.  Click Save, then use 'Import from BGG...' on the toolbar."
            ),
            bg="#eaf4fd", fg=C_TEXT,
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        tk.Button(
            help_frame,
            text="Open boardgamegeek.com/applications  ↗",
            bg="#eaf4fd", fg=C_BLUE,
            relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "underline"),
            command=lambda: __import__("webbrowser").open("https://boardgamegeek.com/applications"),
        ).pack(anchor="w", pady=(4, 0))

        ttk.Button(frame, text="Save", command=self.on_save_settings).grid(row=3, column=0, sticky="w", pady=(12, 0))

    def on_save_settings(self) -> None:
        self.settings["bgg_username"] = self.username_var.get().strip()
        self.settings["bgg_token"] = self.token_var.get().strip()
        config.save(self.settings)
        self.status("Settings saved.")

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
            ("Created",  APP_CREATED),
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
        self.status(f"Reading {Path(path).name}...")
        try:
            games = bgg.import_collection_csv(Path(path))
        except Exception as e:
            messagebox.showerror("Import failed", f"Could not read CSV:\n{e}")
            self.status("Import failed.")
            return
        if not games:
            messagebox.showinfo("Nothing imported", "No games were found in that CSV.")
            self.status("Nothing imported.")
            return

        self._save_games_to_db(games)
        self.refresh_games()
        self.status(f"Imported {len(games)} games. Downloading thumbnails in the background...")
        threading.Thread(target=self._download_thumbnails_bg, args=(games,), daemon=True).start()

    def on_import_from_bgg(self) -> None:
        """Show a dialog asking for a BGG username + token, then import the collection."""
        token = self.settings.get("bgg_token", "").strip()
        username = self.settings.get("bgg_username", "").strip()

        dialog = tk.Toplevel(self)
        dialog.title("Import from BGG")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(bg=C_BG)

        # Username row
        ttk.Label(dialog, text="BGG username:", padding=(16, 14, 16, 2)).pack(anchor="w")
        uname_var = tk.StringVar(value=username)
        entry = ttk.Entry(dialog, textvariable=uname_var, width=34)
        entry.pack(padx=16, pady=(0, 8))
        entry.focus_set()
        entry.select_range(0, "end")

        # Token status / warning
        if token:
            msg_text  = "✓  API token found in Settings — full import will run."
            msg_color = "#2e7d32"
        else:
            msg_text  = (
                "⚠  No API token found.\n\n"
                "BGG now requires a free Bearer token for all API access.\n"
                "Go to Settings → click the link → register → paste token → Save.\n"
                "Then come back here to import."
            )
            msg_color = "#b71c1c"

        tk.Label(
            dialog, text=msg_text,
            bg=C_BG, fg=msg_color,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=340,
            padx=16, pady=4,
        ).pack(anchor="w")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=16, pady=(8, 14), fill="x")

        def go_settings() -> None:
            dialog.destroy()
            self.nb.select(self.settings_tab)

        def do_import() -> None:
            uname = uname_var.get().strip()
            if not uname:
                messagebox.showerror("Username required", "Enter your BGG username.", parent=dialog)
                return
            tok = self.settings.get("bgg_token", "").strip()
            if not tok:
                messagebox.showerror(
                    "API token required",
                    "BGG requires a Bearer token.\nOpen Settings to add one.",
                    parent=dialog,
                )
                return
            self.settings["bgg_username"] = uname
            config.save(self.settings)
            self.username_var.set(uname)
            dialog.destroy()
            self.status(f"Importing collection for {uname}…")
            threading.Thread(
                target=self._import_from_username_bg,
                args=(uname, tok),
                daemon=True,
            ).start()

        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="left")
        if not token:
            ttk.Button(btn_frame, text="Open Settings", command=go_settings).pack(side="right")
        else:
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
                f"BGG rejected the token:\n{err}\n\nCheck it in Settings and try again.",
            ))
            self._post_status("Import failed: token rejected.")
        except Exception as exc:
            traceback.print_exc()
            self.after(0, lambda err=str(exc): messagebox.showerror(
                "Import failed",
                f"Could not import collection for '{username}':\n{err}",
            ))
            self._post_status("Import from BGG failed.")

    def on_sync_api(self) -> None:
        token = self.settings.get("bgg_token", "")
        username = self.settings.get("bgg_username", "")
        if not token:
            messagebox.showinfo(
                "API token needed",
                "BGG's XML API requires a free Bearer token.\n\n"
                "Go to Settings for step-by-step instructions.",
            )
            self.nb.select(self.settings_tab)
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
            rows = c.execute("SELECT bgg_id, image_path, best_players FROM games").fetchall()
        # Fetch pages for games missing image OR missing best_players data.
        needs_fetch = [
            r["bgg_id"] for r in rows
            if (not r["image_path"] or not Path(r["image_path"]).exists())
            or not r["best_players"]
        ]
        if not needs_fetch:
            messagebox.showinfo("Images", "All games already have images and Best-at data.")
            return
        self.status(f"Fetching BGG page data for {len(needs_fetch)} games in the background...")
        threading.Thread(
            target=self._fetch_and_cache_images_bg,
            args=(needs_fetch,),
            daemon=True,
        ).start()

    def _fetch_and_cache_images_bg(self, bgg_ids: list[int]) -> None:
        """Download box-art for every game that is missing an image.

        Image URL priority (most reliable → least):
          1. image_url / thumbnail_url already stored from CSV import
          2. BGG XML API  (/xmlapi2/thing — public, no token needed)
        HTML page scraping is NOT used for images — BGG's Cloudflare blocks
        non-browser clients.  Best-at data is fetched from the HTML page as a
        silent, non-fatal bonus.
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
                # 2. Ask the public XML API if we still have nothing
                if not url:
                    url = bgg.get_image_url_from_api(bgg_id)

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
                else:
                    img_failed += 1
                    last_error = f"No image URL found for game #{bgg_id}"

            # ── best-at (HTML scrape — optional, silent on failure) ───────────
            if not (row and row["best_players"]):
                try:
                    page = bgg.get_bgg_page_data(bgg_id)
                    if page.best_players:
                        with db.connect() as c:
                            c.execute(
                                "UPDATE games SET best_players = ? WHERE bgg_id = ?",
                                (page.best_players, bgg_id),
                            )
                except Exception:
                    pass  # Best-at data is a bonus; never block image downloads

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
        if not all_games:
            messagebox.showinfo("No games", "Import your collection first.")
            return

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
        ttk.Entry(dialog, textvariable=players_var, width=36).grid(row=2, column=1, **pad)

        ttk.Label(dialog, text="Winner:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, **pad)
        winner_var = tk.StringVar(value=play["winner"] or "" if editing else "")
        ttk.Entry(dialog, textvariable=winner_var, width=36).grid(row=3, column=1, **pad)

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
            with db.connect() as c:
                if editing:
                    db.update_play(c, play["id"], gid, played,
                                   players_var.get().strip(),
                                   winner_var.get().strip(),
                                   notes_var.get().strip())
                else:
                    db.log_play(c, gid, played,
                                players_var.get().strip(),
                                winner_var.get().strip(),
                                notes_var.get().strip())
            dialog.destroy()
            self.refresh_plays()
            self.refresh_games()   # update play-count badges
            action = "Updated" if editing else "Logged"
            self.status(f"{action} play for {game_var.get()}.")

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
        win.geometry("640x560")

        top = ttk.Frame(win, padding=10)
        top.pack(fill="x")

        if game["image_path"] and Path(game["image_path"]).exists():
            try:
                img = Image.open(game["image_path"])
                img.thumbnail((220, 220))
                tk_img = ImageTk.PhotoImage(img)
                lbl = ttk.Label(top, image=tk_img)
                lbl.image = tk_img
                lbl.pack(side="left", padx=(0, 12))
            except (OSError, ValueError):
                pass

        info = ttk.Frame(top)
        info.pack(side="left", fill="both", expand=True)
        title = ttk.Label(info, text=game["name"], font=("Segoe UI", 13, "bold"))
        title.pack(anchor="w")
        if game["year"]:
            ttk.Label(info, text=f"Published {game['year']}", foreground="#666").pack(anchor="w")

        rows: list[tuple[str, str]] = []
        rows.append(("Players", fmt_players(game["min_players"], game["max_players"])))
        rows.append(("Playing time", fmt_time(game["min_playtime"], game["max_playtime"], game["playing_time"])))
        if game["min_age"]:
            rows.append(("Min age", f"{game['min_age']}+"))
        if game["best_players"]:
            rows.append(("Best at", f"{game['best_players']} players"))
        if game["weight"]:
            rows.append(("Complexity", f"{game['weight']:.2f} / 5"))
        if game["avg_rating"]:
            rows.append(("BGG rating", f"{game['avg_rating']:.2f}"))
        if game["my_rating"]:
            rows.append(("My rating", f"{game['my_rating']:.1f}"))
        if game["categories"]:
            rows.append(("Categories", game["categories"]))
        if game["mechanics"]:
            rows.append(("Mechanics", game["mechanics"]))
        if game["designers"]:
            rows.append(("Designers", game["designers"]))
        if game["publishers"]:
            rows.append(("Publishers", game["publishers"]))

        grid = ttk.Frame(info)
        grid.pack(anchor="w", pady=(8, 0), fill="x")
        for i, (k, v) in enumerate(rows):
            ttk.Label(grid, text=f"{k}:", font=("Segoe UI", 9, "bold")).grid(row=i, column=0, sticky="nw", padx=(0, 8))
            ttk.Label(grid, text=v, wraplength=320, justify="left").grid(row=i, column=1, sticky="w")

        if game["my_comment"]:
            ttk.Label(win, text="Your note:", font=("Segoe UI", 9, "bold"), padding=(10, 6, 10, 0)).pack(anchor="w")
            ttk.Label(win, text=game["my_comment"], wraplength=600, justify="left", padding=(10, 0)).pack(anchor="w")

        if game["description"]:
            ttk.Label(win, text="Description:", font=("Segoe UI", 9, "bold"), padding=(10, 6, 10, 0)).pack(anchor="w")
            text = tk.Text(win, wrap="word", height=8)
            text.insert("1.0", game["description"])
            text.configure(state="disabled")
            text.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # --- toggles row ---
        toggles = ttk.Frame(win, padding=(10, 4))
        toggles.pack(fill="x")

        insert_var = tk.BooleanVar(value=bool(game["has_insert"]))
        def on_insert_toggle() -> None:
            with db.connect() as c:
                db.set_insert(c, game["bgg_id"], insert_var.get())
            self.refresh_games()
        ttk.Checkbutton(
            toggles, text="\U0001f5f3 Has 3D printed insert",
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

        close_row = ttk.Frame(win)
        close_row.pack(fill="x", pady=(0, 10))
        ttk.Button(close_row, text="Log Play",
                   command=lambda: self.on_log_play(game)).pack(side="left", padx=10)
        ttk.Button(close_row, text="Set Image…",
                   command=lambda: self.on_set_image(game, refresh_callback=win.destroy)
                   ).pack(side="left")
        ttk.Button(close_row, text="Close", command=win.destroy).pack(side="right", padx=10)

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
            old_path = game.get("image_path") or ""
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

    # ---------- refresh ----------

    def refresh_all(self) -> None:
        self.refresh_games()
        self.refresh_members()
        self.refresh_history()
        self.refresh_plays()


if __name__ == "__main__":
    App().mainloop()
