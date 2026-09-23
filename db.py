"""SQLite storage for the board game library."""
from __future__ import annotations

import base64
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    bgg_id          INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    year            INTEGER,
    image_url       TEXT,
    thumbnail_url   TEXT,
    image_path      TEXT,
    min_players     INTEGER,
    max_players     INTEGER,
    min_playtime    INTEGER,
    max_playtime    INTEGER,
    playing_time    INTEGER,
    min_age         INTEGER,
    weight          REAL,
    avg_rating      REAL,
    my_rating       REAL,
    description     TEXT,
    categories      TEXT,
    mechanics       TEXT,
    designers       TEXT,
    publishers      TEXT,
    best_players    TEXT,
    my_comment      TEXT,
    own             INTEGER DEFAULT 1,
    last_synced     TEXT,
    is_favorite     INTEGER DEFAULT 0,
    has_insert      INTEGER DEFAULT 0,
    is_expansion    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(bgg_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    checked_out_at  TEXT NOT NULL,
    returned_at     TEXT,
    due_date        TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS plays (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id           INTEGER NOT NULL REFERENCES games(bgg_id) ON DELETE CASCADE,
    played_at         TEXT NOT NULL,
    player_names      TEXT,
    winner            TEXT,
    notes             TEXT,
    duration_minutes  INTEGER,
    scores            TEXT
);

-- Multi-collection support: each synced BGG username is a "collection", and a
-- game can belong to several (many-to-many) so collections can be compared.
CREATE TABLE IF NOT EXISTS collections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    bgg_username TEXT UNIQUE,
    created_at   TEXT,
    last_synced  TEXT
);

CREATE TABLE IF NOT EXISTS game_collections (
    game_id       INTEGER NOT NULL REFERENCES games(bgg_id)   ON DELETE CASCADE,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    PRIMARY KEY (game_id, collection_id)
);

CREATE INDEX IF NOT EXISTS idx_gc_collection ON game_collections(collection_id);
CREATE INDEX IF NOT EXISTS idx_gc_game       ON game_collections(game_id);

