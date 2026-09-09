"""Board Game Library — Flask web app.

Reuses db.py, bgg.py, config.py, and paths.py from the parent directory.
Run with:  python web/app.py
Then open  http://localhost:5000  on any device on the same Wi-Fi.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys
import threading
from datetime import datetime
from pathlib import Path

# ── Pull in the shared library modules ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import bgg as _bgg
import config as _config
from paths import IMAGES_DIR

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort, Response,
)

app = Flask(__name__)
app.secret_key = "bgl-flask-secret-2025"

# ── Ensure the database is ready ──────────────────────────────────────────────
db.init_db()
# Backfill an existing single-collection library into one named collection
with db.connect() as _c:
    _u = _config.load().get("bgg_username", "")
    db.ensure_collection_migration(_c, default_username=_u, default_name=_u or "My Collection")

# ── Background sync state ─────────────────────────────────────────────────────
_sync_lock   = threading.Lock()
_sync_status = {"running": False, "message": "Idle", "error": None}


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _settings():
    return _config.load()


def _row_to_dict(row):
    """Convert sqlite3.Row → plain dict (safe to pass to jsonify / templates)."""
    if row is None:
        return None
    return dict(zip(row.keys(), tuple(row)))


@app.template_filter("usdate")
def _usdate(iso):
    """Format an ISO date/timestamp for display as US-style MM/DD/YYYY, no time."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%m/%d/%Y")
    except ValueError:
        return iso


# ═══════════════════════════════════════════════════════════════════════════════
# Image serving
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/img/<int:bgg_id>")
def game_image(bgg_id):
    with db.connect() as c:
        game = db.get_game(c, bgg_id)
    if game and game["image_path"] and Path(game["image_path"]).exists():
        return send_file(game["image_path"])
    abort(404)


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    with db.connect() as c:
        summary     = db.stats_summary(c)
        checked_out = db.currently_checked_out(c)
        recent      = [_row_to_dict(r) for r in db.recent_plays(c, limit=8)]
        top_games   = [_row_to_dict(r) for r in db.top_games_by_plays(c, limit=5)]
        top_wins    = [_row_to_dict(r) for r in db.top_winners(c, limit=5)]
        checked_out = [_row_to_dict(r) for r in checked_out]

    today = datetime.now().date().isoformat()
    for loan in checked_out:
        loan["overdue"] = bool(loan.get("due_date") and loan["due_date"] < today)

    return render_template("dashboard.html",
                           summary=summary,
                           checked_out=checked_out,
                           recent=recent,
                           top_games=top_games,
                           top_wins=top_wins,
                           today=today)


# ═══════════════════════════════════════════════════════════════════════════════
# Games
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/games")
def games():
    q          = request.args.get("q", "").strip()
    tag_filter = request.args.get("tag", "")
    status     = request.args.get("status", "all")   # all | available | out | favs
    coop       = request.args.get("coop", "any")     # any | coop | competitive
    bstatus    = request.args.get("bstatus", "owned")   # owned | all | a bgg.STATUS_FLAGS value
    show_exp   = request.args.get("exp", "") == "1"
    collection = request.args.get("collection", "all")
    compare    = request.args.get("compare", "off")          # off | shared | only | diff
    compare_other_raw = request.args.get("compare_other", "")

    status_param = None if bstatus == "owned" else bstatus
    with db.connect() as c:
        rows      = db.list_games(c, search=q, status=status_param)
        open_loans = {r["game_id"]: _row_to_dict(r)
                      for r in db.currently_checked_out(c)}
        play_cts   = db.play_counts(c)
        all_tags   = db.all_tags(c)
        collections = [_row_to_dict(r) for r in db.list_collections(c) if r["game_count"] > 0]
        gc_map     = db.game_collection_map(c)
        members    = [_row_to_dict(r) for r in db.list_users(c)]

    member_name = {u["id"]: f"{u['first_name']} {u['last_name']}".strip() for u in members}
    for col in collections:
        col["owner_name"] = member_name.get(col.get("owner_user_id"))

    coll_ids = {col["id"] for col in collections}
    multi = len(collections) >= 2

    def _to_cid(v):
        try:
            cid = int(v)
        except (TypeError, ValueError):
            return None
        return cid if cid in coll_ids else None

    active_cid = None if collection in ("", "all") else _to_cid(collection)
    other_cid  = _to_cid(compare_other_raw)
    if not multi:
        active_cid, compare, other_cid = None, "off", None
    elif compare in ("only", "diff") and active_cid is None and collections:
        active_cid = collections[0]["id"]   # these modes need a specific library

    games_list = []
    for g in rows:
        gd = _row_to_dict(g)
        gd["play_count"] = play_cts.get(g["bgg_id"], 0)
        gd["loan"]       = open_loans.get(g["bgg_id"])

        if not show_exp and g["is_expansion"]:
            continue
        if tag_filter:
            tags = [t.strip() for t in (g["tags"] or "").split(",") if t.strip()]
            if tag_filter not in tags:
                continue
        if status == "available" and g["bgg_id"] in open_loans:
            continue
        if status == "out" and g["bgg_id"] not in open_loans:
            continue
        if status == "favs" and not g["is_favorite"]:
            continue
        if coop == "coop" and g["is_cooperative"] != 1:
            continue
        if coop == "competitive" and g["is_cooperative"] != 0:
            continue

        # collection tab / comparison filter
        if multi:
            member = gc_map.get(g["bgg_id"], set())
            if compare == "shared":
                if not coll_ids <= member:
                    continue
            elif compare == "only":
                if active_cid is None or member != {active_cid}:
                    continue
            elif compare == "diff":
                if active_cid is not None and other_cid is not None \
                        and not (active_cid in member and other_cid not in member):
                    continue
            elif active_cid is not None and active_cid not in member:
                continue

        games_list.append(gd)

    return render_template("games.html",
                           games=games_list,
                           q=q,
                           tag_filter=tag_filter,
                           status=status,
                           coop=coop,
                           bstatus=bstatus,
                           bgg_status_labels=_bgg.STATUS_LABELS,
                           bgg_status_flags=_bgg.STATUS_FLAGS,
                           show_exp=show_exp,
                           all_tags=all_tags,
                           collections=collections,
                           members=members,
                           multi=multi,
                           active_collection=active_cid,
                           compare=compare,
                           compare_other=other_cid)


