"""Tests for db.play_summary (count / first / last played for one game)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from tests.test_backup import DbCase, _game  # noqa: E402


class PlaySummaryTests(DbCase):
    def test_never_played(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Unplayed"))
            self.assertEqual(db.play_summary(c, 1), (0, None, None))

    def test_count_first_last_ignores_other_games(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "A"))
            self.insert_game(c, _game(2, "B"))
            db.log_play(c, 1, "2026-03-05")
            db.log_play(c, 1, "2025-03-03")
            db.log_play(c, 1, "2026-09-12T20:00:00")
            db.log_play(c, 2, "2027-01-01")
            self.assertEqual(db.play_summary(c, 1), (3, "2025-03-03", "2026-09-12"))
            self.assertEqual(db.play_summary(c, 2), (1, "2027-01-01", "2027-01-01"))

    def test_after_delete(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "A"))
            db.log_play(c, 1, "2026-01-01")
            pid = db.list_plays(c, game_id=1)[0]["id"]
            db.delete_play(c, pid)
            self.assertEqual(db.play_summary(c, 1), (0, None, None))
