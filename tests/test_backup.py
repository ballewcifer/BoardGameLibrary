"""Tests for the shared logic in db.py: the full-library JSON backup (version 5,
interchangeable with the mobile app), the claimed-collection helpers, and the
friend helpers.

Run from the repo root:  python -m unittest discover -s tests -v

Everything runs against throwaway temp databases — never the real library.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402


def _game(bgg_id, name, **extra):
    row = {"bgg_id": bgg_id, "name": name, "own": 1}
    row.update(extra)
    return row


class DbCase(unittest.TestCase):
    """Gives each test its own pair of temp databases (`src` and `dst`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.src = self.tmp / "src.db"
        self.dst = self.tmp / "dst.db"
        db.init_db(self.src)
        db.init_db(self.dst)

    @staticmethod
    def insert_game(c, g):
        cols = list(g)
        c.execute(f"INSERT INTO games ({', '.join(cols)}) "
                  f"VALUES ({', '.join('?' * len(cols))})", [g[k] for k in cols])

    @staticmethod
    def count(c, table):
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def seed_source(self):
        """A library with every kind of row the backup has to carry."""
        with db.connect(self.src) as c:
            self.insert_game(c, _game(101, "Owned Game", year=2020,
                                      description="a" * 300, min_players=2,
                                      bgg_status="own", is_favorite=1, tags="Party",
                                      image_path="C:/somewhere/local/101.jpg"))
            self.insert_game(c, _game(102, "Wishlist Game", own=0, bgg_status="wishlist"))
            self.insert_game(c, _game(103, "Added Individually", year=2018))  # in no collection
            self.insert_game(c, _game(-5, "Hand Made Game", tags="Custom",
                                      my_comment="house rules", is_cooperative=1))
            jane = db.add_user(c, "Jane", "Doe", "janed")
            bob = db.add_user(c, "Bob", "Ray")
            cid = db.get_or_create_collection(c, "ballewcifer", "ballewcifer")
            db.claim_collection(c, cid, bob)
            db.replace_collection_games(c, cid, [101, 102])
            db.log_play(c, 101, "2026-03-01", "Jane Doe, Bob Ray", "Jane Doe")
            db.check_out(c, 101, jane)

    def export(self):
        """The backup exactly as it would be written to disk and read back."""
        with db.connect(self.src) as c:
            return json.loads(json.dumps(db.build_backup_payload(c), default=str))

    def restore(self, path, data, **kw):
        with db.connect(path) as c:
            return db.restore_backup_tables(c, data, **kw)


class BackupExportTests(DbCase):
    def test_export_is_v5_and_carries_the_whole_library(self):
        self.seed_source()
        payload = self.export()
        self.assertEqual(payload["version"], 5)
        self.assertEqual(len(payload["games"]), 4, "every game, not just manual ones")
        for key in ("members", "collections", "game_collections", "plays",
                    "loans", "customisations"):
            self.assertIn(key, payload)
        # Device-local paths never leave the machine.
        self.assertTrue(all("image_path" not in g for g in payload["games"]))
        self.assertTrue(all("image_path" not in cu for cu in payload["customisations"]))
        # Members carry their BGG username; collections carry the owner.
        jane = next(m for m in payload["members"] if m["first_name"] == "Jane")
        self.assertEqual(jane["bgg_username"], "janed")
        self.assertIsNotNone(payload["collections"][0]["owner_user_id"])
        self.assertTrue(db.is_backup_payload(payload))

    def test_is_backup_payload(self):
        self.assertTrue(db.is_backup_payload({"version": 5, "members": []}))
        self.assertTrue(db.is_backup_payload({"version": 5, "games": []}))
        self.assertFalse(db.is_backup_payload({"members": []}))
        self.assertFalse(db.is_backup_payload({"version": 5}))
        self.assertFalse(db.is_backup_payload([]))


class BackupRestoreTests(DbCase):
    def test_a_fresh_library_gets_everything_back(self):
        self.seed_source()
        r = self.restore(self.dst, self.export())
        self.assertEqual((r["games"], r["no_game"], r["members"]), (4, 0, 2))
        with db.connect(self.dst) as c:
            self.assertEqual(self.count(c, "games"), 4)
            g101 = db.get_game(c, 101)
            self.assertEqual(len(g101["description"]), 300)
            self.assertEqual((g101["is_favorite"], g101["tags"]), (1, "Party"))
            self.assertIsNone(g101["image_path"])
            self.assertEqual(db.get_game(c, 102)["bgg_status"], "wishlist")
            self.assertIsNotNone(db.get_game(c, 103), "individually added game restored")
            hm = db.get_game(c, -5)
            self.assertEqual((hm["tags"], hm["my_comment"], hm["is_cooperative"]),
                             ("Custom", "house rules", 1))
            self.assertEqual(self.count(c, "plays"), 1)
            self.assertEqual(self.count(c, "loans"), 1)
            self.assertEqual(self.count(c, "collections"), 1)
            self.assertEqual(self.count(c, "game_collections"), 2)
            self.assertEqual(
                c.execute("SELECT bgg_username FROM users WHERE first_name='Jane'"
                          ).fetchone()[0], "janed")

    def test_restoring_the_same_file_again_changes_nothing(self):
        self.seed_source()
        data = self.export()
        self.restore(self.dst, data)
        r2 = self.restore(self.dst, data)
        for k in ("games", "plays", "loans", "collections", "members"):
            self.assertEqual(r2[k], 0, k)
        with db.connect(self.dst) as c:
            self.assertEqual(self.count(c, "games"), 4)
            self.assertEqual(self.count(c, "plays"), 1)
            self.assertEqual(self.count(c, "loans"), 1)
            self.assertEqual(self.count(c, "game_collections"), 2)
            self.assertEqual(self.count(c, "users"), 2)
            self.assertEqual(self.count(c, "collections"), 1)

    def test_old_v4_backup_restores_manual_games_and_reports_the_rest(self):
        self.seed_source()
        full = self.export()
        v4 = {"version": 4, "members": full["members"],
              "manual_games": [g for g in full["games"] if g["bgg_id"] < 0],
              "plays": full["plays"], "loans": full["loans"],
              "customisations": full["customisations"]}
        r = self.restore(self.dst, v4)
        self.assertEqual(r["games"], 1)
        with db.connect(self.dst) as c:
            self.assertEqual(self.count(c, "games"), 1)
        self.assertGreater(r["no_game"], 0)
        self.assertIn("BoardGameGeek", db.summarize_import(r))

    def test_existing_game_is_not_overwritten_but_your_data_goes_on_top(self):
        self.seed_source()
        with db.connect(self.dst) as c:
            self.insert_game(c, _game(101, "Owned Game (fresh BGG sync)"))
        r = self.restore(self.dst, self.export())
        with db.connect(self.dst) as c:
            g = db.get_game(c, 101)
            self.assertEqual(g["name"], "Owned Game (fresh BGG sync)")
            self.assertEqual((g["is_favorite"], g["tags"]), (1, "Party"))
        self.assertEqual(r["games"], 3)

    def test_ids_that_differ_on_the_target_are_remapped(self):
        self.seed_source()
        with db.connect(self.dst) as c:
            db.add_user(c, "Someone", "Else")
            db.add_user(c, "Other", "Person")
        self.restore(self.dst, self.export())
        with db.connect(self.dst) as c:
            owner = c.execute("SELECT u.first_name FROM collections col "
                              "JOIN users u ON u.id = col.owner_user_id").fetchone()
            borrower = c.execute("SELECT u.first_name FROM loans l "
                                 "JOIN users u ON u.id = l.user_id").fetchone()
        self.assertEqual(owner[0], "Bob")
        self.assertEqual(borrower[0], "Jane")

    def test_collections_match_by_username_then_by_name(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "One"))
            self.insert_game(c, _game(2, "Two"))
            by_user = db.get_or_create_collection(c, "someuser", "Some User")
            by_name = db.get_or_create_collection(c, None, "Hand Picked")
            db.replace_collection_games(c, by_user, [1])
            db.replace_collection_games(c, by_name, [2])
        with db.connect(self.dst) as c:
            self.insert_game(c, _game(1, "One"))
            existing = db.get_or_create_collection(c, "someuser", "Renamed Locally")
            named = db.get_or_create_collection(c, None, "Hand Picked")
        r = self.restore(self.dst, self.export())
        self.assertEqual(r["collections"], 0, "both matched existing collections")
        with db.connect(self.dst) as c:
            self.assertEqual(self.count(c, "collections"), 2)
            self.assertEqual(db.collection_game_ids(c, existing), {1})
            self.assertEqual(db.collection_game_ids(c, named), {2})

    def test_membership_and_plays_for_games_not_in_the_backup_are_skipped(self):
        data = {"version": 5, "members": [], "games": [],
                "collections": [{"id": 1, "name": "X", "bgg_username": "x"}],
                "game_collections": [{"game_id": 999, "collection_id": 1}],
                "plays": [{"game_id": 999, "played_at": "2026-01-01"}],
                "loans": [{"game_id": 999, "user_id": 1, "checked_out_at": "2026-01-01"}],
                "customisations": [{"bgg_id": 999, "tags": "t"}]}
        r = self.restore(self.dst, data)
        self.assertEqual(r["no_game"], 3)
        with db.connect(self.dst) as c:
            self.assertEqual(self.count(c, "game_collections"), 0)
            self.assertEqual(self.count(c, "plays"), 0)
        self.assertIn("3 play, loan or detail records belong", db.summarize_import(r))

    def test_unknown_columns_are_ignored_and_bad_rows_skipped(self):
        data = {"version": 5, "members": [],
                "games": [{"bgg_id": 7, "name": "Seven", "from_the_future": "x",
                           "image_path": "C:/nope.jpg"},
                          {"bgg_id": "8", "name": "Bad id"},
                          {"bgg_id": 9, "name": ""}]}
        r = self.restore(self.dst, data)
        self.assertEqual((r["games"], r["skipped"]), (1, 2))
        with db.connect(self.dst) as c:
            self.assertIsNone(db.get_game(c, 7)["image_path"])

    def test_custom_cover_photo_round_trips(self):
        photo = self.tmp / "101.png"
        photo.write_bytes(b"\x89PNG-not-really")
        self.seed_source()
        with db.connect(self.src) as c:
            db.set_image_path(c, 101, str(photo))
        data = self.export()
        cu = next(x for x in data["customisations"] if x["bgg_id"] == 101)
        self.assertNotIn("image_path", cu)
        self.assertEqual(cu["photo_ext"], "png")
        images = self.tmp / "images"
        self.restore(self.dst, data, images_dir=images)
        with db.connect(self.dst) as c:
            self.assertEqual(Path(db.get_game(c, 101)["image_path"]).read_bytes(),
                             b"\x89PNG-not-really")

    def test_summary_lists_the_counts(self):
        self.seed_source()
        text = db.summarize_import(self.restore(self.dst, self.export()))
        self.assertIn("Games: +4", text)
        self.assertIn("Collections: +1", text)
        self.assertIn("Friends: +2", text)


