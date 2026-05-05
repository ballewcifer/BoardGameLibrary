"""SQLite storage for the board game library."""
from __future__ import annotations

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
    has_insert      INTEGER DEFAULT 0
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
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS plays (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(bgg_id) ON DELETE CASCADE,
    played_at       TEXT NOT NULL,
    player_names    TEXT,
    winner          TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_loans_open
    ON loans(game_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_loans_user ON loans(user_id);
CREATE INDEX IF NOT EXISTS idx_plays_game ON plays(game_id);

CREATE TABLE IF NOT EXISTS collections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT,
    display_name TEXT    NOT NULL,
    color        TEXT    NOT NULL DEFAULT '#2471a3'
);

CREATE TABLE IF NOT EXISTS collection_games (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    bgg_id        INTEGER NOT NULL REFERENCES games(bgg_id)   ON DELETE CASCADE,
    PRIMARY KEY (collection_id, bgg_id)
);

CREATE INDEX IF NOT EXISTS idx_cg_collection ON collection_games(collection_id);
CREATE INDEX IF NOT EXISTS idx_cg_game       ON collection_games(bgg_id);
"""

# Columns added after the initial release — applied via ALTER TABLE so
# existing databases are updated without losing data.
MIGRATIONS = [
    "ALTER TABLE games ADD COLUMN is_favorite INTEGER DEFAULT 0",
    "ALTER TABLE games ADD COLUMN has_insert   INTEGER DEFAULT 0",
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

        # Data migration: if collections table is empty but games exist,
        # create a default "My Collection" containing all current games.
        col_count = c.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        if col_count == 0:
            game_count = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            if game_count > 0:
                cur = c.execute(
                    "INSERT INTO collections (display_name, color) VALUES (?, ?)",
                    ("My Collection", "#2471a3"),
                )
                col_id = cur.lastrowid
                c.execute(
                    "INSERT OR IGNORE INTO collection_games (collection_id, bgg_id) "
                    "SELECT ?, bgg_id FROM games",
                    (col_id,),
                )


# ---------- games ----------

def upsert_game(c: sqlite3.Connection, g: dict) -> None:
    cols = [
        "bgg_id", "name", "year", "image_url", "thumbnail_url", "image_path",
        "min_players", "max_players", "min_playtime", "max_playtime",
        "playing_time", "min_age", "weight", "avg_rating", "my_rating",
        "description", "categories", "mechanics", "designers", "publishers",
        "best_players", "my_comment", "own", "last_synced",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    # Don't overwrite is_favorite / has_insert on re-sync.
    updates = ", ".join(f"{col}=excluded.{col}" for col in cols if col != "bgg_id")
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


def list_games(
    c: sqlite3.Connection,
    search: str = "",
    collection_filter = "all",   # "all" | "shared" | ("col", id) | ("unique", id)
) -> list[sqlite3.Row]:
    like = f"%{search}%"
    base = """
        SELECT games.*,
               GROUP_CONCAT(cg.collection_id) AS owned_by
        FROM games
        JOIN collection_games cg ON cg.bgg_id = games.bgg_id
        {where}
        GROUP BY games.bgg_id
        {having}
        ORDER BY games.name COLLATE NOCASE
    """
    if collection_filter == "all":
        sql = base.format(where="WHERE games.name LIKE ?", having="")
        return c.execute(sql, (like,)).fetchall()
    elif collection_filter == "shared":
        sql = base.format(
            where="WHERE games.name LIKE ?",
            having="HAVING COUNT(DISTINCT cg.collection_id) >= (SELECT COUNT(*) FROM collections)",
        )
        return c.execute(sql, (like,)).fetchall()
    elif isinstance(collection_filter, tuple) and collection_filter[0] == "col":
        col_id = collection_filter[1]
        sql = base.format(
            where="WHERE cg.collection_id = ? AND games.name LIKE ?",
            having="",
        )
        return c.execute(sql, (col_id, like)).fetchall()
    elif isinstance(collection_filter, tuple) and collection_filter[0] == "unique":
        col_id = collection_filter[1]
        # Games in this collection that are NOT in any other collection
        sql = base.format(
            where="WHERE cg.collection_id = ? AND games.name LIKE ?",
            having="""HAVING COUNT(DISTINCT cg2.collection_id) = 0""",
        ).replace(
            "JOIN collection_games cg ON cg.bgg_id = games.bgg_id",
            "JOIN collection_games cg ON cg.bgg_id = games.bgg_id\n"
            "        LEFT JOIN collection_games cg2 ON cg2.bgg_id = games.bgg_id AND cg2.collection_id != ?",
        )
        return c.execute(sql, (col_id, like, col_id)).fetchall()
    else:
        # Fallback — return all
        sql = base.format(where="WHERE games.name LIKE ?", having="")
        return c.execute(sql, (like,)).fetchall()


def get_game(c: sqlite3.Connection, bgg_id: int) -> Optional[sqlite3.Row]:
    return c.execute("SELECT * FROM games WHERE bgg_id = ?", (bgg_id,)).fetchone()


# ---------- collections ----------

def list_collections(c: sqlite3.Connection) -> list[sqlite3.Row]:
    return c.execute("SELECT * FROM collections ORDER BY id").fetchall()


def get_collection(c: sqlite3.Connection, col_id: int) -> Optional[sqlite3.Row]:
    return c.execute("SELECT * FROM collections WHERE id = ?", (col_id,)).fetchone()


def add_collection(
    c: sqlite3.Connection,
    display_name: str,
    color: str = "#2471a3",
    username: str = "",
) -> int:
    cur = c.execute(
        "INSERT INTO collections (display_name, color, username) VALUES (?, ?, ?)",
        (display_name.strip(), color, username.strip()),
    )
    return cur.lastrowid


def rename_collection(c: sqlite3.Connection, col_id: int, display_name: str) -> None:
    c.execute(
        "UPDATE collections SET display_name = ? WHERE id = ?",
        (display_name.strip(), col_id),
    )


def set_collection_color(c: sqlite3.Connection, col_id: int, color: str) -> None:
    c.execute("UPDATE collections SET color = ? WHERE id = ?", (color, col_id))


def delete_collection(c: sqlite3.Connection, col_id: int) -> None:
    # collection_games rows are cascade-deleted by FK
    c.execute("DELETE FROM collections WHERE id = ?", (col_id,))


def add_game_to_collection(c: sqlite3.Connection, col_id: int, bgg_id: int) -> None:
    c.execute(
        "INSERT OR IGNORE INTO collection_games (collection_id, bgg_id) VALUES (?, ?)",
        (col_id, bgg_id),
    )


def remove_game_from_collection(c: sqlite3.Connection, col_id: int, bgg_id: int) -> None:
    c.execute(
        "DELETE FROM collection_games WHERE collection_id = ? AND bgg_id = ?",
        (col_id, bgg_id),
    )


def get_game_collection_ids(c: sqlite3.Connection, bgg_id: int) -> list[int]:
    rows = c.execute(
        "SELECT collection_id FROM collection_games WHERE bgg_id = ?", (bgg_id,)
    ).fetchall()
    return [r["collection_id"] for r in rows]


def collection_game_count(c: sqlite3.Connection, col_id: int) -> int:
    return c.execute(
        "SELECT COUNT(*) FROM collection_games WHERE collection_id = ?", (col_id,)
    ).fetchone()[0]


def get_or_create_default_collection(c: sqlite3.Connection) -> int:
    """Return the id of the first collection, creating 'My Collection' if none exist."""
    row = c.execute("SELECT id FROM collections ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    cur = c.execute(
        "INSERT INTO collections (display_name, color) VALUES (?, ?)",
        ("My Collection", "#2471a3"),
    )
    return cur.lastrowid


# ---------- users ----------

def add_user(c: sqlite3.Connection, first_name: str, last_name: str) -> int:
    cur = c.execute(
        "INSERT INTO users (first_name, last_name, created_at) VALUES (?, ?, ?)",
        (first_name.strip(), last_name.strip(), now_iso()),
    )
    return cur.lastrowid


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


def check_out(c: sqlite3.Connection, bgg_id: int, user_id: int, notes: str = "") -> int:
    if open_loan_for_game(c, bgg_id) is not None:
        raise ValueError("Game is already checked out.")
    cur = c.execute(
        "INSERT INTO loans (game_id, user_id, checked_out_at, notes) VALUES (?, ?, ?, ?)",
        (bgg_id, user_id, now_iso(), notes),
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

def log_play(
    c: sqlite3.Connection,
    game_id: int,
    played_at: str,
    player_names: str = "",
    winner: str = "",
    notes: str = "",
) -> int:
    cur = c.execute(
        "INSERT INTO plays (game_id, played_at, player_names, winner, notes) VALUES (?, ?, ?, ?, ?)",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip()),
    )
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
) -> None:
    c.execute(
        "UPDATE plays SET game_id=?, played_at=?, player_names=?, winner=?, notes=? WHERE id=?",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip(), play_id),
    )


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


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