@app.route("/collections/claim", methods=["POST"])
def claim_collection():
    """Claim a collection for a member (or release it with user_id empty)."""
    cid = request.form.get("collection_id", type=int)
    uid = request.form.get("user_id", type=int)   # None/0 → release
    if not cid:
        flash("No collection selected.", "error")
        return redirect(url_for("games"))
    with db.connect() as c:
        db.claim_collection(c, cid, uid or None)
    flash("Collection ownership updated.", "success")
    return redirect(url_for("games"))


@app.route("/api/random_game")
def api_random_game():
    """Return a random game matching the given criteria, or {game: null}."""
    players    = request.args.get("players", "Any")
    max_time   = request.args.get("max_time", "Any")     # 30|60|90|120|Any
    complexity = request.args.get("complexity", "Any")   # light|medium|heavy|Any
    coop       = request.args.get("coop", "Any")         # coop|competitive|Any
    available  = request.args.get("available", "1") == "1"
    collection = request.args.get("collection", "all")

    with db.connect() as c:
        rows        = db.list_games(c)
        open_loans  = {r["game_id"] for r in db.currently_checked_out(c)}
        collections = [r for r in db.list_collections(c) if r["game_count"] > 0]
        gc_map      = db.game_collection_map(c)

    coll_ids = {col["id"] for col in collections}
    multi    = len(collections) >= 2
    try:
        active_cid = int(collection) if collection not in ("", "all") else None
    except ValueError:
        active_cid = None
    if active_cid not in coll_ids:
        active_cid = None

    def matches(g) -> bool:
        if available and g["bgg_id"] in open_loans:
            return False
        if multi and active_cid is not None \
                and active_cid not in gc_map.get(g["bgg_id"], set()):
            return False
        if players != "Any":
            mn, mx = g["min_players"], g["max_players"]
            if players == "8+":
                if not mx or mx < 8:
                    return False
            else:
                n = int(players)
                lo = mn if mn else 1
                hi = mx if mx else mn
                if not hi or not (lo <= n <= hi):
                    return False
        if max_time != "Any":
            lim = int(max_time)
            pt = g["playing_time"] or g["max_playtime"] or g["min_playtime"]
            if pt is None or pt > lim:
                return False
        if complexity != "Any":
            w = g["weight"]
            if w is None:
                return False
            if complexity == "light"  and not (1.0 <= w <= 2.0):
                return False
            if complexity == "medium" and not (2.0 < w <= 3.0):
                return False
            if complexity == "heavy"  and not (w > 3.0):
                return False
        if coop == "coop" and g["is_cooperative"] != 1:
            return False
        if coop == "competitive" and g["is_cooperative"] != 0:
            return False
        return True

    pool = [g for g in rows if matches(g)]
    if not pool:
        return jsonify({"game": None})
    g  = random.choice(pool)
    gd = _row_to_dict(g)
    gd["checked_out"] = g["bgg_id"] in open_loans
    return jsonify({"game": gd})