class ClaimTests(DbCase):
    def test_game_in_username_collection(self):
        with db.connect(self.dst) as c:
            self.insert_game(c, _game(1, "In"))
            self.insert_game(c, _game(2, "Out"))
            cid = db.get_or_create_collection(c, "me", "me")
            db.replace_collection_games(c, cid, [1])
            self.assertTrue(db.game_in_username_collection(c, "me", 1))
            self.assertFalse(db.game_in_username_collection(c, "me", 2))
            # A collection that no longer exists restricts nothing.
            self.assertTrue(db.game_in_username_collection(c, "gone", 2))

    def test_migrate_claimed_member_derives_username(self):
        with db.connect(self.dst) as c:
            uid = db.add_user(c, "Me", "Myself")
            cid = db.get_or_create_collection(c, "myname", "myname")
            db.claim_collection(c, cid, uid)
            s = {"claimed_member_id": uid, "bgg_username": "myname"}
            self.assertTrue(db.migrate_claimed_member(c, s))
            self.assertEqual(s, {"bgg_username": "myname", "claimed_bgg_username": "myname"})
            self.assertFalse(db.migrate_claimed_member(c, s), "runs once")

    def test_migrate_claimed_member_drops_an_orphan_and_keeps_an_existing_claim(self):
        with db.connect(self.dst) as c:
            orphan = {"claimed_member_id": 42}
            self.assertTrue(db.migrate_claimed_member(c, orphan))
            self.assertEqual(orphan, {})
            uid = db.add_user(c, "A", "B")
            cid = db.get_or_create_collection(c, "one", "one")
            db.claim_collection(c, cid, uid)
            kept = {"claimed_member_id": uid, "claimed_bgg_username": "already"}
            db.migrate_claimed_member(c, kept)
            self.assertEqual(kept, {"claimed_bgg_username": "already"})
            self.assertFalse(db.migrate_claimed_member(c, {"bgg_username": "x"}))

    def test_reset_claim_if_cleared(self):
        s = {"claimed_bgg_username": "me"}
        self.assertFalse(db.reset_claim_if_cleared(s, ["other"]))
        self.assertTrue(db.reset_claim_if_cleared(s, ["me", "other"]))
        self.assertNotIn("claimed_bgg_username", s)
        self.assertFalse(db.reset_claim_if_cleared({}, ["me"]))


