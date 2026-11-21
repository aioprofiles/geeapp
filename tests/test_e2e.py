import asyncio, json, os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.fakes import FakeTg
from geebot import admin, group, guest, main, sched, user, wq, features
from geebot.app import Ctx
from geebot.config import Config
from geebot.db import DB, Track
from geebot.llm import LLM
from geebot.sources import Jamendo, Lrclib
from geebot.webauth import sign_for_test, validate_init_data

LRC = "\n".join(f"[00:{i * 4:02d}.00]ඒක දෙක තුන හතර {i}" for i in range(12))
FF = shutil.which("ffmpeg")


def run(c): return asyncio.run(c)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = Config(bot_token="1:T", bot_username="gb", owner_ids={999}, webapp_url="https://w.example",
                          media_dir=self.d, db_path=os.path.join(self.d, "t.sqlite"), free_dl_per_day=1)
        self.db = DB(self.cfg.db_path)
        self.tg = FakeTg()
        self.ctx = Ctx(self.cfg, self.db, self.tg, LLM("x"), Jamendo(""), Lrclib())
        self.src = os.path.join(self.d, "s.mp3")
        if FF:
            os.system(f"ffmpeg -y -v error -f lavfi -i sine=frequency=440:duration=20 -c:a libmp3lame {self.src}")

        async def fake_audio(ctx, t): return self.src if FF else None
        user.audio_path = group.audio_path = wq.audio_path = fake_audio
        for i in range(5):
            self.db.upsert_track(Track(f"t{i}", f"පළමු සින්දුව {i}", "ගායකයා" if i < 4 else "වෙන කෙනා", duration=200, year=2000 + i,
                                       audio_url="http://x/a.mp3", downloadable=1, lrc=LRC, tags="rock,calm",
                                       license="https://creativecommons.org/licenses/by/3.0/"))
        for u in (1, 2, 999):
            self.db.touch_user({"id": u, "first_name": f"U{u}", "username": f"u{u}", "language_code": "en"})

    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def msg(self, text, uid=1, chat=None, ctype="private", **kw):
        return {"message_id": 1, "from": {"id": uid, "first_name": f"U{uid}", "username": f"u{uid}"},
                "chat": {"id": chat or uid, "type": ctype}, "text": text, **kw}

    def cb(self, data, uid=1, chat=None, ctype="private"):
        return {"id": "c1", "from": {"id": uid, "first_name": f"U{uid}"}, "data": data, "chat_instance": "CI1",
                "message": {"message_id": 5, "chat": {"id": chat or uid, "type": ctype}}}

    def send(self, text, **kw): run(main.on_message(self.ctx, self.msg(text, **kw)))
    def press(self, data, **kw): run(main.on_callback(self.ctx, self.cb(data, **kw)))


