"""Board Game Library — Flask web app.

Reuses db.py, bgg.py, config.py, and paths.py from the parent directory.
Run with:  python web/app.py
Then open  http://localhost:5000  on any device on the same Wi-Fi.
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

# ── Pull in the shared library modules ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import bgg as _bgg
import config as _config

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort, Response,
)

app = Flask(__name__)
app.secret_key = "bgl-flask-secret-2025"

# ── Ensure the database is ready ──────────────────────────────────────────────
db.init_db()

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
    status     = request.args.get("status", "all")   # all | available | out
    fav_only   = request.args.get("fav", "") == "1"
    show_exp   = request.args.get("exp", "") == "1"

    with db.connect() as c:
        rows      = db.list_games(c, search=q)
        open_loans = {r["game_id"]: _row_to_dict(r)
                      for r in db.currently_checked_out(c)}
        play_cts   = db.play_counts(c)
        all_tags   = db.all_tags(c)

    games_list = []
    for g in rows:
        gd = _row_to_dict(g)
        gd["play_count"] = play_cts.get(g["bgg_id"], 0)
        gd["loan"]       = open_loans.get(g["bgg_id"])

        if not show_exp and g["is_expansion"]:
            continue
        if fav_only and not g["is_favorite"]:
            continue
        if tag_filter:
            tags = [t.strip() for t in (g["tags"] or "").split(",") if t.strip()]
            if tag_filter not in tags:
                continue
        if status == "available" and g["bgg_id"] in open_loans:
            continue
        if status == "out" and g["bgg_id"] not in open_loans:
            continue

        games_list.append(gd)

    return render_template("games.html",
                           games=games_list,
                           q=q,
                           tag_filter=tag_filter,
                           status=status,
                           fav_only=fav_only,
                           show_exp=show_exp,
                           all_tags=all_tags)


@app.route("/games/<int:bgg_id>")
def game_detail(bgg_id):
    with db.connect() as c:
        game = _row_to_dict(db.get_game(c, bgg_id))
        if not game:
            abort(404)
        loan      = _row_to_dict(db.open_loan_for_game(c, bgg_id))
        plays     = [_row_to_dict(r) for r in db.list_plays(c, game_id=bgg_id)]
        stats     = db.game_play_stats(c, bgg_id)
        users     = [_row_to_dict(r) for r in db.list_users(c)]

    today = datetime.now().date().isoformat()
    if loan:
        loan["overdue"] = bool(loan.get("due_date") and loan["due_date"] < today)

    return render_template("game_detail.html",
                           game=game,
                           loan=loan,
                           plays=plays,
                           stats=stats,
                           users=users,
                           today=today)


# ── Checkout ──────────────────────────────────────────────────────────────────

@app.route("/games/<int:bgg_id>/checkout", methods=["POST"])
def checkout(bgg_id):
    user_id  = request.form.get("user_id", type=int)
    due_date = request.form.get("due_date", "").strip() or None
    notes    = request.form.get("notes", "").strip()
    if not user_id:
        flash("Please select a member.", "error")
        return redirect(url_for("game_detail", bgg_id=bgg_id))
    try:
        with db.connect() as c:
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
    flash("Member removed.", "success")
    return redirect(url_for("members"))


# ═══════════════════════════════════════════════════════════════════════════════
# Checkout history
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/history")
def history():
    user_id  = request.args.get("user_id", type=int)
    game_id  = request.args.get("game_id",  type=int)
    status   = request.args.get("status", "all")    # all | active | returned

    with db.connect() as c:
        rows  = [_row_to_dict(r) for r in db.loan_history(c, game_id=game_id, user_id=user_id)]
        users = [_row_to_dict(r) for r in db.list_users(c)]

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
                           status=status,
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
        games = [_row_to_dict(r) for r in db.list_games(c)]
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
        results = _bgg.search_games(q)
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

def _run_sync():
    global _sync_status
    settings = _settings()
    username = settings.get("bgg_username", "")
    token    = settings.get("bgg_token", "")

    def on_status(msg):
        _sync_status["message"] = msg

    try:
        collection = _bgg.fetch_collection(username, token=token, on_status=on_status)
        with db.connect() as c:
            for g in collection:
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
                    "own":          1,
                    "last_synced":  db.now_iso(),
                    "is_expansion": int(g.is_expansion),
                }
                existing = db.get_game(c, g.bgg_id)
                skip = set()
                if existing:
                    if existing["image_path"]:
                        row["image_path"] = existing["image_path"]
                    skip = db.get_manual_fields(c, g.bgg_id)
                db.upsert_game(c, row, skip_fields=skip)

        _sync_status["message"] = f"Sync complete — {len(collection)} games."
    except Exception as e:
        _sync_status["error"]   = str(e)
        _sync_status["message"] = f"Sync failed: {e}"
    finally:
        _sync_status["running"] = False


@app.route("/sync", methods=["POST"])
def sync():
    with _sync_lock:
        if _sync_status["running"]:
            flash("Sync already in progress.", "info")
            return redirect(url_for("dashboard"))
        _sync_status["running"] = True
        _sync_status["message"] = "Starting sync…"
        _sync_status["error"]   = None
    threading.Thread(target=_run_sync, daemon=True).start()
    flash("BGG sync started — refresh in a moment.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/sync_status")
def sync_status():
    return jsonify(_sync_status)


# ═══════════════════════════════════════════════════════════════════════════════
# Template helpers
# ═══════════════════════════════════════════════════════════════════════════════

@app.context_processor
def inject_globals():
    return {
        "now": datetime.now(),
        "sync_status": _sync_status,
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
    print(f"  Network: http://{local_ip}:{port}  ← open this on your phone\n")
    app.run(host=host, port=port, debug=False)
