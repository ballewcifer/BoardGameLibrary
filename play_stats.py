"""Play statistics for the Plays tab's Stats view. Pure functions over play rows
(anything with game_id, game_name, played_at, player_names, winner), so they can be
tested without a database. Mirrors the mobile app's lib/playStats.ts."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MIN_RANKED_PLAYS = 3


def _day(p) -> str:
    return (p["played_at"] or "")[:10]


def period_start(period: str, today: Optional[date] = None) -> Optional[str]:
    """First day (YYYY-MM-DD) included in 'all' | 'year' | '30d'; None means all time."""
    today = today or date.today()
    if period == "year":
        return f"{today.year}-01-01"
    if period == "30d":
        return (today - timedelta(days=29)).isoformat()
    return None


def plays_in_period(plays, period: str, today: Optional[date] = None) -> list:
    since = period_start(period, today)
    return [p for p in plays if _day(p) >= since] if since else list(plays)


def most_played_games(plays) -> list[dict]:
    """Every game with at least one play, most played first (ties: most recent, then name)."""
    games: dict[int, dict] = {}
    for p in plays:
        day = _day(p)
        cur = games.get(p["game_id"])
        if cur:
            cur["count"] += 1
            cur["last_played"] = max(cur["last_played"], day)
        else:
            games[p["game_id"]] = {"game_id": p["game_id"], "name": p["game_name"] or "Unknown game",
                                   "count": 1, "last_played": day}
    out = list(games.values())
    out.sort(key=lambda g: g["name"].lower())
    out.sort(key=lambda g: g["last_played"], reverse=True)
    out.sort(key=lambda g: g["count"], reverse=True)
    return out


def player_records(plays) -> list[dict]:
    """Win rate per player. Only plays with a recorded winner other than "All" count:
    "All" is a co-op result and a blank winner means nothing was recorded. Names are
    matched case-insensitively."""
    records: dict[str, dict] = {}
    for p in plays:
        winner = (p["winner"] or "").strip().lower()
        if not winner or winner == "all":
            continue
        seen: set[str] = set()
        for raw in (p["player_names"] or "").split(","):
            name = raw.strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            rec = records.setdefault(key, {"name": name, "plays": 0, "wins": 0, "rate": 0.0})
            rec["plays"] += 1
            if key == winner:
                rec["wins"] += 1
    out = list(records.values())
    for r in out:
        r["rate"] = r["wins"] / r["plays"]
    out.sort(key=lambda r: (-r["rate"], -r["wins"], -r["plays"], r["name"].lower()))
    return out


def plays_by_month(plays, months: int = 12, today: Optional[date] = None) -> list[dict]:
    """Plays per calendar month for the last `months` months, newest first (empty months included)."""
    today = today or date.today()
    counts: dict[str, int] = {}
    for p in plays:
        key = _day(p)[:7]
        if key:
            counts[key] = counts.get(key, 0) + 1
    out = []
    y, m = today.year, today.month
    for _ in range(months):
        key = f"{y}-{m:02d}"
        out.append({"key": key, "label": f"{MONTHS[m - 1]} {y}", "count": counts.get(key, 0)})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def plays_this_year(plays, today: Optional[date] = None) -> int:
    return len(plays_in_period(plays, "year", today))