CREATE INDEX IF NOT EXISTS idx_loans_open
    ON loans(game_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_loans_user ON loans(user_id);
CREATE INDEX IF NOT EXISTS idx_plays_game ON plays(game_id);
"""

# Columns added after the initial release — applied via ALTER TABLE so
# existing databases are updated without losing data.
MIGRATIONS = [
    "ALTER TABLE games ADD COLUMN is_favorite       INTEGER DEFAULT 0",
    "ALTER TABLE games ADD COLUMN has_insert        INTEGER DEFAULT 0",
    "ALTER TABLE games ADD COLUMN is_expansion      INTEGER DEFAULT 0",
    "ALTER TABLE games ADD COLUMN tags              TEXT",
    "ALTER TABLE loans ADD COLUMN due_date          TEXT",
    "ALTER TABLE plays ADD COLUMN duration_minutes  INTEGER",
    "ALTER TABLE plays ADD COLUMN scores            TEXT",
    "ALTER TABLE games ADD COLUMN manual_fields     TEXT",
    # A collection can be "claimed" by a member (its owner). When a member owns
    # one or more collections they may only check out games from them.
    "ALTER TABLE collections ADD COLUMN owner_user_id INTEGER REFERENCES users(id)",
    # 1 = cooperative, 0 = competitive, NULL = unset.
    "ALTER TABLE games ADD COLUMN is_cooperative INTEGER",
    # BGG id/name of this game's base game, if it's an expansion. Purely
    # BGG-derived (not user-editable), so always overwritten on sync.
    "ALTER TABLE games ADD COLUMN base_game_id INTEGER",
    "ALTER TABLE games ADD COLUMN base_game_name TEXT",
    # BGG's collection status (own, wishlist, fortrade, etc. — see
    # bgg.STATUS_FLAGS). NULL for games with no BGG collection data (e.g.
    # manually added and never synced). The `own` column above stays the
    # authoritative "is this really in my library" bit; this is a richer,
    # informational label alongside it.
    "ALTER TABLE games ADD COLUMN bgg_status TEXT",
    # Optional BGG username on a friend (reference only — parity with mobile).
    "ALTER TABLE users ADD COLUMN bgg_username TEXT",
    # 1 = the user manually marked this OWNED game "not played yet". Opt-in
    # (a game with zero plays may have been played before the app existed);
    # cleared automatically when a play is logged for the game.
    "ALTER TABLE games ADD COLUMN is_unplayed INTEGER DEFAULT 0",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as c:
        c.executescript(SCHEMA)
        # Apply any migrations that add columns to existing tables.
        for sql in MIGRATIONS:
            try:
                c.execute(sql)
            except sqlite3.OperationalError:
                pass  # Column already exists — safe to ignore.


# ---------- games ----------

def upsert_game(
    c: sqlite3.Connection,
    g: dict,
    skip_fields: Optional[set] = None,
) -> None:
    """Insert or update a game row.

    skip_fields: column names that must NOT be overwritten on conflict
    (used by the BGG sync to honour manual field overrides).
    is_favorite and has_insert are always protected.
    """
    cols = [
        "bgg_id", "name", "year", "image_url", "thumbnail_url", "image_path",
        "min_players", "max_players", "min_playtime", "max_playtime",
        "playing_time", "min_age", "weight", "avg_rating", "my_rating",
        "description", "categories", "mechanics", "designers", "publishers",
        "best_players", "my_comment", "own", "last_synced", "is_expansion",
        "is_cooperative", "base_game_id", "base_game_name", "bgg_status",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    # is_favorite / has_insert are always protected; caller may add more.
    protected = {"bgg_id"} | (skip_fields or set())
    # bgg_status uses COALESCE so call sites that omit it (e.g. "Find on BGG…"
    # in Log-a-Play) don't silently wipe an existing game's real status to NULL.
    coalesced = {"bgg_status"}
    updates = ", ".join(
        f"{col}=COALESCE(excluded.{col}, {col})" if col in coalesced
        else f"{col}=excluded.{col}"
        for col in cols if col not in protected
    )
    sql = (
        f"INSERT INTO games ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(bgg_id) DO UPDATE SET {updates}"
    )
    c.execute(sql, [g.get(col) for col in cols])


def set_image_path(c: sqlite3.Connection, bgg_id: int, image_path: str) -> None:
    c.execute("UPDATE games SET image_path = ? WHERE bgg_id = ?", (image_path, bgg_id))


def set_favorite(c: sqlite3.Connection, bgg_id: int, value: bool) -> None:
    c.execute("UPDATE games SET is_favorite = ? WHERE bgg_id = ?", (int(value), bgg_id))


def set_insert(c: sqlite3.Connection, bgg_id: int, value: bool) -> None:
    c.execute("UPDATE games SET has_insert = ? WHERE bgg_id = ?", (int(value), bgg_id))


def unplayed_eligible(c: sqlite3.Connection, bgg_id: int) -> bool:
    """A game can be marked "not played yet" only if it is owned and has no
    logged plays."""
    row = c.execute(
        "SELECT own, (SELECT COUNT(*) FROM plays WHERE game_id = games.bgg_id) AS n "
        "FROM games WHERE bgg_id = ?", (bgg_id,)).fetchone()
    return row is not None and bool(row["own"]) and row["n"] == 0


def set_unplayed(c: sqlite3.Connection, ids, value: bool) -> tuple[int, int]:
    """Mark (value=True) or clear (value=False) the "not played yet" flag on
    *ids*. Marking skips ineligible games (not owned, or with a logged play).
    Returns (changed, skipped); clearing never skips."""
    changed = skipped = 0
    for gid in ids:
        if value and not unplayed_eligible(c, gid):
            skipped += 1
            continue
        c.execute("UPDATE games SET is_unplayed = ? WHERE bgg_id = ?", (int(bool(value)), gid))
        changed += 1
    return changed, skipped


UNPLAYED_NONE_ELIGIBLE = ("Games with a logged play, and games you don't own, "
                          "can't be marked unplayed.")


def clear_unplayed_if_played(c: sqlite3.Connection) -> None:
    """Drop the mark from every game that has plays (keeps a mark from ever
    contradicting the play log)."""
    c.execute("UPDATE games SET is_unplayed = 0 WHERE is_unplayed = 1 AND "
              "EXISTS (SELECT 1 FROM plays WHERE plays.game_id = games.bgg_id)")


def get_manual_fields(c: sqlite3.Connection, bgg_id: int) -> set:
    """Return the set of field names that have been manually overridden."""
    row = c.execute(
        "SELECT manual_fields FROM games WHERE bgg_id = ?", (bgg_id,)
    ).fetchone()
    if row is None or not row["manual_fields"]:
        return set()
    return {f.strip() for f in row["manual_fields"].split(",") if f.strip()}


def set_manual_fields(c: sqlite3.Connection, bgg_id: int, fields: set) -> None:
    """Persist the set of manually overridden field names (empty set clears all)."""
    val = ", ".join(sorted(fields)) if fields else None
    c.execute(
        "UPDATE games SET manual_fields = ? WHERE bgg_id = ?", (val, bgg_id)
    )


# BGG's own collection sort ignores a leading "The", "A", or "An" when
# alphabetizing titles (e.g. "The Castles of Burgundy" sorts under "C") —
# match that instead of a plain alphabetical sort.
_NAME_SORT_KEY = """CASE
    WHEN name LIKE 'The %' THEN SUBSTR(name, 5)
    WHEN name LIKE 'An %'  THEN SUBSTR(name, 4)
    WHEN name LIKE 'A %'   THEN SUBSTR(name, 3)
    ELSE name
  END COLLATE NOCASE"""


def name_sort_key(name: str) -> str:
    """Python-side equivalent of _NAME_SORT_KEY, for sorting name lists
    outside of a SQL query (e.g. an autocomplete suggestion list)."""
    lower = name.lower()
    for article in ("the ", "an ", "a "):
        if lower.startswith(article):
            return name[len(article):].lower()
    return name.lower()


def _status_where(owned_only: bool, status) -> tuple[str, list]:
    """Shared WHERE-clause builder for list_games()/count_games().

    status accepts a single value (back-compat) or a list for a multi-select
    filter (e.g. ["wishlist", "fortrade"] — match any of them).
    None/empty      — respect owned_only (default behavior, unchanged).
    "all"           — every game regardless of own/bgg_status; overrides
                      every other value if present alongside them.
    "owned"         — own = 1 (the authoritative ownership flag — works even
                      for legacy rows with no bgg_status set), combinable
                      with real statuses in the same list.
    a bgg.STATUS_FLAGS value (e.g. "wishlist") — bgg_status = that value.
    """
    statuses = [] if not status else ([status] if isinstance(status, str) else list(status))
    if not statuses:
        return ("own = 1" if owned_only else "1"), []
    if "all" in statuses:
        return "1", []
    conditions: list[str] = []
    params: list = []
    if "owned" in statuses:
        conditions.append("own = 1")
    flags = [s for s in statuses if s not in ("owned", "all")]
    if flags:
        placeholders = ",".join("?" * len(flags))
        conditions.append(f"bgg_status IN ({placeholders})")
        params.extend(flags)
    if not conditions:
        return ("own = 1" if owned_only else "1"), []
    return " OR ".join(conditions), params


def list_games(c: sqlite3.Connection, search: str = "",
               owned_only: bool = True,
               status=None, unplayed_only: bool = False) -> list[sqlite3.Row]:
    """Return games ordered by name. See _status_where() for `status`'s shape.
    unplayed_only: only owned games marked "not played yet"."""
    where, params = _status_where(owned_only, status)
    if unplayed_only:
        where = f"({where}) AND own = 1 AND is_unplayed = 1"
    if search:
        return c.execute(
            f"SELECT * FROM games WHERE {where} AND name LIKE ?"
            f" ORDER BY {_NAME_SORT_KEY}",
            (*params, f"%{search}%"),
        ).fetchall()
    return c.execute(
        f"SELECT * FROM games WHERE {where} ORDER BY {_NAME_SORT_KEY}", params
    ).fetchall()


def count_games(c: sqlite3.Connection, owned_only: bool = True,
                 status=None) -> int:
    """Same WHERE-clause semantics as list_games(), but just the row count
    (used for the games-view "N of M" footer without fetching every row)."""
    where, params = _status_where(owned_only, status)
    return c.execute(f"SELECT COUNT(*) FROM games WHERE {where}", params).fetchone()[0]


def next_manual_id(c: sqlite3.Connection) -> int:
    """A synthetic bgg_id for a manually-added game with no real BGG match —
    guaranteed to never collide with a real (always-positive) BGG id."""
    r = c.execute("SELECT MIN(bgg_id) FROM games").fetchone()
    lowest = r[0] if r[0] is not None else 0
    return min(lowest, 0) - 1


def get_game(c: sqlite3.Connection, bgg_id: int) -> Optional[sqlite3.Row]:
    return c.execute("SELECT * FROM games WHERE bgg_id = ?", (bgg_id,)).fetchone()


def delete_game(c: sqlite3.Connection, bgg_id: int) -> None:
    """Remove a game and all its related loans/plays (CASCADE handles FK rows)."""
    c.execute("DELETE FROM games WHERE bgg_id = ?", (bgg_id,))


def list_expansions_of(c: sqlite3.Connection, base_game_id: int) -> list[sqlite3.Row]:
    """Games in the library that are expansions of the given base game."""
    return c.execute(
        f"SELECT * FROM games WHERE base_game_id = ? ORDER BY {_NAME_SORT_KEY}",
        (base_game_id,),
    ).fetchall()


# ---------- collections ----------

def list_collections(c: sqlite3.Connection) -> list[sqlite3.Row]:
    """All collections with their game counts, ordered by name."""
    return c.execute(
        """
        SELECT col.*, COUNT(gc.game_id) AS game_count
        FROM collections col
        LEFT JOIN game_collections gc ON gc.collection_id = col.id
        GROUP BY col.id
        ORDER BY col.name COLLATE NOCASE
        """
    ).fetchall()


def get_or_create_collection(
    c: sqlite3.Connection, bgg_username: Optional[str], name: Optional[str] = None
) -> int:
    """Return the id of the collection for `bgg_username`, creating it if needed.

    If `bgg_username` is falsy a new unnamed-source collection is created.
    Passing `name` updates the display name of an existing match.
    """
    if bgg_username:
        row = c.execute(
            "SELECT id FROM collections WHERE bgg_username = ?", (bgg_username,)
        ).fetchone()
        if row:
            if name:
                c.execute("UPDATE collections SET name = ? WHERE id = ?", (name, row["id"]))
            return row["id"]
    cur = c.execute(
        "INSERT INTO collections (name, bgg_username, created_at) VALUES (?, ?, ?)",
        (name or bgg_username or "Collection", bgg_username or None, now_iso()),
    )
    return cur.lastrowid


def collection_id_for_username(c: sqlite3.Connection, bgg_username: str) -> Optional[int]:
    """Return the existing collection id for a BGG username, or None (no create)."""
    if not bgg_username:
        return None
    row = c.execute(
        "SELECT id FROM collections WHERE bgg_username = ?", (bgg_username,)).fetchone()
    return row["id"] if row else None


def rename_collection(c: sqlite3.Connection, collection_id: int, name: str) -> None:
    c.execute("UPDATE collections SET name = ? WHERE id = ?", (name.strip(), collection_id))


def delete_collection(c: sqlite3.Connection, collection_id: int) -> None:
    """Remove a collection (its game links cascade; the games themselves stay)."""
    c.execute("DELETE FROM collections WHERE id = ?", (collection_id,))


# ---------- collection ownership ("claiming") ----------

def claim_collection(c: sqlite3.Connection, collection_id: int,
                     user_id: Optional[int]) -> None:
    """Set (or clear, with user_id=None) the member who owns a collection.

    A member may own only one collection, so claiming releases any other
    collection that member previously owned.
    """
    if user_id is not None:
        c.execute("UPDATE collections SET owner_user_id = NULL WHERE owner_user_id = ?",
                  (user_id,))
    c.execute("UPDATE collections SET owner_user_id = ? WHERE id = ?",
              (user_id, collection_id))


def owned_collection_ids(c: sqlite3.Connection, user_id: int) -> set:
    """Collection ids claimed by a member."""
    rows = c.execute(
        "SELECT id FROM collections WHERE owner_user_id = ?", (user_id,)
    ).fetchall()
    return {r["id"] for r in rows}


def user_can_checkout(c: sqlite3.Connection, user_id: int, game_id: int) -> bool:
    """A member who has claimed one or more collections may only check out games
    that belong to one of them. Members who own no collection may check out any
    game."""
    owned = owned_collection_ids(c, user_id)
    if not owned:
        return True
    qmarks = ",".join("?" * len(owned))
    row = c.execute(
        f"SELECT 1 FROM game_collections "
        f"WHERE game_id = ? AND collection_id IN ({qmarks}) LIMIT 1",
        (game_id, *owned),
    ).fetchone()
    return row is not None


def members_allowed_to_checkout(c: sqlite3.Connection, game_id: int) -> set:
    """Member ids permitted to check out *game_id*: everyone who owns no
    collection, plus owners of a collection that contains the game."""
    allowed = set()
    for u in c.execute("SELECT id FROM users").fetchall():
        if user_can_checkout(c, u["id"], game_id):
            allowed.add(u["id"])
    return allowed


def game_in_username_collection(c: sqlite3.Connection, bgg_username: str,
                                game_id: int) -> bool:
    """True if *game_id* belongs to the collection synced under *bgg_username*.

    Backs the device-level "claim my synced collection" check (settings key
    ``claimed_bgg_username``), which is independent of the Friend-keyed
    claim_collection()/user_can_checkout() above (that one assigns a
    collection to a specific Friend). If the collection no longer exists there
    is nothing to restrict against, so it returns True — same as mobile.
    """
    row = c.execute(
        "SELECT id FROM collections WHERE bgg_username = ?", (bgg_username,)
    ).fetchone()
    if row is None:
        return True
    hit = c.execute(
        "SELECT 1 FROM game_collections WHERE game_id = ? AND collection_id = ? LIMIT 1",
        (game_id, row[0]),
    ).fetchone()
    return hit is not None


def migrate_claimed_member(c: sqlite3.Connection, settings: dict) -> bool:
    """One-time settings migration: the old ``claimed_member_id`` (a Friend id)
    becomes ``claimed_bgg_username`` (a string).

    The username is taken from the collection(s) that member owned, when
    exactly one of them has a BGG username. The old key is always dropped so
    it is never read again. Returns True when *settings* changed (the caller
    should persist it).
    """
    if "claimed_member_id" not in settings:
        return False
    mid = settings.pop("claimed_member_id")
    if mid and not settings.get("claimed_bgg_username"):
        names = []
        for cid in owned_collection_ids(c, mid):
            row = c.execute(
                "SELECT bgg_username FROM collections WHERE id = ?", (cid,)
            ).fetchone()
            if row and row[0]:
                names.append(row[0])
        if len(names) == 1:
            settings["claimed_bgg_username"] = names[0]
    return True


def reset_claim_if_cleared(settings: dict, cleared_usernames) -> bool:
    """Drop ``claimed_bgg_username`` if its collection was just cleared, so a
    new collection can be claimed. Returns True when *settings* changed."""
    claimed = settings.get("claimed_bgg_username")
    if claimed and claimed in set(cleared_usernames or []):
        settings.pop("claimed_bgg_username", None)
        return True
    return False


def clear_collections(c: sqlite3.Connection, collection_ids: list[int]) -> list[int]:
    """Delete the given collections and any games left orphaned by the removal.

    A game shared with a collection that is *not* being cleared is kept. A game
    that ends up in no collection is deleted — UNLESS it has play history, which
    is preserved (the game stays so its plays are never lost).
    Returns the bgg_ids of the deleted games so callers can drop cached images.
    """
    ids = [int(i) for i in collection_ids]
    if not ids:
        return []
    qmarks = ",".join("?" * len(ids))
    affected = [
        r["game_id"] for r in c.execute(
            f"SELECT DISTINCT game_id FROM game_collections "
            f"WHERE collection_id IN ({qmarks})", ids,
        )
    ]
    # Removing the collections cascades their game_collections links.
    c.execute(f"DELETE FROM collections WHERE id IN ({qmarks})", ids)

    orphaned = []
    for gid in affected:
        if c.execute("SELECT 1 FROM game_collections WHERE game_id = ? LIMIT 1",
                     (gid,)).fetchone():
            continue   # still in another collection
        if c.execute("SELECT 1 FROM plays WHERE game_id = ? LIMIT 1",
                     (gid,)).fetchone():
            continue   # keep games with play history so plays aren't deleted
        orphaned.append(gid)
    if orphaned:
        om = ",".join("?" * len(orphaned))
        c.execute(f"DELETE FROM games WHERE bgg_id IN ({om})", orphaned)
    return orphaned


def replace_collection_games(
    c: sqlite3.Connection, collection_id: int, game_ids: list[int]
) -> None:
    """Make `game_ids` the exact membership of a collection (used after a sync)."""
    c.execute("DELETE FROM game_collections WHERE collection_id = ?", (collection_id,))
    c.executemany(
        "INSERT OR IGNORE INTO game_collections (game_id, collection_id) VALUES (?, ?)",
        [(gid, collection_id) for gid in game_ids],
    )
    c.execute(
        "UPDATE collections SET last_synced = ? WHERE id = ?", (now_iso(), collection_id)
    )


def collection_game_ids(c: sqlite3.Connection, collection_id: int) -> set:
    rows = c.execute(
        "SELECT game_id FROM game_collections WHERE collection_id = ?", (collection_id,)
    ).fetchall()
    return {r["game_id"] for r in rows}


def remove_game_from_collection(c: sqlite3.Connection, game_id: int, collection_id: int) -> None:
    """Unlink a single game from one collection (the game itself is untouched)."""
    c.execute(
        "DELETE FROM game_collections WHERE game_id = ? AND collection_id = ?",
        (game_id, collection_id),
    )


def game_collection_map(c: sqlite3.Connection) -> dict[int, set]:
    """Return {game_id: {collection_id, ...}} across all collections."""
    out: dict[int, set] = {}
    for r in c.execute("SELECT game_id, collection_id FROM game_collections"):
        out.setdefault(r["game_id"], set()).add(r["collection_id"])
    return out


def ensure_collection_migration(
    c: sqlite3.Connection, default_username: str = "", default_name: str = "My Collection"
) -> None:
    """One-time backfill: if no collections exist yet but owned games do, create a
    default collection (from the configured BGG username) and link all owned games
    to it, so existing single-collection databases keep working."""
    if c.execute("SELECT COUNT(*) FROM collections").fetchone()[0]:
        return
    if not c.execute("SELECT COUNT(*) FROM games WHERE own = 1").fetchone()[0]:
        return
    name = default_name or default_username or "My Collection"
    cid = get_or_create_collection(c, default_username or None, name)
    c.execute(
        "INSERT OR IGNORE INTO game_collections (game_id, collection_id) "
        "SELECT bgg_id, ? FROM games WHERE own = 1",
        (cid,),
    )


# ---------- users ----------

def add_user(c: sqlite3.Connection, first_name: str, last_name: str,
             bgg_username: Optional[str] = None) -> int:
    cur = c.execute(
        "INSERT INTO users (first_name, last_name, bgg_username, created_at) "
        "VALUES (?, ?, ?, ?)",
        (first_name.strip(), last_name.strip(),
         (bgg_username or "").strip() or None, now_iso()),
    )
    return cur.lastrowid


def update_user(c: sqlite3.Connection, user_id: int, first_name: str,
                last_name: str, bgg_username: Optional[str] = None) -> None:
    c.execute(
        "UPDATE users SET first_name = ?, last_name = ?, bgg_username = ? WHERE id = ?",
        (first_name.strip(), last_name.strip(),
         (bgg_username or "").strip() or None, user_id),
    )


def find_user_by_name(c: sqlite3.Connection, first_name: str, last_name: str,
                      exclude_id: Optional[int] = None) -> Optional[sqlite3.Row]:
    """The friend whose "First Last" matches (case-insensitive), or None.
    *exclude_id* skips one friend — used when editing so a friend never
    collides with themselves."""
    full = f"{first_name} {last_name}".strip().casefold()
    for u in list_users(c):
        if exclude_id is not None and u["id"] == exclude_id:
            continue
        if f"{u['first_name']} {u['last_name']}".strip().casefold() == full:
            return u
    return None


def validate_friend(c: sqlite3.Connection, first_name: str, last_name: str,
                    exclude_id: Optional[int] = None) -> Optional[str]:
    """Shared Add/Edit Friend validation (matches mobile's FriendFormModal):
    both names are required and must not duplicate an existing friend.
    Returns an error message, or None when the names are acceptable."""
    f, l = (first_name or "").strip(), (last_name or "").strip()
    if not f or not l:
        return "Both first and last name are required."
    dupe = find_user_by_name(c, f, l, exclude_id)
    if dupe is not None:
        return (f"{dupe['first_name']} {dupe['last_name']} is already in "
                f"your friends list.")
    return None


def list_users(c: sqlite3.Connection) -> list[sqlite3.Row]:
    return c.execute(
        "SELECT * FROM users ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE"
    ).fetchall()


def delete_user(c: sqlite3.Connection, user_id: int) -> None:
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ---------- loans ----------

def open_loan_for_game(c: sqlite3.Connection, bgg_id: int) -> Optional[sqlite3.Row]:
    return c.execute(
        """
        SELECT loans.*, users.first_name, users.last_name
        FROM loans JOIN users ON users.id = loans.user_id
        WHERE loans.game_id = ? AND loans.returned_at IS NULL
        """,
        (bgg_id,),
    ).fetchone()


def check_out(
    c: sqlite3.Connection,
    bgg_id: int,
    user_id: int,
    notes: str = "",
    due_date: Optional[str] = None,
) -> int:
    if open_loan_for_game(c, bgg_id) is not None:
        raise ValueError("Game is already checked out.")
    cur = c.execute(
        "INSERT INTO loans (game_id, user_id, checked_out_at, due_date, notes) VALUES (?, ?, ?, ?, ?)",
        (bgg_id, user_id, now_iso(), due_date or None, notes),
    )
    return cur.lastrowid


def check_in(c: sqlite3.Connection, bgg_id: int) -> None:
    loan = open_loan_for_game(c, bgg_id)
    if loan is None:
        raise ValueError("Game is not currently checked out.")
    c.execute("UPDATE loans SET returned_at = ? WHERE id = ?", (now_iso(), loan["id"]))


def loan_history(
    c: sqlite3.Connection,
    game_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    where = []
    params: list = []
    if game_id is not None:
        where.append("loans.game_id = ?")
        params.append(game_id)
    if user_id is not None:
        where.append("loans.user_id = ?")
        params.append(user_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    return c.execute(
        f"""
        SELECT loans.*, games.name AS game_name,
               users.first_name, users.last_name
        FROM loans
        JOIN games ON games.bgg_id = loans.game_id
        JOIN users ON users.id     = loans.user_id
        {where_sql}
        ORDER BY loans.checked_out_at DESC
        """,
        params,
    ).fetchall()


# ---------- plays ----------

def ensure_players_as_members(c: sqlite3.Connection, player_names: str) -> None:
    """Auto-create a Member for any comma-separated player-name token that doesn't
    already match an existing member's "First Last" (case-insensitive)."""
    tokens = [t.strip() for t in (player_names or "").split(",") if t.strip()]
    if not tokens:
        return
    known = {f"{u['first_name']} {u['last_name']}".strip().casefold() for u in list_users(c)}
    for token in tokens:
        if token.casefold() in known:
            continue
        if " " in token:
            first_name, last_name = token.rsplit(" ", 1)
        else:
            first_name, last_name = token, ""
        add_user(c, first_name, last_name)
        known.add(token.casefold())


def log_play(
    c: sqlite3.Connection,
    game_id: int,
    played_at: str,
    player_names: str = "",
    winner: str = "",
    notes: str = "",
    duration_minutes: Optional[int] = None,
    scores: Optional[str] = None,
) -> int:
    ensure_players_as_members(c, player_names)
    cur = c.execute(
        "INSERT INTO plays (game_id, played_at, player_names, winner, notes, duration_minutes, scores) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip(),
         duration_minutes, scores),
    )
    c.execute("UPDATE games SET is_unplayed = 0 WHERE bgg_id = ?", (game_id,))
    return cur.lastrowid


def get_play(c: sqlite3.Connection, play_id: int) -> Optional[sqlite3.Row]:
    return c.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()


def update_play(
    c: sqlite3.Connection,
    play_id: int,
    game_id: int,
    played_at: str,
    player_names: str = "",
    winner: str = "",
    notes: str = "",
    duration_minutes: Optional[int] = None,
    scores: Optional[str] = None,
) -> None:
    ensure_players_as_members(c, player_names)
    c.execute(
        "UPDATE plays SET game_id=?, played_at=?, player_names=?, winner=?, notes=?, "
        "duration_minutes=?, scores=? WHERE id=?",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip(),
         duration_minutes, scores, play_id),
    )
    c.execute("UPDATE games SET is_unplayed = 0 WHERE bgg_id = ?", (game_id,))