class PrivateFlows(Base):
    def test_search_card_fav(self):
        self.send("පළමු සින්දුව 2")
        rows = self.tg.calls("send")[-1][0][2]
        self.assertTrue(any("c:t2" in b["callback_data"] for r in rows for b in r))
        self.press("c:t2"); self.assertTrue(self.tg.calls("send_rich"))
        self.press("fv:t2"); self.assertTrue(self.db.is_fav(1, "t2"))
        self.press("fv:t2"); self.assertFalse(self.db.is_fav(1, "t2"))

    @unittest.skipUnless(FF, "ffmpeg")
    def test_download_quota_and_premium(self):
        self.press("dl:t0"); self.assertEqual(len(self.tg.calls("send_audio_bytes")), 1)
        self.assertEqual(len(self.tg.calls("send_doc_bytes")), 1)            # .lrc file
        self.press("dl:t1"); self.assertEqual(len(self.tg.calls("send_audio_bytes")), 1)  # blocked by free limit
        self.db.add_premium(1, 30); self.press("dl:t1")
        self.assertEqual(len(self.tg.calls("send_audio_bytes")), 2)

    @unittest.skipUnless(FF, "ffmpeg")
    def test_heardle_flow_win_and_streak(self):
        self.send("/heardle"); self.assertEqual(len(self.tg.calls("send_audio_bytes")), 1)
        from geebot import games
        from geebot.util import today
        t = games.daily_track(today(self.cfg.tz_offset_min), self.db.tracks())
        self.send("totally wrong"); self.assertEqual(len(self.tg.calls("send_audio_bytes")), 2)   # longer clip
        self.send(t.title)
        txt = "\n".join(self.tg.texts()); self.assertIn("🟥🟩", txt); self.assertEqual(self.db.user(1)["streak"], 1)
        self.send("/heardle"); self.assertIn("🟩", self.tg.texts()[-1])                          # already done today

    def test_dedication_to_registered_user(self):
        self.send("/dedicate"); self.send("පළමු සින්දුව 1"); self.press("dd:t1")
        self.send("@u2 සුබ උපන්දිනයක්"); self.press("dw:n")
        self.assertEqual(len(self.db.q("SELECT * FROM dedications")), 1)
        run(sched.tick(self.ctx))
        self.assertTrue(any(a[0] == 2 for n, a, k in self.tg.log if n == "send"))           # delivered to user 2
        self.assertEqual(self.db.one("SELECT sent FROM dedications")["sent"], 1)

    def test_dedication_unknown_recipient_gets_link(self):
        features.add_dedication(self.db, 1, "@ghost", "t1", "hi", int(time.time()) - 1)
        run(sched.tick(self.ctx))
        self.assertEqual(self.db.one("SELECT sent FROM dedications")["sent"], 2)
        self.assertIn("ded_", str(self.tg.calls("sendMessage")[-1][1]["text"]))

    def test_diary_and_playlist_flow(self):
        self.press("di:t0"); self.send("මතකයක්")
        self.assertEqual(len(self.db.q("SELECT * FROM diary")), 1)
        self.press("pn:t0"); self.send("My list")
        self.assertEqual(len(self.db.q("SELECT * FROM pl_items")), 1)

    def test_banned_user_ignored(self):
        self.db.x("UPDATE users SET banned=1 WHERE id=1"); self.send("/help"); self.assertFalse(self.tg.log)

    def test_command_for_other_bot_ignored(self):
        self.send("/help@otherbot"); self.assertFalse(self.tg.log)
        self.send("/help@gb"); self.assertTrue(self.tg.log)

    def test_payment_grants_premium(self):
        m = self.msg("", successful_payment={"invoice_payload": "prem30"}); del m["text"]
        run(main.on_message(self.ctx, m)); self.assertTrue(self.db.is_premium(1))


class WidgetFlows(Base):
    def test_karaoke_widget_and_chunk_refill(self):
        self.press("w:t0")
        (a, k), = self.tg.calls("sendWidget")
        self.assertLessEqual(len(k["chat_data"].encode()), 1024); self.assertLessEqual(len(k["public_data"].encode()), 1024)
        self.assertIn("startapp", k["public_data"])
        mid = self.tg.mid
        q = {"id": "q1", "from": {"id": 1}, "chat": {"id": 1}, "message_id": mid, "data": "m:20.0"}
        run(wq.handle(self.ctx, q))
        self.assertEqual(self.tg.calls("answer_widget")[-1][0][1], "")
        (a2, k2), = self.tg.calls("edit_widget")
        d = json.loads(k2["chat_data"]); self.assertEqual(d["r"], 2); self.assertTrue(d["L"][0][0] > 20.0)

    def test_widget_unknown_message_and_beat_score_validation(self):
        run(wq.handle(self.ctx, {"id": "q", "from": {"id": 1}, "chat": {"id": 1}, "message_id": 9999, "data": "m:1"}))
        self.assertEqual(self.tg.calls("answer_widget")[-1][0][1], "expired")
        self.send("/beat"); mid = self.tg.mid
        run(wq.handle(self.ctx, {"id": "q", "from": {"id": 1, "first_name": "A"}, "chat": {"id": 1}, "message_id": mid, "data": "s:999"}))
        self.assertEqual(self.tg.calls("answer_widget")[-1][0][1], "invalid")
        run(wq.handle(self.ctx, {"id": "q", "from": {"id": 1, "first_name": "A"}, "chat": {"id": 1}, "message_id": mid, "data": "s:45"}))
        self.assertIn("saved", self.tg.calls("answer_widget")[-1][0][1])


