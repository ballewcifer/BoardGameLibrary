"""BoardGameGeek client.

Two ways to populate the library:

1. CSV import (works without an API token).
   On BGG: open your collection page → "Export collection" → CSV.
   Pass the file path to `import_collection_csv`.

2. XMLAPI2 (requires a registered-application Bearer token as of late 2025).
   Register at https://boardgamegeek.com/applications, then call
   `fetch_collection` / `fetch_things` with `token=...`.

Box / thumbnail images on BGG's CDN (cf.geekdo-images.com) are still
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
    token: Optional[str] = None,
) -> list[tuple[int, str, Optional[int]]]:
    """Search BGG for board games matching *query*.

    Returns a list of (bgg_id, name, year) tuples sorted by year descending
    so the most recent version of a game appears first.
    """
    url = f"{BASE}/search?{urllib.parse.urlencode({'query': query, 'type': 'boardgame'})}"
    root = _fetch_xml(url, token=token)
    results: list[tuple[int, str, Optional[int]]] = []
    for item in root.findall("item"):
        bgg_id = int(item.get("id", "0") or "0")
        if not bgg_id:
            continue
        name_el = item.find("name")
        year_el = item.find("yearpublished")
        name = name_el.get("value", "").strip() if name_el is not None else f"#{bgg_id}"
        year = _i(year_el.get("value")) if year_el is not None else None
        results.append((bgg_id, name, year))
    results.sort(key=lambda x: (-(x[2] or 0), x[1].lower()))
    return results


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