@app.route("/collections/clear", methods=["POST"])
def clear_collections():
    """Clear the selected collections; games kept only by them are deleted."""
    ids = [int(i) for i in request.form.getlist("collection_ids") if i.isdigit()]
    if not ids:
        flash("No collections selected.", "error")
        return redirect(url_for("games"))
    with db.connect() as c:
        # Collections synced from BGG are looked up (and recreated if
        # missing) by username -- clearing one without also forgetting its
        # username would have the next sync silently bring it right back.
        placeholders = ",".join("?" * len(ids))
        cleared_usernames = [r["bgg_username"] for r in c.execute(
            f"SELECT bgg_username FROM collections WHERE id IN ({placeholders})", ids)]
        deleted = db.clear_collections(c, ids)
        s = _config.load()
        changed = False
        # If the device owner's collection was just cleared, drop the claim so a
        # new collection can be claimed.
        mid = s.get("claimed_member_id")
        if mid and not db.owned_collection_ids(c, mid):
            s.pop("claimed_member_id", None)
            changed = True
        username = s.get("bgg_username")
        if username and username in cleared_usernames:
            s["bgg_username"] = ""
            changed = True
        if changed:
            _config.save(s)
    for gid in deleted:
        for p in IMAGES_DIR.glob(f"{gid}.*"):
            try:
                p.unlink()
            except OSError:
                pass
    flash(f"Cleared {len(ids)} collection{'s' if len(ids) != 1 else ''}; "
          f"deleted {len(deleted)} game{'s' if len(deleted) != 1 else ''}.", "success")
    return redirect(url_for("games"))


@app.route("/games/<int:bgg_id>")
def game_detail(bgg_id):
    with db.connect() as c:
        game = _row_to_dict(db.get_game(c, bgg_id))
        if not game:
            abort(404)
        loan      = _row_to_dict(db.open_loan_for_game(c, bgg_id))
        plays     = [_row_to_dict(r) for r in db.list_plays(c, game_id=bgg_id)]
        stats     = db.game_play_stats(c, bgg_id)
        # Only members allowed to borrow this game (owners of a claimed
        # collection that contains it, plus members who claimed nothing).
        allowed   = db.members_allowed_to_checkout(c, bgg_id)
        users     = [_row_to_dict(r) for r in db.list_users(c) if r["id"] in allowed]
        # If this device's owner has claimed a collection, only their own games
        # may be checked out here.
        my_id = _config.load().get("claimed_member_id")
        can_checkout_here = (not my_id) or db.user_can_checkout(c, my_id, bgg_id)
        base_game = _row_to_dict(db.get_game(c, game["base_game_id"])) if game.get("base_game_id") else None
        owned_expansions = [_row_to_dict(r) for r in db.list_expansions_of(c, bgg_id)]

    today = datetime.now().date().isoformat()
    if loan:
        loan["overdue"] = bool(loan.get("due_date") and loan["due_date"] < today)

    return render_template("game_detail.html",
                           game=game,
                           loan=loan,
                           plays=plays,
                           stats=stats,
                           users=users,
                           can_checkout_here=can_checkout_here,
                           today=today,
                           base_game=base_game,
                           owned_expansions=owned_expansions,
                           bgg_status_labels=_bgg.STATUS_LABELS,
                           bgg_status_flags=_bgg.STATUS_FLAGS)


# ── Checkout ──────────────────────────────────────────────────────────────────

