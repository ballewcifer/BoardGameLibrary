"""Tests for play_stats.py and the case-insensitive BGG-username collection lookups.

Run from the repo root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import play_stats as ps  # noqa: E402


def _p(pid, game_id, game_name, played_at, player_names="", winner=""):
    return {"id": pid, "game_id": game_id, "game_name": game_name, "played_at": played_at,
            "player_names": player_names, "winner": winner}


TODAY = date(2026, 1, 15)
PLAYS = [
    _p(1, 1, "Catan", "2026-01-10", "Tim, Sam, Ann", "Tim"),
    _p(2, 1, "Catan", "2025-12-20", "tim, Sam", "Sam"),
    _p(3, 2, "Pandemic", "2025-06-01", "Tim, Sam, Ann", "All"),
    _p(4, 2, "Pandemic", "2026-01-02", "Tim, Sam", ""),
    _p(5, 3, "Azul", "2025-12-17", "Tim, Ann", "Ann"),
    _p(6, 3, "Azul", "2025-12-16T10:00:00", "Tim, Ann, Tim", "tim"),
]


class PlayStatsCase(unittest.TestCase):
    def test_periods(self):
        self.assertIsNone(ps.period_start("all", TODAY))
        self.assertEqual(ps.period_start("year", TODAY), "2026-01-01")
        self.assertEqual(ps.period_start("30d", TODAY), "2025-12-17")
        self.assertEqual([p["id"] for p in ps.plays_in_period(PLAYS, "30d", TODAY)], [1, 2, 4, 5])
        self.assertEqual(ps.plays_this_year(PLAYS, TODAY), 2)

    def test_most_played(self):
        top = ps.most_played_games(PLAYS)
        self.assertEqual([(g["name"], g["count"]) for g in top],
                         [("Catan", 2), ("Pandemic", 2), ("Azul", 2)])
        self.assertEqual(top[1]["last_played"], "2026-01-02")

    def test_player_records(self):
        recs = {r["name"].lower(): r for r in ps.player_records(PLAYS)}
        self.assertEqual((recs["tim"]["plays"], recs["tim"]["wins"]), (4, 2))
        self.assertEqual((recs["ann"]["plays"], recs["ann"]["wins"]), (3, 1))
        self.assertEqual((recs["sam"]["plays"], recs["sam"]["wins"]), (2, 1))
        self.assertEqual([r["name"].lower() for r in ps.player_records(PLAYS)], ["tim", "sam", "ann"])

    def test_plays_by_month(self):
        rows = ps.plays_by_month(PLAYS, 3, TODAY)
        self.assertEqual([(m["key"], m["label"], m["count"]) for m in rows],
                         [("2026-01", "Jan 2026", 2), ("2025-12", "Dec 2025", 3), ("2025-11", "Nov 2025", 0)])
        year = ps.plays_by_month(PLAYS, 12, TODAY)
        self.assertEqual(len(year), 12)
        self.assertEqual(year[-1]["key"], "2025-02")


class PlayFilterCase(unittest.TestCase):
    def ids(self, **kw):
        return [p["id"] for p in ps.filter_plays(PLAYS, ps.PlayFilters(**kw), TODAY)]

    def test_filters(self):
        self.assertFalse(ps.has_play_filters(ps.PlayFilters()))
        self.assertFalse(ps.has_play_filters(ps.PlayFilters(query="  ")))
        self.assertTrue(ps.has_play_filters(ps.PlayFilters(period="30d")))
        self.assertEqual(self.ids(), [1, 2, 3, 4, 5, 6])
        self.assertEqual(self.ids(game_id=3), [5, 6])
        self.assertEqual(self.ids(friend="ann"), [1, 3, 5, 6])          # case-insensitive, listed players only
        self.assertEqual(self.ids(friend="Sam", game_id=1), [1, 2])
        self.assertEqual(self.ids(query="AZUL"), [5, 6])                # game name
        self.assertEqual(self.ids(query="ann"), [1, 3, 5, 6])           # player names
        self.assertEqual(self.ids(query="pand", period="year"), [4])    # combined with a period
        self.assertEqual(self.ids(friend="Zed"), [])

    def test_player_names_and_filtered_stats(self):
        self.assertEqual(ps.player_names_in(PLAYS), ["Ann", "Sam", "Tim"])
        azul = ps.filter_plays(PLAYS, ps.PlayFilters(game_id=3), TODAY)
        self.assertEqual([(g["name"], g["count"]) for g in ps.most_played_games(azul)], [("Azul", 2)])
        self.assertEqual([(r["name"], r["plays"], r["wins"]) for r in ps.player_records(azul)],
                         [("Ann", 2, 1), ("Tim", 2, 1)])               # tie -> name A-Z


class CollectionCaseCase(unittest.TestCase):
    def test_username_lookup_ignores_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.db"
            db.init_db(path)
            with db.connect(path) as c:
                first = db.get_or_create_collection(c, "ballewcifer", "ballewcifer")
                again = db.get_or_create_collection(c, "Ballewcifer", "Ballewcifer")
                self.assertEqual(first, again)
                self.assertEqual(db.collection_id_for_username(c, "BALLEWCIFER"), first)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM collections").fetchone()[0], 1)

    def test_reset_claim_ignores_case(self):
        settings = {"claimed_bgg_username": "Ballewcifer"}
        self.assertTrue(db.reset_claim_if_cleared(settings, ["ballewcifer"]))
        self.assertNotIn("claimed_bgg_username", settings)


if __name__ == "__main__":
    unittest.main()