def delete_play(c: sqlite3.Connection, play_id: int) -> None:
    c.execute("DELETE FROM plays WHERE id = ?", (play_id,))


def list_plays(
    c: sqlite3.Connection,
    game_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    where = "WHERE plays.game_id = ?" if game_id is not None else ""
    params = [game_id] if game_id is not None else []
    return c.execute(
        f"""
        SELECT plays.*, games.name AS game_name
        FROM plays
        JOIN games ON games.bgg_id = plays.game_id
        {where}
        ORDER BY plays.played_at DESC
        """,
        params,
    ).fetchall()


def play_counts(c: sqlite3.Connection) -> dict[int, int]:
    """Return {bgg_id: play_count} for all games that have been played."""
    rows = c.execute("SELECT game_id, COUNT(*) AS n FROM plays GROUP BY game_id").fetchall()
    return {r["game_id"]: r["n"] for r in rows}


def play_summary(c: sqlite3.Connection, game_id: int) -> tuple[int, Optional[str], Optional[str]]:
    """Return (count, first_played, last_played) for one game.

    Dates are the ISO ``YYYY-MM-DD`` day part of ``played_at``; both are None
    when the game has never been played (count 0).
    """
    row = c.execute(
        "SELECT COUNT(*) AS n, MIN(played_at) AS first, MAX(played_at) AS last "
        "FROM plays WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    n = row["n"] or 0
    if not n:
        return 0, None, None
    return n, (row["first"] or "")[:10] or None, (row["last"] or "")[:10] or None


# ---------- tags ----------

def set_tags(c: sqlite3.Connection, bgg_id: int, tags: str) -> None:
    """Store a comma-separated tag string for a game."""
    c.execute("UPDATE games SET tags = ? WHERE bgg_id = ?", (tags.strip() or None, bgg_id))


def all_tags(c: sqlite3.Connection) -> list[str]:
    """Return a sorted deduplicated list of every tag in use across all games."""
    rows = c.execute("SELECT tags FROM games WHERE tags IS NOT NULL AND tags != ''").fetchall()
    seen: set[str] = set()
    for row in rows:
        for t in row["tags"].split(","):
            t = t.strip()
            if t:
                seen.add(t)
    return sorted(seen, key=str.casefold)


# ---------- dashboard helpers ----------

def stats_summary(c: sqlite3.Connection) -> dict:
    """Return aggregate counts useful for the dashboard."""
    total_games   = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    total_plays   = c.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    total_members = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    checked_out   = c.execute(
        "SELECT COUNT(*) FROM loans WHERE returned_at IS NULL"
    ).fetchone()[0]
    return {
        "total_games":   total_games,
        "total_plays":   total_plays,
        "total_members": total_members,
        "checked_out":   checked_out,
    }


def currently_checked_out(c: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all open loans with game name, borrower, checkout date, and due date."""
    return c.execute(
        """
        SELECT loans.id, loans.game_id, loans.user_id,
               loans.checked_out_at, loans.due_date,
               games.name AS game_name, games.bgg_id,
               users.first_name, users.last_name
        FROM loans
        JOIN games ON games.bgg_id = loans.game_id
        JOIN users ON users.id     = loans.user_id
        WHERE loans.returned_at IS NULL
        ORDER BY loans.checked_out_at ASC
        """
    ).fetchall()


def recent_plays(c: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Return the most recent play log entries."""
    return c.execute(
        """
        SELECT plays.*, games.name AS game_name
        FROM plays
        JOIN games ON games.bgg_id = plays.game_id
        ORDER BY plays.played_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def top_games_by_plays(c: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    """Return games ranked by total play count."""
    return c.execute(
        """
        SELECT games.bgg_id, games.name, COUNT(plays.id) AS play_count
        FROM plays
        JOIN games ON games.bgg_id = plays.game_id
        GROUP BY plays.game_id
        ORDER BY play_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def top_winners(c: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    """Return members ranked by number of plays they've won."""
    return c.execute(
        """
        SELECT winner, COUNT(*) AS win_count
        FROM plays
        WHERE winner IS NOT NULL AND winner != ''
        GROUP BY winner
        ORDER BY win_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def game_play_stats(c: sqlite3.Connection, bgg_id: int) -> dict:
    """Return per-game play statistics for the Details popup."""
    rows = c.execute(
        "SELECT played_at, player_names, winner, duration_minutes "
        "FROM plays WHERE game_id = ? ORDER BY played_at",
        (bgg_id,),
    ).fetchall()
    if not rows:
        return {"count": 0}
    count = len(rows)
    last_played = rows[-1]["played_at"][:10]
    durations = [r["duration_minutes"] for r in rows if r["duration_minutes"]]
    avg_duration = int(sum(durations) / len(durations)) if durations else None
    # Win counts per player
    win_counts: dict[str, int] = {}
    for r in rows:
        w = (r["winner"] or "").strip()
        if w:
            win_counts[w] = win_counts.get(w, 0) + 1
    return {
        "count":        count,
        "last_played":  last_played,
        "avg_duration": avg_duration,
        "win_counts":   win_counts,
    }


# ---------- JSON backup (shared with the mobile app) ----------
#
# The mobile app's Export/Import Backup (lib/backupCore.ts) and desktop's
# "Export for Mobile" / JSON import speak the same file. Version 5 carries the
# WHOLE library: `members` (with bgg_username), `games` (full rows, minus the
# device-local image_path), `collections`, `game_collections`, `plays`,
# `loans` and `customisations`. Pre-v5 files carried only `manual_games`
# (negative-id games). Custom cover photos are embedded as base64 on the
# customisations — the raw image_path is never exported.

BACKUP_VERSION = 5


def collect_backup_tables(c: sqlite3.Connection) -> dict:
    """Everything in a backup that comes straight from the database.

    The customisations still carry ``image_path`` so the caller can embed the
    photo (see embed_customisation_photos()), which then drops it.
    """
    members = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id")]

    # Full rows for every game. image_path is device-local, so it's dropped —
    # custom cover photos travel with the customisations below.
    games = [dict(r) for r in c.execute("SELECT * FROM games ORDER BY bgg_id")]
    for g in games:
        g.pop("image_path", None)

    collections = [dict(r) for r in c.execute("SELECT * FROM collections ORDER BY id")]
    game_collections = [dict(r) for r in c.execute(
        "SELECT game_id, collection_id FROM game_collections")]

    plays = [dict(r) for r in c.execute(
        """SELECT plays.*, games.name AS game_name
           FROM plays
           LEFT JOIN games ON games.bgg_id = plays.game_id
           ORDER BY plays.played_at DESC""")]

    loans = [dict(r) for r in c.execute(
        """SELECT loans.*, games.name AS game_name,
                  users.first_name, users.last_name
           FROM loans
           LEFT JOIN games ON games.bgg_id = loans.game_id
           LEFT JOIN users ON users.id = loans.user_id
           ORDER BY loans.checked_out_at DESC""")]

    customisations = [dict(r) for r in c.execute(
        """SELECT bgg_id, name, tags, is_favorite, has_insert,
                  my_comment, my_rating, best_players, is_cooperative,
                  manual_fields, image_path, own, bgg_status, is_unplayed
           FROM games
           WHERE tags IS NOT NULL OR is_favorite = 1 OR has_insert = 1
              OR my_comment IS NOT NULL OR my_rating IS NOT NULL
              OR best_players IS NOT NULL OR is_cooperative IS NOT NULL
              OR image_path IS NOT NULL OR own = 0 OR is_unplayed = 1
              OR (bgg_status IS NOT NULL AND bgg_status != 'own')""")]

    return {
        "members": members,
        "games": games,
        "collections": collections,
        "game_collections": game_collections,
        "plays": plays,
        "loans": loans,
        "customisations": customisations,
    }


def embed_customisation_photos(customisations: list) -> None:
    """Replace each customisation's local ``image_path`` with an embedded
    base64 ``photo_base64`` / ``photo_ext`` (in place). The path itself means
    nothing on another machine, so it is always removed."""
    for cu in customisations:
        path = cu.pop("image_path", None)
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as imgf:
                    cu["photo_base64"] = base64.b64encode(imgf.read()).decode("ascii")
                cu["photo_ext"] = os.path.splitext(path)[1].lstrip(".").lower() or "jpg"
            except OSError:
                pass  # Photo file unreadable -- skip it, don't fail the whole export.


def build_backup_payload(c: sqlite3.Connection) -> dict:
    """The full, ready-to-serialise version-5 backup document."""
    tables = collect_backup_tables(c)
    embed_customisation_photos(tables["customisations"])
    return {"version": BACKUP_VERSION, "exported_at": now_iso(), **tables}


def is_backup_payload(data) -> bool:
    """Loose sanity check that parsed JSON looks like a BGL backup (mobile
    requires `version` and `members`; an empty members list is fine)."""
    return (isinstance(data, dict) and bool(data.get("version"))
            and (data.get("members") is not None
                 or isinstance(data.get("games"), list)))


def restore_backup_tables(c: sqlite3.Connection, data: dict,
                          images_dir: Optional[Path] = None) -> dict:
    """Merge a parsed backup into the database (port of mobile's
    backupCore.restoreTables). Never overwrites a game row that is already
    here (a fresh BGG sync is newer); it only fills in missing games, then
    re-applies the user's own data on top. Safe to run repeatedly.

    Order: games, members (old id -> new id), collections (+ membership),
    plays, loans, customisations. Returns counts: games, collections, members,
    plays, loans, customisations, skipped (already here / not importable) and
    no_game (plays / loans / customisations whose game isn't in this library).

    images_dir: where embedded custom cover photos are written; None skips them.
    """
    counts = {"games": 0, "collections": 0, "members": 0, "plays": 0, "loans": 0,
              "customisations": 0, "skipped": 0, "no_game": 0}

    def game_exists(gid) -> bool:
        return gid is not None and c.execute(
            "SELECT 1 FROM games WHERE bgg_id = ?", (gid,)).fetchone() is not None

    # ── Games ────────────────────────────────────────────────────────────────
    # First, so everything below can find them. Columns come from the live
    # schema, so a backup from a different app version still imports the fields
    # both sides know about. Pre-v5 backups only carried manually added games
    # (negative bgg_id), under `manual_games`.
    game_cols = {row[1] for row in c.execute("PRAGMA table_info(games)")}
    incoming = data.get("games") if isinstance(data.get("games"), list)         else (data.get("manual_games") or [])
    for g in incoming:
        gid = g.get("bgg_id")
        if not isinstance(gid, int) or isinstance(gid, bool) or not g.get("name"):
            counts["skipped"] += 1
            continue
        if game_exists(gid):
            continue   # already here — not a skip, nothing lost
        cols = [k for k in g if k in game_cols and k != "image_path"]
        c.execute(
            f"INSERT INTO games ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            [g[k] for k in cols],
        )
        counts["games"] += 1

    # ── Members — map old ids -> local ids so loans/collections resolve ──────
    user_id_map: dict = {}
    for m in data.get("members") or []:
        row = c.execute(
            "SELECT id FROM users WHERE first_name = ? AND last_name = ?",
            (m.get("first_name"), m.get("last_name")),
        ).fetchone()
        if row:
            user_id_map[m.get("id")] = row[0]
            counts["skipped"] += 1
        else:
            cur = c.execute(
                "INSERT INTO users (first_name, last_name, bgg_username, created_at) "
                "VALUES (?, ?, ?, ?)",
                ((m.get("first_name") or "").strip(), (m.get("last_name") or "").strip(),
                 m.get("bgg_username") or None, m.get("created_at") or now_iso()),
            )
            user_id_map[m.get("id")] = cur.lastrowid
            counts["members"] += 1

    # ── Collections and which games are in them ──────────────────────────────
    coll_id_map: dict = {}
    for col in data.get("collections") or []:
        if col.get("bgg_username"):
            existing = c.execute("SELECT id FROM collections WHERE bgg_username = ?",
                                 (col["bgg_username"],)).fetchone()
        else:
            existing = c.execute(
                "SELECT id FROM collections WHERE name = ? AND bgg_username IS NULL",
                (col.get("name"),)).fetchone()
        if existing:
            coll_id_map[col.get("id")] = existing[0]
        else:
            owner = col.get("owner_user_id")
            cur = c.execute(
                "INSERT INTO collections (name, bgg_username, created_at, last_synced, "
                "owner_user_id) VALUES (?, ?, ?, ?, ?)",
                (col.get("name") or col.get("bgg_username") or "Collection",
                 col.get("bgg_username") or None, col.get("created_at") or now_iso(),
                 col.get("last_synced"),
                 user_id_map.get(owner) if owner is not None else None),
            )
            coll_id_map[col.get("id")] = cur.lastrowid
            counts["collections"] += 1
    for gc in data.get("game_collections") or []:
        cid = coll_id_map.get(gc.get("collection_id"))
        if cid is None or not game_exists(gc.get("game_id")):
            continue
        c.execute("INSERT OR IGNORE INTO game_collections (game_id, collection_id) "
                  "VALUES (?, ?)", (gc["game_id"], cid))

    # ── Plays ────────────────────────────────────────────────────────────────
    for p in data.get("plays") or []:
        if c.execute("SELECT 1 FROM plays WHERE game_id = ? AND played_at = ?",
                     (p.get("game_id"), p.get("played_at"))).fetchone():
            counts["skipped"] += 1
            continue
        if not game_exists(p.get("game_id")):
            counts["no_game"] += 1
            continue
        log_play(
            c, p["game_id"], p["played_at"],
            p.get("player_names") or "", p.get("winner") or "", p.get("notes") or "",
            duration_minutes=p.get("duration_minutes"), scores=p.get("scores"),
        )
        counts["plays"] += 1

    # ── Loans ────────────────────────────────────────────────────────────────
    for l in data.get("loans") or []:
        if c.execute("SELECT 1 FROM loans WHERE game_id = ? AND checked_out_at = ?",
                     (l.get("game_id"), l.get("checked_out_at"))).fetchone():
            counts["skipped"] += 1
            continue
        if not game_exists(l.get("game_id")):
            counts["no_game"] += 1
            continue
        uid = user_id_map.get(l.get("user_id"), l.get("user_id"))
        if uid is None or c.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
            # Borrower isn't in the file's member list — fall back to the name
            # carried on the loan row, else there's nobody to attach it to.
            match = find_user_by_name(c, l.get("first_name") or "", l.get("last_name") or "")
            if match is None:
                counts["skipped"] += 1
                continue
            uid = match["id"]
        c.execute(
            "INSERT INTO loans (game_id, user_id, checked_out_at, returned_at, due_date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (l["game_id"], uid, l["checked_out_at"],
             l.get("returned_at"), l.get("due_date"), l.get("notes")),
        )
        counts["loans"] += 1

    # ── Game customisations ──────────────────────────────────────────────────
    for cu in data.get("customisations") or []:
        if not game_exists(cu.get("bgg_id")):
            counts["no_game"] += 1
            continue
        image_path = None
        if cu.get("photo_base64") and images_dir is not None:
            try:
                ext = cu.get("photo_ext") or "jpg"
                images_dir.mkdir(parents=True, exist_ok=True)
                dest = images_dir / f"{cu['bgg_id']}.{ext}"
                dest.write_bytes(base64.b64decode(cu["photo_base64"]))
                image_path = str(dest)
            except (OSError, ValueError):
                pass  # Couldn't write the photo -- keep any existing one.
        c.execute(
            "UPDATE games SET tags=?, is_favorite=?, has_insert=?, "
            "my_comment=?, my_rating=?, best_players=?, is_cooperative=?, "
            "manual_fields=?, image_path=COALESCE(?, image_path), "
            "own=COALESCE(?, own), bgg_status=COALESCE(?, bgg_status), "
            "is_unplayed=COALESCE(?, is_unplayed) WHERE bgg_id=?",
            (cu.get("tags"), cu.get("is_favorite") or 0, cu.get("has_insert") or 0,
             cu.get("my_comment"), cu.get("my_rating"), cu.get("best_players"),
             cu.get("is_cooperative"), cu.get("manual_fields"), image_path,
             cu.get("own"), cu.get("bgg_status"),
             (1 if cu["is_unplayed"] else 0) if cu.get("is_unplayed") is not None else None,
             cu["bgg_id"]),
        )
        counts["customisations"] += 1

    # A restored mark must never contradict the play log.
    clear_unplayed_if_played(c)

    return counts


def summarize_import(counts: dict, sep: str = "\n") -> str:
    """Result text for the "Import complete" message (mirrors mobile's
    summarizeImport). *sep* joins the lines — "\n" for a dialog, ", " for a
    one-line flash message."""
    lines = [
        f"Games: +{counts['games']}",
        f"Collections: +{counts['collections']}",
        f"Friends: +{counts['members']}",
        f"Plays: +{counts['plays']}",
        f"Loans: +{counts['loans']}",
        f"Game details applied: {counts['customisations']}",
        f"Already here / skipped: {counts['skipped']}",
    ]
    n = counts["no_game"]
    if n > 0:
        lines.append(
            f"{n} play, loan or detail record{'s' if n != 1 else ''} "
            f"belong{'s' if n == 1 else ''} to games that are not in this "
            "library, so they were not imported. If this backup was made "
            "before backups included the game list, Sync with BoardGameGeek "
            "and then import it again."
        )
    return sep.join(lines)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
