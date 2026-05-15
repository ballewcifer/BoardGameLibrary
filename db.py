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

def upsert_game(c: sqlite3.Connection, g: dict) -> None:
    cols = [
        "bgg_id", "name", "year", "image_url", "thumbnail_url", "image_path",
        "min_players", "max_players", "min_playtime", "max_playtime",
        "playing_time", "min_age", "weight", "avg_rating", "my_rating",
        "description", "categories", "mechanics", "designers", "publishers",
        "best_players", "my_comment", "own", "last_synced", "is_expansion",
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


def list_games(c: sqlite3.Connection, search: str = "") -> list[sqlite3.Row]:
    if search:
        return c.execute(
            "SELECT * FROM games WHERE name LIKE ? ORDER BY name COLLATE NOCASE",
            (f"%{search}%",),
        ).fetchall()
    return c.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE").fetchall()


def get_game(c: sqlite3.Connection, bgg_id: int) -> Optional[sqlite3.Row]:
    return c.execute("SELECT * FROM games WHERE bgg_id = ?", (bgg_id,)).fetchone()


def delete_game(c: sqlite3.Connection, bgg_id: int) -> None:
    """Remove a game and all its related loans/plays (CASCADE handles FK rows)."""
    c.execute("DELETE FROM games WHERE bgg_id = ?", (bgg_id,))


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
    cur = c.execute(
        "INSERT INTO plays (game_id, played_at, player_names, winner, notes, duration_minutes, scores) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip(),
         duration_minutes, scores),
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
    duration_minutes: Optional[int] = None,
    scores: Optional[str] = None,
) -> None:
    c.execute(
        "UPDATE plays SET game_id=?, played_at=?, player_names=?, winner=?, notes=?, "
        "duration_minutes=?, scores=? WHERE id=?",
        (game_id, played_at, player_names.strip(), winner.strip(), notes.strip(),
         duration_minutes, scores, play_id),
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
        SELECT loans.id, loans.checked_out_at, loans.due_date,
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


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
