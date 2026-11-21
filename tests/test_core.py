import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from geebot import lrc, textutil as tu
from geebot.db import DB, Track


class LrcTests(unittest.TestCase):
    TXT = "[00:01.50]ඒක\n[00:05.00]දෙක\n[01:02.25]තුන"

    def test_parse_roundtrip(self):
        ls = lrc.parse(self.TXT)
        self.assertEqual(ls[0], (1.5, "ඒක"))
        self.assertEqual(ls[2][0], 62.25)
        self.assertEqual(lrc.parse(lrc.dumps(ls)), ls)

    def test_current_index(self):
        ls = lrc.parse(self.TXT)
        self.assertEqual(lrc.current_index(ls, 0.5), -1)
        self.assertEqual(lrc.current_index(ls, 5.0), 1)
        self.assertEqual(lrc.current_index(ls, 99), 2)

    def test_chunk_fits_state_limit(self):
        ls = [(i * 4.0, "සිංහල පද පේළියක් මෙහෙමයි " + str(i)) for i in range(60)]
        js, nxt = lrc.widget_chunk(ls, 0, 7)
        self.assertLessEqual(len(js.encode()), 1024)
        d = json.loads(js)
        self.assertEqual(d["r"], 7)
        self.assertEqual(len(d["L"]), nxt)
        self.assertGreater(nxt, 3)

    def test_plain_lines(self):
        self.assertEqual(lrc.plain_lines("a\n\n b "), ["a", "b"])
        self.assertEqual(lrc.plain_lines(self.TXT)[0], "ඒක")


class TextTests(unittest.TestCase):
    def test_roman(self):
        self.assertEqual(tu.roman("මල්"), "mal")
        self.assertEqual(tu.roman("අම්මා"), "ammaa")
        self.assertEqual(tu.roman("ආදරේ"), "aadaree")
        self.assertEqual(tu.roman("ශ්‍රී"), "shrii")

    def test_similarity(self):
        self.assertGreater(tu.similarity("ආදරේ", "ආදරේ සින්දුව"), 0.8)
        self.assertGreater(tu.similarity("Dangal Movie", "dangal"), 0.8)
        self.assertLess(tu.similarity("කුරුලු", "ගෙදර"), 0.6)

    def test_rhyme(self):
        v = ["මල", "කල", "පැල", "ගහ", "සඳ"]
        self.assertIn("කල", tu.rhymes("මල", v))
        self.assertNotIn("ගහ", tu.rhymes("මල", v))
        self.assertEqual(tu.graphemes("කා")[0], "කා")


class DBTests(unittest.TestCase):
    def setUp(self):
        self.p = tempfile.mktemp(suffix=".sqlite")
        self.db = DB(self.p)

    def tearDown(self):
        os.path.exists(self.p) and os.remove(self.p)

    def test_track_roundtrip_keeps_lyrics(self):
        self.db.upsert_track(Track("up:1", "සඳ", "කවුරුහරි", lrc="[00:01.00]x"))
        self.db.upsert_track(Track("up:1", "සඳ", "කවුරුහරි"))   # refresh without lyrics
        self.assertEqual(self.db.track("up:1").lrc, "[00:01.00]x")

    def test_takedown_hides(self):
        self.db.upsert_track(Track("up:2", "t", "a"))
        self.db.x("UPDATE tracks SET takedown=1 WHERE id='up:2'")
        self.assertIsNone(self.db.track("up:2"))

    def test_fav_and_premium_and_games(self):
        self.db.touch_user({"id": 5, "first_name": "A", "username": "Ab", "language_code": "si"})
        self.assertEqual(self.db.user(5)["username"], "ab")
        self.assertTrue(self.db.toggle_fav(5, "x")); self.assertFalse(self.db.toggle_fav(5, "x"))
        self.assertFalse(self.db.is_premium(5)); self.db.add_premium(5, 30); self.assertTrue(self.db.is_premium(5))
        self.db.game_set(1, "chain", {"a": 1}); self.assertEqual(self.db.game_get(1, "chain"), {"a": 1})
        self.db.add_score(1, 5, "A", "g", 3); self.db.add_score(1, 5, "A", "g", 2)
        self.assertEqual(self.db.leaderboard(1)[0]["p"], 5)


if __name__ == "__main__":
    unittest.main()
