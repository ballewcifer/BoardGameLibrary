"""BoardGameGeek client.

Two ways to populate the library:

1. Import from BGG (File → Import from BGG…) — uses the built-in app token.
2. CSV import (File → Import collection CSV…) — no token needed.

Box / thumbnail images on BGG's CDN (cf.geekdo-images.com) are publicly
fetchable without authentication.
"""
from __future__ import annotations

import csv
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

BASE = "https://boardgamegeek.com/xmlapi2"
USER_AGENT = "BoardGameLibrary/0.1 (personal-use)"
# BGG returns 403 to non-browser User-Agents on its HTML pages.
# Use a real Chrome UA for page scraping only.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
THING_BATCH = 20

# ── Built-in application token ────────────────────────────────────────────────
# Register at https://boardgamegeek.com/applications to get a Bearer token,
# then paste it here.  This single token works for all users of the app.
BGG_APP_TOKEN: str = "3761c334-250c-41c9-bfbd-e67414e0d735"


def _ssl_ctx() -> ssl.SSLContext:
    """Return an SSL context with a reliable CA bundle.

    Loads the OS/system certificate store first (via create_default_context),
    then layers certifi's bundle on top via load_verify_locations so that
    both sources are trusted.  On Windows, create_default_context() pulls
    from the Windows Certificate Store (SChannel), so setting SSL_CERT_FILE
    has no effect — we must add certifi explicitly after the fact.
    """
    ctx = ssl.create_default_context()
    try:
        import certifi  # noqa: PLC0415
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ctx


@dataclass
class CollectionEntry:
    bgg_id: int
    name: str
    year: Optional[int]
    image_url: Optional[str]
    thumbnail_url: Optional[str]
    my_rating: Optional[float]
    my_comment: Optional[str]
    own: bool
    # Parsed from <stats> when stats=1 is included in the request
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    min_playtime: Optional[int] = None
    max_playtime: Optional[int] = None
    avg_rating: Optional[float] = None


@dataclass
class GameDetails:
    bgg_id: int
    name: str
    year: Optional[int] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    min_playtime: Optional[int] = None
    max_playtime: Optional[int] = None
    playing_time: Optional[int] = None
    min_age: Optional[int] = None
    weight: Optional[float] = None
    avg_rating: Optional[float] = None
    description: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    mechanics: list[str] = field(default_factory=list)
    designers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    best_players: Optional[str] = None
    my_rating: Optional[float] = None
    my_comment: Optional[str] = None
    is_expansion: bool = False


def _http_get(url: str, timeout: int = 30, token: Optional[str] = None) -> tuple[int, bytes]:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError(
                "BGG returned 401 Unauthorized. The XML API now requires a "
                "Bearer token from a registered application "
                "(https://boardgamegeek.com/applications)."
            ) from e
        raise


def _fetch_xml(url: str, *, token: Optional[str] = None, max_attempts: int = 10,
               backoff: float = 2.0,
               on_status: Optional[Callable[[str], None]] = None) -> ET.Element:
    """GET a BGG XML endpoint, retrying on HTTP 202 (queued)."""
    for attempt in range(1, max_attempts + 1):
        status, body = _http_get(url, token=token)
        if status == 200:
            return ET.fromstring(body)
        if status == 202:
            if on_status:
                on_status(f"BGG queued the request (attempt {attempt}/{max_attempts}); retrying...")
            time.sleep(backoff)
            continue
        raise RuntimeError(f"Unexpected HTTP {status} from {url}")
    raise TimeoutError(f"BGG kept returning 202 after {max_attempts} attempts: {url}")


