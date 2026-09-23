"""Tests for the "In Collection" (no status checked) BGG status. No network."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bgg  # noqa: E402
import db  # noqa: E402
from tests.test_backup import DbCase, _game  # noqa: E402

FLAGS = ("own", "prevowned", "fortrade", "want", "wanttoplay", "wanttobuy",
         "wishlist", "preordered")


def _item(oid, name, collid=1, **on):
    attrs = " ".join(f'{f}="{1 if on.get(f) else 0}"' for f in FLAGS)
    return (f'<item objecttype="thing" objectid="{oid}" collid="{collid}">'
            f'<name>{name}</name><status {attrs} lastmodified="2026-01-01"/></item>')


def _root(*items):
    return ET.fromstring("<items>" + "".join(items) + "</items>")


def _row_from_entry(e):
    """Same own/bgg_status mapping the sync code uses."""
    return {"bgg_id": e.bgg_id, "name": e.name,
            "own": 1 if e.bgg_status in (None, "own") else 0,
            "bgg_status": e.bgg_status}


class BggStatusTests(DbCase):
    def test_constants(self):
        self.assertEqual(bgg.STATUS_FLAGS[-1], "incollection")
        self.assertEqual(bgg.STATUS_LABELS["incollection"], "In Collection")
        self.assertEqual(set(bgg.STATUS_COLORS["incollection"]), {"bg", "text"})
        self.assertEqual(set(bgg.STATUS_LABELS), set(bgg.STATUS_FLAGS))
        self.assertEqual(set(bgg.STATUS_COLORS), set(bgg.STATUS_FLAGS))

    def test_all_zero_row_is_incollection_and_not_owned(self):
        entries = bgg.parse_collection_xml(_root(_item(1, "Rivals")))
        self.assertEqual(entries[0].bgg_status, "incollection")
        self.assertFalse(entries[0].own)
        with db.connect(self.dst) as c:
            db.upsert_game(c, _row_from_entry(entries[0]))
            g = db.get_game(c, 1)
            self.assertEqual((g["own"], g["bgg_status"]), (0, "incollection"))
            self.assertEqual(len(db.list_games(c)), 0, "not in the default Owned view")
            self.assertEqual(len(db.list_games(c, status=["incollection"])), 1)

    def test_real_flags_unchanged(self):
        e = bgg.parse_collection_xml(_root(
            _item(2, "Buy", wanttobuy=True), _item(3, "Mine", own=True)))
        self.assertEqual([x.bgg_status for x in e], ["wanttobuy", "own"])
        self.assertEqual([x.own for x in e], [False, True])

    def test_duplicate_rows_or_merge_own_wins(self):
        for order in ((True, False), (False, True)):
            rows = [_item(5, "Dup", collid=i + 1, **({"own": True} if o else {}))
                    for i, o in enumerate(order)]
            e = bgg.parse_collection_xml(_root(*rows))
            self.assertEqual(len(e), 1)
            self.assertEqual((e[0].bgg_status, e[0].own), ("own", True))
        e = bgg.parse_collection_xml(_root(
            _item(6, "D", collid=1), _item(6, "D", collid=2, wishlist=True)))
        self.assertEqual(e[0].bgg_status, "wishlist")

    def test_csv_all_zero_row(self):
        p = self.tmp / "c.csv"
        p.write_text("objectid,objectname," + ",".join(FLAGS) + "\n"
                     "9,Zero," + ",".join("0" for _ in FLAGS) + "\n"
                     "10,Owned,1," + ",".join("0" for _ in FLAGS[1:]) + "\n",
                     encoding="utf-8")
        g = bgg.import_collection_csv(p)
        self.assertEqual([x.bgg_status for x in g], ["incollection", "own"])

    def test_backup_round_trip(self):
        with db.connect(self.src) as c:
            self.insert_game(c, _game(77, "Rated Only", own=0, bgg_status="incollection"))
        with db.connect(self.src) as c:
            payload = json.loads(json.dumps(db.build_backup_payload(c), default=str))
        self.restore(self.dst, payload)
        with db.connect(self.dst) as c:
            g = db.get_game(c, 77)
            self.assertEqual((g["own"], g["bgg_status"]), (0, "incollection"))

    def test_resync_corrects_previously_owned_row(self):
        with db.connect(self.dst) as c:
            self.insert_game(c, _game(1, "Rivals", bgg_status=None))
            e = bgg.parse_collection_xml(_root(_item(1, "Rivals")))[0]
            db.upsert_game(c, _row_from_entry(e))
            g = db.get_game(c, 1)
            self.assertEqual((g["own"], g["bgg_status"]), (0, "incollection"))
            # manual override protection is unchanged
            db.upsert_game(c, {"bgg_id": 1, "name": "Rivals", "own": 1,
                               "bgg_status": "own"})
            db.upsert_game(c, _row_from_entry(e), skip_fields={"bgg_status", "own"})
            self.assertEqual(db.get_game(c, 1)["bgg_status"], "own")