class FriendTests(DbCase):
    def test_add_and_update_user_with_bgg_username(self):
        with db.connect(self.dst) as c:
            plain = db.add_user(c, " Ann ", " Lee ")          # old 3-arg style still works
            withname = db.add_user(c, "Bo", "Kay", " bokay ")
            row = {u["id"]: u for u in db.list_users(c)}
            self.assertEqual((row[plain]["first_name"], row[plain]["last_name"]), ("Ann", "Lee"))
            self.assertIsNone(row[plain]["bgg_username"])
            self.assertEqual(row[withname]["bgg_username"], "bokay")
            db.update_user(c, plain, "Anna", "Lee", "annalee")
            db.update_user(c, withname, "Bo", "Kay", "")      # blank clears it
            row = {u["id"]: u for u in db.list_users(c)}
            self.assertEqual((row[plain]["first_name"], row[plain]["bgg_username"]),
                             ("Anna", "annalee"))
            self.assertIsNone(row[withname]["bgg_username"])

    def test_validate_friend(self):
        with db.connect(self.dst) as c:
            jane = db.add_user(c, "Jane", "Doe")
            self.assertIn("Both", db.validate_friend(c, "Jane", ""))
            self.assertIn("Both", db.validate_friend(c, "  ", "Doe"))
            self.assertIn("already", db.validate_friend(c, "jane", "DOE"))
            self.assertIsNone(db.validate_friend(c, "Jane", "Doe", exclude_id=jane),
                              "editing a friend never collides with themselves")
            self.assertIsNone(db.validate_friend(c, "Janet", "Doe"))

    def test_users_bgg_username_column_migrates_onto_an_old_database(self):
        old = self.tmp / "old.db"
        import sqlite3
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "first_name TEXT NOT NULL, last_name TEXT NOT NULL, "
                     "created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO users (first_name,last_name,created_at) VALUES ('O','Ld','x')")
        conn.commit()
        conn.close()
        db.init_db(old)
        with db.connect(old) as c:
            self.assertIsNone(c.execute("SELECT bgg_username FROM users").fetchone()[0])


