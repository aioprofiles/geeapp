import os, random, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from geebot import games as g
from geebot.db import Track

LRC = "\n".join(f"[00:{i*4:02d}.00]ඒක දෙක තුන හතර {i}" for i in range(10))


def T(i, artist="A", **kw):
    return Track(f"x:{i}", f"song {i}", artist, audio_url="u", **kw)


class GameTests(unittest.TestCase):
    def test_daily_is_deterministic_and_changes(self):
        ts = [T(i) for i in range(30)]
        self.assertEqual(g.daily_track("2026-11-21", ts).id, g.daily_track("2026-11-21", list(reversed(ts))).id)
        days = {g.daily_track(f"2026-11-{d:02d}", ts).id for d in range(1, 29)}
        self.assertGreater(len(days), 5)

    def test_heardle_share_and_clip(self):
        self.assertEqual(g.clip_seconds(0), 1); self.assertEqual(g.clip_seconds(99), 16)
        self.assertEqual(g.share_row("d", ["x", "x", "w"], True).split("\n")[1], "🟥🟥🟩⬛⬛⬛")
        self.assertTrue(g.guess_ok("song 3", T(3)))
        self.assertFalse(g.guess_ok("zzzzz", T(3)))
        self.assertEqual(g.next_streak("2026-11-20", "2026-11-21", 4, "2026-11-20"), 5)
        self.assertEqual(g.next_streak("2026-11-10", "2026-11-21", 4, "2026-11-20"), 1)

    def test_missing_word(self):
        t = Track("l", "t", "a", lrc=LRC)
        q = g.missing_word(t, random.Random(1), ["කුරුල්ලා", "මුහුදු", "සඳ්‍රකාන්ත", "වැස්සක්"])
        self.assertIn("____", q["question"]); self.assertEqual(len(set(q["options"])), len(q["options"]))
        self.assertTrue(0 <= q["correct"] < len(q["options"]))

    def test_scramble_answer_reconstructs(self):
        t = Track("l", "t", "a", plain="\n".join(f"line number {i} here" for i in range(8)))
        s = g.scramble(t, random.Random(3))
        order = [s["shown"][n - 1] for n in s["answer"]]
        self.assertEqual(order, sorted(order))       # reading order restored
        self.assertTrue(g.check_scramble(" ".join(map(str, s["answer"])), s["answer"]))

    def test_chain(self):
        self.assertTrue(g.chain_check("ඒක දෙක තුන හතර 3", "ඒක දෙක තුන හතර 3"))
        self.assertFalse(g.chain_check("completely different", "ඒක දෙක තුන හතර 3"))

    def test_odd_and_before_after(self):
        ts = [T(i, "A", year=2000 + i) for i in range(3)] + [T(9, "B", year=1999)]
        q = g.odd_one_out(ts, random.Random(2)); self.assertEqual(q["options"][q["correct"]], "song 9")
        ba = g.before_after(ts, random.Random(1)); self.assertIn(ba["options"][ba["correct"]], [t.title for t in ts])

    def test_bingo(self):
        pool = [f"tag{i}" for i in range(12)]
        card = g.bingo_card(7, pool)
        self.assertEqual(card, g.bingo_card(7, pool))
        marks = {(0, 0), (1, 1), (2, 2)}; self.assertTrue(g.bingo_win(marks))
        self.assertFalse(g.bingo_win({(0, 0), (1, 2)}))
        t = Track("b", "t", "x", tags=card[0][0]); self.assertIn((0, 0), g.bingo_marks(card, t))

    def test_wordhunt_and_taste(self):
        t = Track("w", "මල් සින්දුව", "a", plain="මල් පිපෙනවා")
        self.assertIs(g.wordhunt_valid("මල්", "මල් සින්දුව", [t]), t)
        self.assertIsNone(g.wordhunt_valid("ගඟ", "මල් සින්දුව", [t]))
        m = g.taste_match({"a", "b"}, {"b", "c"}, {"x"}, {"x", "y"})
        self.assertEqual(m["tracks"], ["b"]); self.assertGreater(m["percent"], 0)


if __name__ == "__main__":
    unittest.main()
