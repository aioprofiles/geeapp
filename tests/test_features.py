import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from geebot import features as f, cards
from geebot.db import DB, Track
from geebot.config import Config


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.p = tempfile.mktemp(); self.db = DB(self.p)
        for i in range(3):
            self.db.upsert_track(Track(f"t{i}", f"song{i}", "A" if i < 2 else "B", duration=200))
        for u in (1, 2):
            self.db.touch_user({"id": u, "first_name": f"U{u}", "username": f"u{u}"})

    def tearDown(self): os.path.exists(self.p) and os.remove(self.p)

    def test_wrapped(self):
        yr = time.gmtime().tm_year
        for t in ("t0", "t0", "t1"): self.db.log_play(1, t)
        w = f.wrapped(self.db, 1, yr)
        self.assertEqual(w["plays"], 3); self.assertEqual(w["top_tracks"][0][0][0], "song0")
        md, html = f.wrapped_text(w, yr, "Kasun", "bot"); self.assertIn("song0", md); self.assertIn("song0", html)
        self.assertIsNone(f.wrapped(self.db, 2, yr))

    def test_taste(self):
        self.db.toggle_fav(1, "t0"); self.db.toggle_fav(1, "t2"); self.db.toggle_fav(2, "t0"); self.db.toggle_fav(2, "t1")
        m = f.taste(self.db, 1, 2); self.assertEqual(m["tracks"], ["t0"]); self.assertEqual(m["artists"], ["A"])

    def test_dedication_flow(self):
        f.add_dedication(self.db, 1, "@U2", "t0", "happy bday", int(time.time()) - 5)
        f.add_dedication(self.db, 1, "u2", "t1", "later", int(time.time()) + 999)
        due = f.due_dedications(self.db); self.assertEqual(len(due), 1)
        self.assertEqual(f.recipient_id(self.db, "@U2"), 2); self.assertIsNone(f.recipient_id(self.db, "nobody"))

    def test_diary_and_contrib_badges(self):
        f.add_diary(self.db, 1, "t0", "note", remind_after_days=0); self.assertEqual(len(f.due_diary(self.db)), 1)
        cid = self.db.x("INSERT INTO contribs(user_id,track_id,lrc,ts) VALUES(1,'t0','[00:01.00]x',1)")
        r = f.approve_contrib(self.db, cid)
        self.assertEqual(r["new_badges"], ["Lyrics Helper"]); self.assertEqual(self.db.track("t0").lrc, "[00:01.00]x")
        self.assertIsNone(f.approve_contrib(self.db, cid))

    def test_reel_licence_gate(self):
        self.assertTrue(f.lyric_reel_ok("https://creativecommons.org/licenses/by/3.0/"))
        self.assertFalse(f.lyric_reel_ok("https://creativecommons.org/licenses/by-nd/3.0/"))
        self.assertFalse(f.lyric_reel_ok(""))

    def test_cards(self):
        cfg = Config(bot_username="b", webapp_url="https://x.y", app_short="player")
        t = Track("jm:1", "T&C", "Art", duration=65, license="https://creativecommons.org/licenses/by/3.0/")
        md, html = cards.card_text(t); self.assertIn("1:05", md); self.assertIn("T&amp;C", html)
        priv = cards.card_kb(cfg, t, False, True); grp = cards.card_kb(cfg, t, False, False)
        self.assertIn("web_app", priv[0][0]); self.assertIn("url", grp[0][0])
        self.assertTrue(all(len(b.get("callback_data", "")) <= 64 for r in priv for b in r))


if __name__ == "__main__":
    unittest.main()