class StatusFilterTests(DbCase):
    def test_all_owned_and_multi_status(self):
        with db.connect(self.dst) as c:
            self.insert_game(c, _game(1, "Own", bgg_status="own"))
            self.insert_game(c, _game(2, "Wish", own=0, bgg_status="wishlist"))
            self.insert_game(c, _game(3, "Trade", own=0, bgg_status="fortrade"))
            names = lambda **kw: [g["name"] for g in db.list_games(c, **kw)]
            self.assertEqual(names(), ["Own"], "callers that pass no status still get owned")
            self.assertEqual(names(status=["all"]), ["Own", "Trade", "Wish"])
            self.assertEqual(names(status=["owned"]), ["Own"])
            self.assertEqual(names(status=["wishlist", "fortrade"]), ["Trade", "Wish"])
            self.assertEqual(db.count_games(c, status=["all"]), 3)


class UnplayedTests(DbCase):
    def test_migration_adds_column_to_old_db(self):
        import sqlite3
        old = self.tmp / "old.db"
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE games (bgg_id INTEGER PRIMARY KEY, name TEXT NOT NULL, own INTEGER DEFAULT 1)")
        conn.execute("INSERT INTO games (bgg_id, name) VALUES (1, 'Old')")
        conn.commit()
        conn.close()
        db.init_db(old)
        with db.connect(old) as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(games)")}
            self.assertIn("is_unplayed", cols)
            self.assertEqual(c.execute("SELECT is_unplayed FROM games").fetchone()[0], 0)

    def test_never_flagged_automatically(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Fresh"))
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 0)

    def test_guard_rules(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Owned"))
            self.insert_game(c, _game(2, "Played"))
            self.insert_game(c, _game(3, "Wish", own=0))
            db.log_play(c, 2, "2026-01-01")
            self.assertEqual(db.set_unplayed(c, [1, 2, 3, 99], True), (1, 3))
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 1)
            self.assertEqual(db.get_game(c, 2)["is_unplayed"], 0)
            self.assertEqual(db.get_game(c, 3)["is_unplayed"], 0)
            self.assertEqual(db.set_unplayed(c, [1], False), (1, 0))
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 0)

    def test_log_play_and_update_play_clear_the_mark(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "A"))
            self.insert_game(c, _game(2, "B"))
            db.set_unplayed(c, [1, 2], True)
            db.log_play(c, 1, "2026-02-01")
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 0)
            self.assertEqual(db.get_game(c, 2)["is_unplayed"], 1)
            pid = db.log_play(c, 1, "2026-02-02")
            db.update_play(c, pid, 2, "2026-02-02")   # re-point the play at B
            self.assertEqual(db.get_game(c, 2)["is_unplayed"], 0)

    def test_list_games_unplayed_only(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Marked"))
            self.insert_game(c, _game(2, "Plain"))
            db.set_unplayed(c, [1], True)
            self.assertEqual([g["name"] for g in db.list_games(c, unplayed_only=True)], ["Marked"])

    def test_backup_round_trip_preserves_the_mark(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Marked"))
            self.insert_game(c, _game(2, "Plain"))
            db.set_unplayed(c, [1], True)
        data = self.export()
        self.assertEqual(
            [cu["bgg_id"] for cu in data["customisations"] if cu.get("is_unplayed")], [1])
        self.assertEqual(self.restore(self.dst, data)["games"], 2)
        with db.connect(self.dst) as c:
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 1)
            self.assertEqual(db.get_game(c, 2)["is_unplayed"], 0)

    def test_restore_drops_mark_when_plays_exist(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Marked"))
            db.set_unplayed(c, [1], True)
        data = self.export()
        data["plays"] = [{"game_id": 1, "played_at": "2026-03-01", "player_names": "A"}]
        self.restore(self.dst, data)
        with db.connect(self.dst) as c:
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 0)

    def test_older_backup_without_field_is_treated_as_unmarked(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(1, "Old", is_favorite=1))
            db.set_unplayed(c, [1], True)
        data = self.export()
        for g in data["games"]:
            g.pop("is_unplayed", None)
        for cu in data["customisations"]:
            cu.pop("is_unplayed", None)
        self.restore(self.dst, data)
        with db.connect(self.dst) as c:
            self.assertEqual(db.get_game(c, 1)["is_unplayed"], 0)
            self.assertEqual(db.get_game(c, 1)["is_favorite"], 1)


if __name__ == "__main__":
    unittest.main()