def _f(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except ValueError:
        return None
    return f if f != 0 else None


def _i(value: Optional[str]) -> Optional[int]:
    f = _f(value)
    return int(f) if f is not None else None


def fetch_collection(
    username: str,
    *,
    own_only: bool = True,
    token: Optional[str] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> list[CollectionEntry]:
    params = {"username": username, "stats": "1"}
    if own_only:
        params["own"] = "1"
    url = f"{BASE}/collection?{urllib.parse.urlencode(params)}"
    if on_status:
        on_status(f"Fetching collection for {username}...")
    root = _fetch_xml(url, token=token, on_status=on_status)

    entries: list[CollectionEntry] = []
    for item in root.findall("item"):
        bgg_id = int(item.get("objectid", "0"))
        if not bgg_id:
            continue
        name_el = item.find("name")
        year_el = item.find("yearpublished")
        image_el = item.find("image")
        thumb_el = item.find("thumbnail")
        stats_el = item.find("stats")
        rating_el = item.find("./stats/rating")
        my_rating = rating_el.get("value") if rating_el is not None else None
        comment_el = item.find("comment")
        status_el = item.find("status")
        own = status_el is not None and status_el.get("own") == "1"

        # Parse player counts / playtime from <stats> (present when stats=1)
        min_players = max_players = min_playtime = max_playtime = None
        avg_rating = None
        if stats_el is not None:
            min_players  = _i(stats_el.get("minplayers"))
            max_players  = _i(stats_el.get("maxplayers"))
            min_playtime = _i(stats_el.get("minplaytime"))
            max_playtime = _i(stats_el.get("maxplaytime"))
            avg_el = stats_el.find("./rating/average")
            if avg_el is not None:
                avg_rating = _f(avg_el.get("value"))

        entries.append(CollectionEntry(
            bgg_id=bgg_id,
            name=(name_el.text or "").strip() if name_el is not None else f"#{bgg_id}",
            year=_i(year_el.text) if year_el is not None and year_el.text else None,
            image_url=_maybe_protocol(image_el.text) if image_el is not None else None,
            thumbnail_url=_maybe_protocol(thumb_el.text) if thumb_el is not None else None,
            my_rating=_f(my_rating) if my_rating not in ("N/A", None) else None,
            my_comment=(comment_el.text or "").strip() if comment_el is not None and comment_el.text else None,
            own=own,
            min_players=min_players,
            max_players=max_players,
            min_playtime=min_playtime,
            max_playtime=max_playtime,
            avg_rating=avg_rating,
        ))
    return entries


def import_from_username(
    username: str,
    *,
    token: Optional[str] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> list[GameDetails]:
    """Import an owned collection by BGG username.

    Requires a BGG Bearer token (register at boardgamegeek.com/applications).

    Step 1: fetch /collection — returns game list + image URLs + basic stats.
    Step 2: fetch /thing in batches — adds weight, categories, designers, best-at.
    """
    if on_status:
        on_status(f"Fetching collection for {username}…")
    entries = fetch_collection(username, token=token, on_status=on_status)
    if not entries:
        return []

    # Seed GameDetails from the collection response (image URLs already normalised).
    result: dict[int, GameDetails] = {}
    for e in entries:
        result[e.bgg_id] = GameDetails(
            bgg_id=e.bgg_id,
            name=e.name,
            year=e.year,
            image_url=e.image_url,
            thumbnail_url=e.thumbnail_url,
            min_players=e.min_players,
            max_players=e.max_players,
            min_playtime=e.min_playtime,
            max_playtime=e.max_playtime,
            avg_rating=e.avg_rating,
            my_rating=e.my_rating,
            my_comment=e.my_comment,
        )

    # Enrich with /thing details (weight, categories, designers, best-at, etc.).
    if on_status:
        on_status(f"Fetching full game details for {len(result)} games…")
    try:
        things = fetch_things(list(result.keys()), token=token, on_status=on_status)
        for d in things:
            existing = result.get(d.bgg_id)
            if existing is None:
                result[d.bgg_id] = d
                continue
            # Prefer /thing details but keep collection image URLs + user fields.
            d.image_url     = d.image_url     or existing.image_url
            d.thumbnail_url = d.thumbnail_url or existing.thumbnail_url
            d.my_rating     = existing.my_rating
            d.my_comment    = existing.my_comment
            result[d.bgg_id] = d
    except PermissionError:
        if on_status:
            on_status(
                f"Note: full details require an API token — imported {len(result)} games "
                "with basic info + images."
            )
    except Exception as exc:
        if on_status:
            on_status(f"Warning: could not fetch full details ({exc}). Using basic collection data.")

    return list(result.values())


def _parse_thing(item: ET.Element) -> GameDetails:
    bgg_id = int(item.get("id", "0"))
    is_expansion = item.get("type", "") == "boardgameexpansion"
    name = ""
    for n in item.findall("name"):
        if n.get("type") == "primary":
            name = n.get("value", "")
            break
    year_el = item.find("yearpublished")
    image_el = item.find("image")
    thumb_el = item.find("thumbnail")
    desc_el = item.find("description")
    minp = item.find("minplayers")
    maxp = item.find("maxplayers")
    minpt = item.find("minplaytime")
    maxpt = item.find("maxplaytime")
    pt = item.find("playingtime")
    minage = item.find("minage")

    weight = None
    avg = None
    avg_el = item.find("./statistics/ratings/average")
    if avg_el is not None:
        avg = _f(avg_el.get("value"))
    weight_el = item.find("./statistics/ratings/averageweight")
    if weight_el is not None:
        weight = _f(weight_el.get("value"))

    categories: list[str] = []
    mechanics: list[str] = []
    designers: list[str] = []
    publishers: list[str] = []
    for link in item.findall("link"):
        ltype = link.get("type", "")
        value = link.get("value", "")
        if ltype == "boardgamecategory":
            categories.append(value)
        elif ltype == "boardgamemechanic":
            mechanics.append(value)
        elif ltype == "boardgamedesigner":
            designers.append(value)
        elif ltype == "boardgamepublisher":
            publishers.append(value)

    best_players = _best_players_from_poll(item)

    return GameDetails(
        bgg_id=bgg_id,
        name=name,
        year=_i(year_el.get("value")) if year_el is not None else None,
        image_url=(image_el.text or None) if image_el is not None else None,
        thumbnail_url=(thumb_el.text or None) if thumb_el is not None else None,
        min_players=_i(minp.get("value")) if minp is not None else None,
        max_players=_i(maxp.get("value")) if maxp is not None else None,
        min_playtime=_i(minpt.get("value")) if minpt is not None else None,
        max_playtime=_i(maxpt.get("value")) if maxpt is not None else None,
        playing_time=_i(pt.get("value")) if pt is not None else None,
        min_age=_i(minage.get("value")) if minage is not None else None,
        weight=weight,
        avg_rating=avg,
        description=(desc_el.text or "").strip() if desc_el is not None and desc_el.text else None,
        categories=categories,
        mechanics=mechanics,
        designers=designers,
        publishers=publishers,
        best_players=best_players,
        is_expansion=is_expansion,
    )


def _best_players_from_poll(item: ET.Element) -> Optional[str]:
    """Return a comma-separated list of player counts the community rates 'Best'."""
    poll = item.find("./poll[@name='suggested_numplayers']")
    if poll is None:
        return None
    best_counts: list[tuple[int, str]] = []
    for results in poll.findall("results"):
        np = results.get("numplayers", "")
        best_votes = 0
        rec_votes = 0
        not_votes = 0
        for r in results.findall("result"):
            v = int(r.get("numvotes", "0"))
            if r.get("value") == "Best":
                best_votes = v
            elif r.get("value") == "Recommended":
                rec_votes = v
            elif r.get("value") == "Not Recommended":
                not_votes = v
        if best_votes > rec_votes and best_votes > not_votes and best_votes > 0:
            best_counts.append((best_votes, np))
    if not best_counts:
        return None
    best_counts.sort(reverse=True)
    return ", ".join(np for _, np in best_counts)


def fetch_things(
    ids: Iterable[int],
    *,
    token: Optional[str] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> list[GameDetails]:
    ids = [i for i in ids if i]
    if not ids:
        return []
    out: list[GameDetails] = []
    for start in range(0, len(ids), THING_BATCH):
        chunk = ids[start:start + THING_BATCH]
        if on_status:
            on_status(f"Fetching game details {start + 1}-{start + len(chunk)} of {len(ids)}...")
        url = f"{BASE}/thing?id={','.join(map(str, chunk))}&stats=1"
        root = _fetch_xml(url, token=token, on_status=on_status)
        for it in root.findall("item"):
            out.append(_parse_thing(it))
        time.sleep(0.5)  # be polite to BGG
    return out


def search_games(
    query: str,
    *,
    token: Optional[str] = None,  # unused — /xmlapi2/search is public
) -> list[tuple[int, str, Optional[int]]]:
    """Search BGG for board games matching *query*.

    Uses the official BGG XML API v2 /search endpoint which is public,
    stable, and does not require a Bearer token or a browser User-Agent.

    Returns a list of (bgg_id, name, year) tuples sorted by year descending
    so the most recent printing of a game appears first.
    """
    params = urllib.parse.urlencode({
        "query": query,
        "type": "boardgame,boardgameexpansion",
    })
    url = f"{BASE}/search?{params}"
    try:
        root = _fetch_xml(url)
    except Exception as exc:
        raise RuntimeError(f"BGG Search failed: {exc}") from exc

    results: list[tuple[int, str, Optional[int]]] = []
    for item in root.findall("item"):
        bgg_id = int(item.get("id", "0"))
        if not bgg_id:
            continue
        name = ""
        for n in item.findall("name"):
            if n.get("type") == "primary":
                name = n.get("value", "").strip()
                break
        if not name:
            continue
        year_el = item.find("yearpublished")
        year = _i(year_el.get("value")) if year_el is not None else None
        results.append((bgg_id, name, year))
    # Sort newest first as a tiebreaker (API results are already ranked by relevance)
    results.sort(key=lambda x: (-(x[2] or 0),))
    return results


# ---------- BGG play history (read) ----------

def fetch_plays(
    username: str,
    *,
    token: Optional[str] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """Fetch all plays logged by *username* on BGG.

    Paginates automatically (BGG returns 100 plays per page).
    Returns a list of dicts with keys:
        bgg_id, game_name, played_at (YYYY-MM-DD), quantity,
        player_names (comma-str), notes
    """
    plays: list[dict] = []
    page = 1
    while True:
        params = urllib.parse.urlencode({"username": username, "page": page})
        url = f"{BASE}/plays?{params}"
        if on_status:
            on_status(f"Fetching BGG plays page {page}…")
        try:
            root = _fetch_xml(url, token=token)
        except Exception as exc:
            raise RuntimeError(f"BGG plays fetch failed: {exc}") from exc

        items = root.findall("play")
        if not items:
            break
        for play in items:
            item_el = play.find("item")
            if item_el is None:
                continue
            bgg_id_str = item_el.get("objectid", "")
            try:
                bgg_id = int(bgg_id_str)
            except ValueError:
                continue
            game_name = item_el.get("name", "")
            played_at = play.get("date", "")
            quantity  = int(play.get("quantity", "1") or "1")
            comments_el = play.find("comments")
            notes = (comments_el.text or "").strip() if comments_el is not None else ""
            players_el = play.find("players")
            player_names = ""
            if players_el is not None:
                names = [
                    p.get("name", "").strip()
                    for p in players_el.findall("player")
                    if p.get("name", "").strip()
                ]
                player_names = ", ".join(names)
            for _ in range(max(quantity, 1)):
                plays.append({
                    "bgg_id":       bgg_id,
                    "game_name":    game_name,
                    "played_at":    played_at,
                    "player_names": player_names,
                    "notes":        notes,
                })
        # If fewer than 100 items returned we've hit the last page
        if len(items) < 100:
            break
        page += 1
    return plays


# ---------- BGG play logging (write path) ----------

def _bgg_login(username: str, password: str):
    """POST credentials to BGG and return (CookieJar, opener) on success.

    BGG's modern login endpoint accepts JSON and responds with a session cookie.
    Returns (None, None) if authentication fails.
    """
    import json as _json
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=_ssl_ctx()),
    )
    payload = _json.dumps({
        "credentials": {"username": username, "password": password},
    }).encode()
    req = urllib.request.Request(
        "https://boardgamegeek.com/login/api/v1",
        data=payload,
        headers={
            "User-Agent":   BROWSER_UA,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=15) as resp:
            if resp.status == 200:
                return jar, opener
    except Exception:
        pass
    return None, None


def log_play_to_bgg(
    username: str,
    password: str,
    bgg_id: int,
    played_at: str,
    player_names: str = "",
    notes: str = "",
) -> tuple[bool, str]:
    """Log a play to the user's BGG profile.

    Authenticates with BGG then POSTs to geekplay.php.
    Returns (success: bool, message: str).
    """
    import json as _json

    jar, opener = _bgg_login(username, password)
    if jar is None:
        return False, "BGG login failed — check username/password in Settings."

    players = [p.strip() for p in player_names.split(",") if p.strip()]

    # Build form data
    data: dict[str, str] = {
        "objectid":   str(bgg_id),
        "objecttype": "thing",
        "action":     "save",
        "playdate":   played_at[:10],   # YYYY-MM-DD
        "quantity":   "1",
        "ajax":       "1",
        "comments":   notes,
    }
    for i, name in enumerate(players):
        data[f"players[{i}][name]"] = name
        data[f"players[{i}][username]"] = ""

    req = urllib.request.Request(
        "https://boardgamegeek.com/geekplay.php",
        data=urllib.parse.urlencode(data).encode(),
        headers={
            "User-Agent":      BROWSER_UA,
            "Content-Type":    "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer":         f"https://boardgamegeek.com/boardgame/{bgg_id}",
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            result = _json.loads(body)
            play_id = result.get("playid")
            if play_id:
                return True, f"Logged to BGG (play #{play_id})"
            # BGG may return errors list
            errors = result.get("error") or result.get("errors") or "unknown error"
            return False, f"BGG rejected the play: {errors}"
    except Exception as exc:
        return False, f"BGG play log failed: {exc}"


# ---------- CSV import (the no-token path) ----------

def _pick(row: dict[str, str], *names: str) -> Optional[str]:
    """Return the first non-empty value among the given column names."""
    for n in names:
        v = row.get(n)
        if v is not None and v != "":
            return v
    return None


def _maybe_protocol(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    return url


def import_collection_csv(csv_path: Path) -> list[GameDetails]:
    """Parse a BGG 'Export collection' CSV file and return GameDetails for every
    row. The export's column set varies by year; we look up fields by several
    possible header names. Owned, want-to-buy, wishlist, etc. are all imported
    — the user chose what to include when they exported.
    """
    games: list[GameDetails] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            obj_id = _pick(row, "objectid", "objectID", "id")
            if not obj_id:
                continue
            try:
                bgg_id = int(obj_id)
            except ValueError:
                continue

            name = _pick(row, "objectname", "name", "originalname") or f"#{bgg_id}"
            year = _i(_pick(row, "yearpublished", "year_published", "year", "originalyear"))
            image_url = _maybe_protocol(_pick(row, "image"))
            thumb_url = _maybe_protocol(_pick(row, "thumbnail"))
            min_players = _i(_pick(row, "minplayers", "min_players"))
            max_players = _i(_pick(row, "maxplayers", "max_players"))
            playing_time = _i(_pick(row, "playingtime", "playing_time"))
            min_playtime = _i(_pick(row, "minplaytime", "min_playtime"))
            max_playtime = _i(_pick(row, "maxplaytime", "max_playtime"))
            min_age = _i(_pick(row, "minage", "min_age"))
            weight = _f(_pick(row, "avgweight", "weight"))
            avg_rating = _f(_pick(row, "average", "baverage", "avg_rating"))

            details = GameDetails(
                bgg_id=bgg_id,
                name=name,
                year=year,
                image_url=image_url,
                thumbnail_url=thumb_url,
                min_players=min_players,
                max_players=max_players,
                min_playtime=min_playtime,
                max_playtime=max_playtime,
                playing_time=playing_time,
                min_age=min_age,
                weight=weight,
                avg_rating=avg_rating,
            )
            details.my_rating = _f(_pick(row, "rating"))
            details.my_comment = _pick(row, "comment")
            games.append(details)
    return games


@dataclass
class PageData:
    """Data scraped from a BGG game page (no API token required)."""
    image_url: Optional[str] = None
    best_players: Optional[str] = None   # e.g. "3", "3-4", "2, 4"


def get_bgg_page_data(bgg_id: int, *, timeout: int = 15) -> PageData:
    """Scrape a BGG game page and return box-art URL + community best-at data.

    BGG game pages are publicly accessible without an API token.
    Both pieces of data come from a single HTTP request.
    """
    page_url = f"https://boardgamegeek.com/boardgame/{bgg_id}"
    try:
        req = urllib.request.Request(page_url, headers={
            "User-Agent":      BROWSER_UA,
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            html = resp.read(200000).decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(f"Could not fetch BGG page for #{bgg_id}: {exc}") from exc

    result = PageData()

    # ---- box-art image URL ----
    # __itemrep is the portrait box-art thumbnail (~246x300).
    m = re.search(
        r"https://cf\.geekdo-images\.com/[^\s\"'<>]+__itemrep[^\s\"'<>]+",
        html,
    )
    if m:
        result.image_url = m.group(0)
    else:
        # Fall back to og:image (landscape crop).
        for pat in (
            r'property=[^>]*og:image[^>]*content="([^"]+)"',
            r'content="([^"]+)"[^>]*property=[^>]*og:image',
        ):
            m = re.search(pat, html)
            if m:
                url = m.group(1)
                result.image_url = url if url.startswith("http") else ("https:" + url)
                break

    # ---- best-at player count from GEEK.geekitemPreload JSON ----
    # BGG embeds  item.polls.userplayers.best  as [{min, max}, …] in the page.
    # We use brace-counting to extract the full (large) JSON object reliably.
    m = re.search(r"GEEK\.geekitemPreload\s*=\s*(\{)", html)
    if m:
        try:
            import json as _json
            start = m.start(1)
            depth = 0
            raw_json = ""
            for i, ch in enumerate(html[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        raw_json = html[start : i + 1]
                        break
            preload = _json.loads(raw_json) if raw_json else {}
            best_list = (
                preload.get("item", preload)   # data lives under "item" key
                       .get("polls", {})
                       .get("userplayers", {})
                       .get("best", [])
            )
            parts: list[str] = []
            for entry in best_list:
                lo = entry.get("min")
                hi = entry.get("max")
                if lo is None:
                    continue
                if hi is None or hi == lo:
                    parts.append(str(lo))
                else:
                    parts.append(f"{lo}-{hi}")
            if parts:
                result.best_players = ", ".join(parts)
        except Exception:
            pass

    return result


def get_image_url_from_api(bgg_id: int) -> Optional[str]:
    """Fetch an image URL for a game via the BGG XML API.

    The /thing endpoint is public — no Bearer token required.
    Returns the full image URL, or None if unavailable.
    """
    url = f"{BASE}/thing?id={bgg_id}"
    try:
        status, body = _http_get(url)
        if status != 200:
            return None
        root = ET.fromstring(body)
        item = root.find("item")
        if item is None:
            return None
        for tag in ("image", "thumbnail"):
            el = item.find(tag)
            if el is not None and el.text and el.text.strip():
                return _maybe_protocol(el.text.strip())
    except Exception:
        pass
    return None


def fetch_game_details_from_page(bgg_id: int, *, fallback_name: str = "") -> Optional[GameDetails]:
    """Scrape full game details from a BGG game page without any API token.

    BGG embeds all game data as a JSON blob (GEEK.geekitemPreload) in every
    public game page.  This single request returns name, year, player counts,
    playtime, weight, description, categories, mechanics, designers, publishers,
    best-players, and an image URL — everything the XML API provides.
    Returns None on any error so callers can fall back gracefully.
    """
    import json as _json
    import html as _html

    page_url = f"https://boardgamegeek.com/boardgame/{bgg_id}"
    try:
        req = urllib.request.Request(page_url, headers={
            "User-Agent":      BROWSER_UA,
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        with urllib.request.urlopen(req, timeout=20, context=_ssl_ctx()) as resp:
            html_text = resp.read(500_000).decode("utf-8", errors="ignore")
    except Exception:
        return None

    # Extract the embedded JSON blob via brace-counting
    m = re.search(r"GEEK\.geekitemPreload\s*=\s*(\{)", html_text)
    if not m:
        return None
    try:
        start = m.start(1)
        depth = 0
        raw_json = ""
        for i, ch in enumerate(html_text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    raw_json = html_text[start: i + 1]
                    break
        if not raw_json:
            return None
        preload = _json.loads(raw_json)
        item = preload.get("item", preload)

        # ── basic fields ──────────────────────────────────────────────────────
        g_name = item.get("name") or fallback_name or f"#{bgg_id}"
        g_year = item.get("yearpublished")
        g_min_players  = item.get("minplayers")
        g_max_players  = item.get("maxplayers")
        g_min_playtime = item.get("minplaytime")
        g_max_playtime = item.get("maxplaytime")
        g_playing_time = item.get("playingtime")
        g_min_age      = item.get("minage")

        # Description: strip HTML tags and unescape HTML entities
        raw_desc = item.get("description") or ""
        raw_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()
        g_description = _html.unescape(raw_desc) or None

        # Expansion flag
        is_expansion = item.get("type", "boardgame") == "boardgameexpansion"

        # ── stats ─────────────────────────────────────────────────────────────
        stats = item.get("stats") or {}
        g_avg_rating = stats.get("average")
        g_weight     = stats.get("averageweight")

        # ── links (categories / mechanics / designers / publishers) ───────────
        links = item.get("links") or {}
        def _names(key):
            return [x.get("name", "") for x in links.get(key, []) if x.get("name")]
        g_categories = _names("boardgamecategory")
        g_mechanics  = _names("boardgamemechanic")
        g_designers  = _names("boardgamedesigner")
        g_publishers = _names("boardgamepublisher")

        # ── best-players from poll ────────────────────────────────────────────
        best_list = (item.get("polls") or {}).get("userplayers", {}).get("best", [])
        parts: list[str] = []
        for entry in best_list:
            lo, hi = entry.get("min"), entry.get("max")
            if lo is None:
                continue
            parts.append(str(lo) if (hi is None or hi == lo) else f"{lo}-{hi}")
        g_best_players = ", ".join(parts) or None

        # ── image URL ─────────────────────────────────────────────────────────
        images = item.get("images") or {}
        g_image_url: Optional[str] = None
        for key in ("square200", "previewthumb", "thumb", "medium", "large"):
            raw = images.get(key)
            if raw:
                g_image_url = raw if raw.startswith("http") else "https:" + raw
                break
        if not g_image_url:
            m2 = re.search(
                r"https://cf\.geekdo-images\.com/[^\s\"'<>]+__itemrep[^\s\"'<>]+",
                html_text,
            )
            if m2:
                g_image_url = m2.group(0)

        def _int(v):
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def _float(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        return GameDetails(
            bgg_id=bgg_id,
            name=g_name,
            year=_int(g_year),
            min_players=_int(g_min_players),
            max_players=_int(g_max_players),
            min_playtime=_int(g_min_playtime),
            max_playtime=_int(g_max_playtime),
            playing_time=_int(g_playing_time),
            min_age=_int(g_min_age),
            description=g_description,
            avg_rating=_float(g_avg_rating),
            weight=_float(g_weight),
            categories=g_categories,
            mechanics=g_mechanics,
            designers=g_designers,
            publishers=g_publishers,
            best_players=g_best_players,
            image_url=g_image_url,
            is_expansion=is_expansion,
        )
    except Exception:
        return None


# Keep old name as a thin alias so existing call-sites still work.
def get_bgg_image_url(bgg_id: int, *, timeout: int = 15) -> Optional[str]:
    return get_bgg_page_data(bgg_id, timeout=timeout).image_url


def download_image(url: str, dest: Path, *, timeout: int = 30) -> Path:
    """Download an image to dest. Returns dest."""
    if not url:
        raise ValueError("No URL provided")
    if url.startswith("//"):
        url = "https:" + url
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp, \
            open(dest, "wb") as f:
        f.write(resp.read())
    return dest


if __name__ == "__main__":
    import sys

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    user = sys.argv[1] if len(sys.argv) > 1 else "Ballewcifer"
    coll = fetch_collection(user, on_status=log)
    print(f"Got {len(coll)} owned items.")
    for entry in coll[:5]:
        print(f"  {entry.bgg_id}: {entry.name} ({entry.year})")