@app.route("/games/<int:bgg_id>/checkout", methods=["POST"])
def checkout(bgg_id):
    name     = request.form.get("friend_name", "").strip()
    due_date = request.form.get("due_date", "").strip() or None
    notes    = request.form.get("notes", "").strip()
    if not name:
        flash("Please select or type a friend.", "error")
        return redirect(url_for("game_detail", bgg_id=bgg_id))
    try:
        with db.connect() as c:
            # New name, not a current friend — auto-create them, same as
            # logging a play with a new player name does.
            db.ensure_players_as_members(c, name)
            match = next(
                (u for u in db.list_users(c)
                 if f"{u['first_name']} {u['last_name']}".strip().casefold() == name.casefold()),
                None)
            user_id = match["id"]
            if not db.user_can_checkout(c, user_id, bgg_id):
                flash("That friend has claimed a collection and can only check out "
                      "games from it.", "error")
                return redirect(url_for("game_detail", bgg_id=bgg_id))
            db.check_out(c, bgg_id, user_id, notes=notes, due_date=due_date)
        flash("Checked out successfully.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(request.referrer or url_for("games"))


@app.route("/games/<int:bgg_id>/checkin", methods=["POST"])
def checkin(bgg_id):
    try:
        with db.connect() as c:
            db.check_in(c, bgg_id)
        flash("Checked in successfully.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(request.referrer or url_for("games"))


# ── Favorite / tag ────────────────────────────────────────────────────────────

@app.route("/games/<int:bgg_id>/favorite", methods=["POST"])
def toggle_favorite(bgg_id):
    with db.connect() as c:
        game = db.get_game(c, bgg_id)
        if game:
            db.set_favorite(c, bgg_id, not bool(game["is_favorite"]))
    return redirect(request.referrer or url_for("games"))


@app.route("/games/<int:bgg_id>/update", methods=["POST"])
def update_game(bgg_id):
    best_players = request.form.get("best_players", "").strip() or None
    has_insert   = 1 if request.form.get("has_insert") else 0
    my_rating_s  = request.form.get("my_rating", "").strip()
    try:
        my_rating = int(my_rating_s) if my_rating_s else None
    except ValueError:
        my_rating = None
    tags       = request.form.get("tags", "").strip()
    my_comment = request.form.get("my_comment", "").strip() or None
    coop       = {"coop": 1, "competitive": 0}.get(request.form.get("is_cooperative", ""))
    status     = request.form.get("bgg_status", "own")
    if status not in _bgg.STATUS_FLAGS:
        status = "own"
    own = 1 if status == "own" else 0
    with db.connect() as c:
        c.execute(
            "UPDATE games SET best_players=?, my_rating=?, my_comment=?, is_cooperative=?, "
            "bgg_status=?, own=? WHERE bgg_id=?",
            (best_players, my_rating, my_comment, coop, status, own, bgg_id),
        )
        db.set_tags(c, bgg_id, tags)
        db.set_insert(c, bgg_id, bool(has_insert))
    flash("Game updated.", "success")
    return redirect(url_for("game_detail", bgg_id=bgg_id))


@app.route("/games/bulk_update", methods=["POST"])
def bulk_update_games():
    bgg_ids = request.form.getlist("bgg_ids", type=int)
    has_insert = request.form.get("has_insert") == "1"
    if bgg_ids:
        with db.connect() as c:
            for bgg_id in bgg_ids:
                db.set_insert(c, bgg_id, has_insert)
        verb = "Marked" if has_insert else "Cleared 3D insert on"
        flash(f"{verb} {len(bgg_ids)} game{'s' if len(bgg_ids) != 1 else ''}.", "success")
    return redirect(request.referrer or url_for("games"))


# ═══════════════════════════════════════════════════════════════════════════════
# Members
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/members")
def members():
    with db.connect() as c:
        users    = [_row_to_dict(r) for r in db.list_users(c)]
        open_map = {}
        for loan in db.currently_checked_out(c):
            uid = loan["user_id"] if "user_id" in loan.keys() else None
            if uid:
                open_map.setdefault(uid, []).append(loan["game_name"])
    return render_template("members.html", users=users, open_map=open_map)


@app.route("/members/add", methods=["POST"])
def add_member():
    first = request.form.get("first_name", "").strip()
    last  = request.form.get("last_name",  "").strip()
    if not first or not last:
        flash("First and last name are required.", "error")
        return redirect(url_for("members"))
    with db.connect() as c:
        db.add_user(c, first, last)
    flash(f"Added {first} {last}.", "success")
    return redirect(url_for("members"))


@app.route("/members/<int:user_id>/delete", methods=["POST"])
def delete_member(user_id):
    with db.connect() as c:
        db.delete_user(c, user_id)
    flash("Friend removed.", "success")
    return redirect(url_for("members"))


# ═══════════════════════════════════════════════════════════════════════════════
# Checkout history
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/history")
def history():
    user_id  = request.args.get("user_id", type=int)
    game_id  = request.args.get("game_id",  type=int)
    status   = request.args.get("status", "all")    # all | active | returned
    mode     = request.args.get("mode", "checkouts")  # checkouts | plays

    with db.connect() as c:
        rows  = [_row_to_dict(r) for r in db.loan_history(c, game_id=game_id, user_id=user_id)]
        users = [_row_to_dict(r) for r in db.list_users(c)]
        plays = [_row_to_dict(r) for r in db.list_plays(c)]

    today = datetime.now().date().isoformat()
    for r in rows:
        r["overdue"] = bool(
            r.get("due_date") and not r.get("returned_at") and r["due_date"] < today
        )

    if status == "active":
        rows = [r for r in rows if not r.get("returned_at")]
    elif status == "returned":
        rows = [r for r in rows if r.get("returned_at")]

    return render_template("history.html",
                           rows=rows,
                           users=users,
                           plays=plays,
                           status=status,
                           mode=mode,
                           filter_user=user_id,
                           today=today)


@app.route("/history/<int:loan_id>/edit", methods=["POST"])
def edit_loan(loan_id):
    out_val   = request.form.get("checked_out_at", "").strip() or None
    ret_val   = request.form.get("returned_at",    "").strip() or None
    due_val   = request.form.get("due_date",        "").strip() or None
    notes_val = request.form.get("notes",           "").strip() or None
    if not out_val:
        flash("Checked-out date is required.", "error")
        return redirect(url_for("history"))
    with db.connect() as c:
        c.execute(
            "UPDATE loans SET checked_out_at=?, returned_at=?, due_date=?, notes=? WHERE id=?",
            (out_val, ret_val, due_val, notes_val, loan_id),
        )
    flash("Loan record updated.", "success")
    return redirect(url_for("history"))


@app.route("/history/<int:loan_id>/return_now", methods=["POST"])
def return_now(loan_id):
    with db.connect() as c:
        c.execute("UPDATE loans SET returned_at=? WHERE id=?",
                  (db.now_iso(), loan_id))
    flash("Marked as returned.", "success")
    return redirect(request.referrer or url_for("history"))


# ═══════════════════════════════════════════════════════════════════════════════
# Plays
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/plays")
def plays():
    game_id = request.args.get("game_id", type=int)
    with db.connect() as c:
        rows  = [_row_to_dict(r) for r in db.list_plays(c, game_id=game_id)]
        games = [_row_to_dict(r) for r in db.list_games(c, owned_only=False)]
    return render_template("plays.html",
                           rows=rows,
                           games=games,
                           filter_game=game_id)


@app.route("/plays/add", methods=["POST"])
def add_play():
    game_id   = request.form.get("game_id", type=int)
    played_at = request.form.get("played_at", "").strip()
    players   = request.form.get("player_names", "").strip()
    winner    = request.form.get("winner", "").strip()
    notes     = request.form.get("notes", "").strip()
    duration  = request.form.get("duration_minutes", "").strip()
    scores    = request.form.get("scores", "").strip() or None

    if not game_id or not played_at:
        flash("Game and date are required.", "error")
        return redirect(url_for("plays"))

    dur = None
    if duration:
        try:
            dur = int(duration)
        except ValueError:
            pass

    with db.connect() as c:
        db.log_play(c, game_id, played_at, players, winner, notes,
                    duration_minutes=dur, scores=scores)
    flash("Play logged.", "success")
    return redirect(request.referrer or url_for("plays"))


@app.route("/plays/<int:play_id>/edit", methods=["POST"])
def edit_play(play_id):
    game_id   = request.form.get("game_id", type=int)
    played_at = request.form.get("played_at", "").strip()
    players   = request.form.get("player_names", "").strip()
    winner    = request.form.get("winner", "").strip()
    notes     = request.form.get("notes", "").strip()
    duration  = request.form.get("duration_minutes", "").strip()
    scores    = request.form.get("scores", "").strip() or None

    if not game_id or not played_at:
        flash("Game and date are required.", "error")
        return redirect(url_for("plays"))

    dur = None
    if duration:
        try:
            dur = int(duration)
        except ValueError:
            pass

    with db.connect() as c:
        db.update_play(c, play_id, game_id, played_at, players, winner, notes,
                       duration_minutes=dur, scores=scores)
    flash("Play updated.", "success")
    return redirect(url_for("plays"))


@app.route("/plays/<int:play_id>/delete", methods=["POST"])
def delete_play(play_id):
    with db.connect() as c:
        db.delete_play(c, play_id)
    flash("Play deleted.", "success")
    return redirect(url_for("plays"))


# ═══════════════════════════════════════════════════════════════════════════════
# BGG search (JSON — used by the Add Game modal)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        tok     = _config.load().get("bgg_token", "")
        results = _bgg.search_games(q, token=tok or None)
        return jsonify([
            {"id": bgg_id, "name": name, "year": year}
            for bgg_id, name, year in results[:30]
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/game/<int:bgg_id>")
def api_game_details(bgg_id):
    """Fetch full game details from BGG (used by Add Game confirm step)."""
    settings = _settings()
    try:
        details = _bgg.fetch_game_details(bgg_id, token=settings.get("bgg_token", ""))
        if details is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify({
            "bgg_id":      details.bgg_id,
            "name":        details.name,
            "year":        details.year,
            "min_players": details.min_players,
            "max_players": details.max_players,
            "playing_time": details.playing_time,
            "weight":      details.weight,
            "avg_rating":  details.avg_rating,
            "description": (details.description or "")[:500],
            "image_url":   details.image_url,
            "thumbnail_url": details.thumbnail_url,
            "is_expansion": details.is_expansion,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/games/add", methods=["POST"])
def add_game():
    """Save a game fetched from BGG."""
    bgg_id = request.form.get("bgg_id", type=int)
    if not bgg_id:
        flash("No BGG ID provided.", "error")
        return redirect(url_for("games"))
    settings = _settings()
    try:
        details = _bgg.fetch_game_details(bgg_id, token=settings.get("bgg_token", ""))
        if details is None:
            flash("Game not found on BGG.", "error")
            return redirect(url_for("games"))
        row = {
            "bgg_id":        details.bgg_id,
            "name":          details.name,
            "year":          details.year,
            "image_url":     details.image_url,
            "thumbnail_url": details.thumbnail_url,
            "image_path":    None,
            "min_players":   details.min_players,
            "max_players":   details.max_players,
            "min_playtime":  details.min_playtime,
            "max_playtime":  details.max_playtime,
            "playing_time":  details.playing_time,
            "min_age":       details.min_age,
            "weight":        details.weight,
            "avg_rating":    details.avg_rating,
            "my_rating":     None,
            "description":   details.description,
            "categories":    ", ".join(details.categories) if details.categories else None,
            "mechanics":     ", ".join(details.mechanics)  if details.mechanics  else None,
            "designers":     ", ".join(details.designers)  if details.designers  else None,
            "publishers":    ", ".join(details.publishers) if details.publishers else None,
            "best_players":  details.best_players,
            "my_comment":    None,
            "own":           1,
            "last_synced":   db.now_iso(),
            "is_expansion":  int(details.is_expansion),
            "is_cooperative": _bgg.derive_cooperative(details.mechanics),
            "base_game_id":   details.base_game_id,
            "base_game_name": details.base_game_name,
        }
        with db.connect() as c:
            db.upsert_game(c, row)
        flash(f'Added "{details.name}" to your library.', "success")
    except Exception as e:
        flash(f"Error adding game: {e}", "error")
    return redirect(url_for("games"))


# ═══════════════════════════════════════════════════════════════════════════════
# BGG Sync
# ═══════════════════════════════════════════════════════════════════════════════

def _run_sync(owner_first: str = "", owner_last: str = "", claim_as_mine: bool = False):
    global _sync_status
    settings = _settings()
    username = settings.get("bgg_username", "")
    token    = settings.get("bgg_token", "")

    def on_status(msg):
        _sync_status["message"] = msg

    try:
        # import_from_username fetches /collection (all BGG statuses — own,
        # wishlist, fortrade, etc.) then enriches every game via /thing
        # (weight, categories, designers, best-at...) and returns GameDetails.
        games = _bgg.import_from_username(username, token=token, on_status=on_status)
        total = len(games)
        with db.connect() as c:
            for i, g in enumerate(games, 1):
                if i == 1 or i % 10 == 0 or i == total:
                    _sync_status["message"] = f"Saving {i} of {total} games…"
                row = {
                    "bgg_id":       g.bgg_id,
                    "name":         g.name,
                    "year":         g.year,
                    "image_url":    g.image_url,
                    "thumbnail_url":g.thumbnail_url,
                    "image_path":   None,
                    "min_players":  g.min_players,
                    "max_players":  g.max_players,
                    "min_playtime": g.min_playtime,
                    "max_playtime": g.max_playtime,
                    "playing_time": g.playing_time,
                    "min_age":      g.min_age,
                    "weight":       g.weight,
                    "avg_rating":   g.avg_rating,
                    "my_rating":    g.my_rating,
                    "description":  g.description,
                    "categories":   ", ".join(g.categories) if g.categories else None,
                    "mechanics":    ", ".join(g.mechanics)  if g.mechanics  else None,
                    "designers":    ", ".join(g.designers)  if g.designers  else None,
                    "publishers":   ", ".join(g.publishers) if g.publishers else None,
                    "best_players": g.best_players,
                    "my_comment":   g.my_comment,
                    # BGG collection status, when known, determines real ownership;
                    # unknown status defaults to owned (matches prior behavior).
                    "own":          1 if g.bgg_status in (None, "own") else 0,
                    "last_synced":  db.now_iso(),
                    "is_expansion": int(g.is_expansion),
                    "is_cooperative": _bgg.derive_cooperative(g.mechanics),
                    "base_game_id": g.base_game_id,
                    "base_game_name": g.base_game_name,
                    "bgg_status":   g.bgg_status,
                }
                existing = db.get_game(c, g.bgg_id)
                skip = set()
                if existing:
                    if existing["image_path"]:
                        row["image_path"] = existing["image_path"]
                    skip = db.get_manual_fields(c, g.bgg_id)
                db.upsert_game(c, row, skip_fields=skip)

            # Link the synced games to this user's collection (multi-collection).
            # Membership is only the games actually owned — wishlist/for-trade/
            # etc. are saved above so they're browsable, but don't count toward
            # collection comparisons.
            if username:
                cid = db.get_or_create_collection(c, username, username)
                owned_ids = [g.bgg_id for g in games if g.bgg_status in (None, "own")]
                db.replace_collection_games(c, cid, owned_ids)

                # Optionally add the importer as a member, claim the collection
                # for them, and mark them as this device's owner ("me").
                if claim_as_mine and (owner_first or owner_last):
                    existing = next(
                        (u for u in db.list_users(c)
                         if u["first_name"].strip().lower() == owner_first.lower()
                         and u["last_name"].strip().lower() == owner_last.lower()),
                        None,
                    )
                    uid = existing["id"] if existing else db.add_user(
                        c, owner_first, owner_last)
                    db.claim_collection(c, cid, uid)
                    s = _config.load()
                    s["claimed_member_id"] = uid
                    _config.save(s)

        _sync_status["message"] = f"Sync complete — {len(games)} games."
    except Exception as e:
        _sync_status["error"]   = str(e)
        _sync_status["message"] = f"Sync failed: {e}"
    finally:
        _sync_status["running"] = False


@app.route("/sync", methods=["POST"])
def sync():
    # Credentials are entered/updated from the Sync dialog (parity with mobile)
    new_username = request.form.get("bgg_username", "").strip()
    if new_username:
        s = _config.load()
        s["bgg_username"] = new_username
        _config.save(s)
    owner_first = request.form.get("owner_first", "").strip()
    owner_last  = request.form.get("owner_last", "").strip()
    claim_as_mine = request.form.get("claim_as_mine") == "1"
    with _sync_lock:
        if _sync_status["running"]:
            flash("Sync already in progress.", "info")
            return redirect(url_for("dashboard"))
        if not _config.load().get("bgg_username", "").strip():
            flash("Enter your BGG username to sync.", "error")
            return redirect(url_for("dashboard"))
        _sync_status["running"] = True
        _sync_status["message"] = "Starting sync…"
        _sync_status["error"]   = None
    threading.Thread(target=_run_sync,
                     kwargs={"owner_first": owner_first, "owner_last": owner_last,
                             "claim_as_mine": claim_as_mine},
                     daemon=True).start()
    flash("BGG sync started — refresh in a moment.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/sync_status")
def sync_status():
    return jsonify(_sync_status)


# ═══════════════════════════════════════════════════════════════════════════════
# Backup export / import — same JSON schema as Desktop's "Export for Mobile"
# and the mobile app's own backup, so files are interchangeable between all
# three platforms.
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/backup/export")
def backup_export():
    with db.connect() as c:
        members = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id").fetchall()]
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
                      my_comment, my_rating, best_players, is_cooperative,
                      manual_fields, image_path, own, bgg_status
               FROM games
               WHERE tags IS NOT NULL OR is_favorite = 1 OR has_insert = 1
                  OR my_comment IS NOT NULL OR my_rating IS NOT NULL
                  OR best_players IS NOT NULL OR is_cooperative IS NOT NULL
                  OR image_path IS NOT NULL OR own = 0
                  OR (bgg_status IS NOT NULL AND bgg_status != 'own')
               """).fetchall()]

    # Embed any custom cover photo as base64 -- the raw image_path is a
    # server-local absolute path that means nothing once restored elsewhere.
    for cu in customisations:
        path = cu.pop("image_path", None)
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as imgf:
                    cu["photo_base64"] = base64.b64encode(imgf.read()).decode("ascii")
                cu["photo_ext"] = os.path.splitext(path)[1].lstrip(".").lower() or "jpg"
            except OSError:
                pass  # Photo file unreadable -- skip it, don't fail the whole export.

    payload = {
        "version": 3,
        "exported_at": db.now_iso(),
        "members": members,
        "plays": plays,
        "loans": loans,
        "customisations": customisations,
    }
    body = json.dumps(payload, indent=2, default=str)
    filename = f"bgl-backup-{datetime.now():%Y-%m-%d}.json"
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/backup/import", methods=["POST"])
def backup_import():
    file = request.files.get("backup_file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard"))
    try:
        data = json.load(file.stream)
    except Exception:
        flash("Could not read that file — is it a valid backup JSON?", "error")
        return redirect(url_for("dashboard"))
    if not data.get("version") or not data.get("members"):
        flash("This doesn't appear to be a Board Game Library backup.", "error")
        return redirect(url_for("dashboard"))

    counts = {"members": 0, "plays": 0, "loans": 0, "customisations": 0, "skipped": 0}
    with db.connect() as c:
        # Members — map old ids -> local ids so loans/plays resolve correctly.
        user_id_map: dict[int, int] = {}
        for m in data.get("members") or []:
            row = c.execute(
                "SELECT id FROM users WHERE first_name = ? AND last_name = ?",
                (m.get("first_name"), m.get("last_name")),
            ).fetchone()
            if row:
                user_id_map[m["id"]] = row["id"]
                counts["skipped"] += 1
            else:
                new_id = db.add_user(c, m.get("first_name") or "", m.get("last_name") or "")
                user_id_map[m["id"]] = new_id
                counts["members"] += 1

        for p in data.get("plays") or []:
            exists = c.execute(
                "SELECT id FROM plays WHERE game_id = ? AND played_at = ?",
                (p.get("game_id"), p.get("played_at")),
            ).fetchone()
            if exists or not db.get_game(c, p.get("game_id")):
                counts["skipped"] += 1
                continue
            db.log_play(
                c, p["game_id"], p["played_at"],
                p.get("player_names") or "", p.get("winner") or "", p.get("notes") or "",
                duration_minutes=p.get("duration_minutes"), scores=p.get("scores"),
            )
            counts["plays"] += 1

        for l in data.get("loans") or []:
            mapped_user_id = user_id_map.get(l.get("user_id"), l.get("user_id"))
            exists = c.execute(
                "SELECT id FROM loans WHERE game_id = ? AND checked_out_at = ?",
                (l.get("game_id"), l.get("checked_out_at")),
            ).fetchone()
            if exists or not db.get_game(c, l.get("game_id")):
                counts["skipped"] += 1
                continue
            c.execute(
                "INSERT INTO loans (game_id, user_id, checked_out_at, returned_at, due_date, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (l["game_id"], mapped_user_id, l["checked_out_at"],
                 l.get("returned_at"), l.get("due_date"), l.get("notes")),
            )
            counts["loans"] += 1

        for cu in data.get("customisations") or []:
            if not db.get_game(c, cu.get("bgg_id")):
                counts["skipped"] += 1
                continue
            image_path = None
            if cu.get("photo_base64"):
                try:
                    ext = cu.get("photo_ext") or "jpg"
                    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                    dest = IMAGES_DIR / f"{cu['bgg_id']}.{ext}"
                    dest.write_bytes(base64.b64decode(cu["photo_base64"]))
                    image_path = str(dest)
                except (OSError, ValueError):
                    pass  # Couldn't write the photo -- keep any existing one.
            c.execute(
                "UPDATE games SET tags=?, is_favorite=?, has_insert=?, "
                "my_comment=?, my_rating=?, best_players=?, is_cooperative=?, "
                "manual_fields=?, image_path=COALESCE(?, image_path), "
                "own=COALESCE(?, own), bgg_status=COALESCE(?, bgg_status) WHERE bgg_id=?",
                (cu.get("tags"), cu.get("is_favorite") or 0, cu.get("has_insert") or 0,
                 cu.get("my_comment"), cu.get("my_rating"), cu.get("best_players"),
                 cu.get("is_cooperative"), cu.get("manual_fields"), image_path,
                 cu.get("own"), cu.get("bgg_status"),
                 cu["bgg_id"]),
            )
            counts["customisations"] += 1

    flash(
        f"Import complete — Members: +{counts['members']}, Plays: +{counts['plays']}, "
        f"Loans: +{counts['loans']}, Customisations: {counts['customisations']}, "
        f"Skipped (already existed): {counts['skipped']}",
        "success",
    )
    return redirect(url_for("dashboard"))


# ═══════════════════════════════════════════════════════════════════════════════
# Template helpers
# ═══════════════════════════════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    return {
        "now": datetime.now(),
        "sync_status": _sync_status,
        "bgg_username": _config.load().get("bgg_username", ""),
        "already_claimed": bool(_config.load().get("claimed_member_id")),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import socket
    host = "0.0.0.0"    # Listen on all interfaces so phones on the same Wi-Fi can connect
    port = 5000
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"\n  Board Game Library Web App")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Network: http://{local_ip}:{port}  <-- open this on your phone\n")
    app.run(host=host, port=port, debug=False)