class GroupFlows(Base):
    G = dict(chat=-50, ctype="supergroup")

    @unittest.skipUnless(FF, "ffmpeg")
    def test_duel_scores_first_correct(self):
        self.send("/duel", uid=1, **self.G)
        st = self.db.game_get(-50, "duel"); t = self.db.track(st["track"])
        self.send(t.title, uid=2, **self.G)
        self.assertEqual(self.db.leaderboard(-50)[0]["user_id"], 2)

    def test_chain_scramble(self):
        self.send("/chain", uid=1, **self.G)
        st = self.db.game_get(-50, "chain"); nxt = LRC.splitlines()[st["i"] + 1].split("]")[1]
        self.send(nxt, uid=2, **self.G); self.assertEqual(self.db.leaderboard(-50)[0]["p"], 3)
        self.send("/scramble", uid=1, **self.G)
        s = self.db.game_get(-50, "scramble"); self.send(" ".join(map(str, s["answer"])), uid=2, **self.G)
        self.assertEqual(self.db.leaderboard(-50)[0]["p"], 7)

    def test_quiz_polls_and_scoring(self):
        rich = "\n".join(f"[00:{i * 4:02d}.00]{l}" for i, l in enumerate(
            ["කුරුල්ලෝ ගී ගයනවා උදේ", "සඳ එළියේ මුහුද නටනවා", "වැස්සක් වගේ ආදරේ වැටුණා", "මල් පිපෙන කාලේ ආවා"]))
        self.db.upsert_track(Track("rich", "පොහොසත්", "x", lrc=rich))
        self.send("/missing", uid=1, **self.G); (a, k), = self.tg.calls("sendPoll")
        self.assertEqual(k["type"], "quiz"); self.assertIn("correct_option_ids", k)
        pid = f"poll{self.tg.mid}"; info = self.db.kv_get(f"poll:{pid}")
        run(group.poll_answer(self.ctx, {"poll_id": pid, "user": {"id": 2, "first_name": "B"}, "option_ids": [info["correct"]]}))
        run(group.poll_answer(self.ctx, {"poll_id": pid, "user": {"id": 1, "first_name": "A"}, "option_ids": [(info["correct"] + 1) % 3]}))
        lb = self.db.leaderboard(-50); self.assertEqual((lb[0]["user_id"], lb[0]["p"]), (2, 2)); self.assertEqual(len(lb), 1)

    def test_voice_contest_vote_and_end(self):
        self.send("/roulette", uid=1, **self.G); prompt = self.tg.mid
        v = self.msg("", uid=2, reply_to_message={"message_id": prompt}, voice={"file_id": "x"}, **self.G); del v["text"]
        run(main.on_message(self.ctx, v))
        self.press("cv:1", uid=3, chat=-50, ctype="supergroup"); self.press("cv:1", uid=2, chat=-50, ctype="supergroup")  # self-vote refused
        self.assertEqual(len(self.db.game_get(-50, "contest")["entries"]["1"]["votes"]), 1)
        run(group.contest_end(self.ctx, -50)); self.assertEqual(self.db.leaderboard(-50)[0]["user_id"], 2)

    def test_wordhunt_timer_job(self):
        self.send("/wordhunt සින්දුව", uid=1, **self.G); self.send("පළමු සින්දුව 3", uid=2, **self.G)
        self.db.x("UPDATE jobs SET run_at=0"); run(sched.tick(self.ctx))
        self.assertEqual(self.db.leaderboard(-50)[0]["user_id"], 2); self.assertIsNone(self.db.game_get(-50, "wordhunt"))

    def test_settings_admin_only_and_cooldown(self):
        self.send("/settings", uid=1, **self.G); self.assertIn("Admins only", self.tg.texts()[-1] + str(self.tg.calls("sendMessage")))
        self.send("/settings", uid=999, **self.G); self.press("gs:who", uid=999, chat=-50, ctype="supergroup")
        self.assertEqual(self.db.gs(-50)["who"], "admins")
        self.send("/chain", uid=1, **self.G)                         # normal member now blocked
        self.assertIsNone(self.db.game_get(-50, "chain"))

    def test_party_start_uses_chat_instance(self):
        self.press("pt:t1", chat=-50, ctype="supergroup")
        p = self.db.one("SELECT * FROM party"); self.assertEqual((p["chat_instance"], p["track_id"]), ("CI1", "t1"))

    def test_bingo_and_hum(self):
        for i in range(9): self.db.upsert_track(Track(f"b{i}", f"b{i}", f"artist{i}", tags=f"tag{i}"))
        self.send("/bingo", uid=1, **self.G); st = self.db.game_get(-50, "bingo")
        self.assertIn("1", st["players"])
        self.send("/hum පළමු සින්දුව 1", uid=1); self.send("/hum", uid=1, **self.G)
        self.send("පළමු සින්දුව 1", uid=2, **self.G); self.assertEqual(self.db.leaderboard(-50)[0]["p"], 4)

    def test_team_battle(self):
        self.send("/team", uid=1, **self.G); self.press("tj:A", uid=1, chat=-50, ctype="supergroup"); self.press("tj:B", uid=2, chat=-50, ctype="supergroup")
        self.send("/team theme rain", uid=1, **self.G)
        self.send("/pick පළමු සින්දුව 1", uid=1, **self.G); self.send("/pick පළමු සින්දුව 2", uid=2, **self.G)
        self.assertEqual(len(self.tg.calls("sendPoll")), 1)
        self.db.x("UPDATE jobs SET run_at=0"); run(sched.tick(self.ctx))
        self.assertEqual(self.db.leaderboard(-50)[0]["user_id"], 1)       # fake poll: A wins 3-1

    def test_tournament_resets_board_window(self):
        self.send("/tournament", uid=999, **self.G); self.assertIsNotNone(self.db.kv_get("tour:-50"))
        self.send("/tournament end", uid=999, **self.G); self.assertIsNone(self.db.kv_get("tour:-50"))


class GuestAndAdmin(Base):
    def test_guest_song_lookup_and_no_match(self):
        run(guest.handle(self.ctx, {"guest_query_id": "g1", "text": "@gb", "reply_to_message": {"text": "පළමු සින්දුව 3"}}))
        (a, k), = self.tg.calls("answer_guest"); self.assertIn("පළමු සින්දුව 3", a[1]); self.assertTrue(k["rows"])
        run(guest.handle(self.ctx, {"guest_query_id": "g2", "text": "@gb zzzzqqq"}))
        self.assertEqual(self.tg.calls("answer_guest")[-1][1]["title"], "No match")

    def test_upload_requires_artist_and_contrib_approval(self):
        a = {"file_id": "F", "file_unique_id": "U1", "duration": 100}
        m = self.msg("", uid=2, audio=a, caption="Song | Me | CC BY | download=yes"); del m["text"]
        run(main.on_message(self.ctx, m)); self.assertIsNone(self.db.track("up:U1"))
        run(admin.cmd_artist(self.ctx, self.msg("", uid=999), "2")); run(main.on_message(self.ctx, m))
        t = self.db.track("up:U1"); self.assertEqual((t.artist, t.downloadable, t.uploader), ("Me", 1, 2))
        cid = self.db.x("INSERT INTO contribs(user_id,track_id,lrc,ts) VALUES(2,'up:U1','[00:01.00]x',1)")
        self.press(f"ap:{cid}", uid=999); self.assertEqual(self.db.track("up:U1").lrc, "[00:01.00]x")
        self.assertTrue(self.db.one("SELECT 1 x FROM badges WHERE user_id=2"))

    def test_takedown_and_channel_daily_post(self):
        self.send("/takedown t0", uid=999); self.assertIsNone(self.db.track("t0"))
        self.send("/channel add @ch 0", uid=999)
        self.assertTrue(self.db.one("SELECT 1 x FROM channels"))
        run(sched.tick(self.ctx)); run(sched.tick(self.ctx))
        self.assertEqual(len([1 for n, a, k in self.tg.log if n == "send_rich" and a[0] == -1001]), 1)  # once per day


class WebAuth(unittest.TestCase):
    def test_init_data(self):
        f = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 7, "first_name": "A"}), "chat_instance": "CI"}
        s = sign_for_test(f, "1:TOKEN")
        self.assertEqual(validate_init_data(s, "1:TOKEN")["user"]["id"], 7)
        self.assertIsNone(validate_init_data(s, "1:OTHER")); self.assertIsNone(validate_init_data(s.replace("A", "B"), "1:TOKEN"))
        old = sign_for_test({**f, "auth_date": str(int(time.time()) - 999999)}, "1:TOKEN")
        self.assertIsNone(validate_init_data(old, "1:TOKEN"))
        self.assertIsNone(validate_init_data("garbage", "1:TOKEN"))


if __name__ == "__main__":
    unittest.main()
