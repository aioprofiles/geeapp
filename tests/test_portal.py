import asyncio, json, os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.fakes import FakeTg
from geebot import commands, donate, main, nav, rich as R, sched, screens, theme
from geebot.app import Ctx
from geebot.config import Config
from geebot.db import DB, Track
from geebot.llm import LLM
from geebot.sources import Jamendo, Lrclib
from geebot.tg import Tg, TgError


def run(c): return asyncio.run(c)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = Config(bot_token="1:T", bot_username="gb", owner_ids={999}, webapp_url="https://w.example",
                          media_dir=self.d, db_path=os.path.join(self.d, "t.sqlite"), donate_max_stars=10000)
        self.db = DB(self.cfg.db_path); self.tg = FakeTg()
        self.ctx = Ctx(self.cfg, self.db, self.tg, LLM("x"), Jamendo(""), Lrclib())
        for i in range(12):
            self.db.upsert_track(Track(f"t{i}", f"Song & {i}", "A<B>", duration=200, year=2000, lrc="[00:01.00]x", downloadable=1,
                                       license="https://creativecommons.org/licenses/by/3.0/"))
        for u in (1, 2, 999):
            self.db.touch_user({"id": u, "first_name": f"U{u}", "username": f"u{u}", "language_code": "en"})

    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def msg(self, text, uid=1, ctype="private", **kw):
        return {"message_id": 1, "from": {"id": uid, "first_name": f"U{uid}"}, "chat": {"id": uid, "type": ctype}, "text": text, **kw}

    def cb(self, data, uid=1, mid=50):
        return {"id": "c", "from": {"id": uid, "first_name": f"U{uid}"}, "data": data, "chat_instance": "CI",
                "message": {"message_id": mid, "chat": {"id": uid, "type": "private"}}}

    def send(self, text, **kw): run(main.on_message(self.ctx, self.msg(text, **kw)))
    def press(self, data, **kw): run(main.on_callback(self.ctx, self.cb(data, **kw)))


class RichBuilders(unittest.TestCase):
    def test_escape_once_no_double_escaping(self):
        h = R.doc(R.heading("Best & Fast <v2>"), R.table([("A & B", "x")]), R.para("1 < 2"))
        self.assertIn("Best &amp; Fast &lt;v2&gt;", h); self.assertNotIn("&amp;amp;", h)
        self.assertEqual(R.esc(R.Raw("<b>x</b>")), "<b>x</b>")                     # Raw is never re-escaped
        self.assertEqual(R.doc(R.details("S&T", R.table([("a", "b")]))).count("<table>"), 1)

    def test_structures_and_plain_fallback(self):
        h = R.doc(R.heading("T"), R.kv_table([("k", "v")]), R.details("More", "hidden", open=True), R.footer("Page 1/2"))
        self.assertIn("<details open><summary>More</summary>", h)
        p = R.to_plain(h); self.assertIn("k — v", p); self.assertIn("Page 1/2", p); self.assertNotIn("<", p)
        self.assertIn('class="language-py"', R.pre("x=1", "py"))


class Theme(unittest.TestCase):
    def test_styles(self):
        self.assertEqual(theme.B("a", "d", "success")["style"], "success")
        self.assertNotIn("style", theme.B("a", "d", "muted"))
        self.assertNotIn("style", theme.B("a", url="https://x", role="link"))      # 'link' only for callback buttons
        self.assertEqual(theme.B("a", "d", "link")["style"], "link")
        self.assertEqual(theme.B("a", "d", icon="123")["icon_custom_emoji_id"], "123")
        self.assertEqual([len(r) for r in theme.grid(list(range(5)), 2)], [2, 2, 1])


class Screens(Base):
    def _check(self, rows):
        flat = [b for r in rows for b in r]
        self.assertLessEqual(len(flat), 100); self.assertTrue(all(len(r) <= 8 for r in rows))
        for b in flat:
            self.assertTrue(b["text"]); 
            if "callback_data" in b: self.assertLessEqual(len(b["callback_data"].encode()), 64)

    def test_home_admin_button_only_for_owner(self):
        h, rows = screens.home(self.ctx, 1); self._check(rows)
        self.assertNotIn("n:admin", str(rows)); self.assertIn("Heardle streak", h)
        self.assertIn("n:admin", str(screens.home(self.ctx, 999)[1]))
        self.assertNotIn("&amp;amp;", h)

    def test_song_card_and_every_screen_within_limits(self):
        t = self.db.track("t3"); h, rows = screens.song_card(self.ctx, 1, t); self._check(rows)
        self.assertIn("Song &amp; 3", h); self.assertIn("A&lt;B&gt;", h); self.assertIn("Creative Commons", h)
        for fn in (screens.faq, lambda: screens.settings(self.ctx, 1), lambda: screens.about(self.ctx),
                   lambda: screens.admin(self.ctx), lambda: donate.home(self.ctx, 1), lambda: donate.wall(self.ctx)):
            self._check(fn()[1])

    def test_paging_buttons(self):
        ids = [f"t{i}" for i in range(12)]
        def page(p): return screens.results(ids, [self.db.track(i) for i in ids[p * 5:p * 5 + 5]], p, "R")
        txt = lambda rows: str(rows)
        self.assertNotIn("Prev", txt(page(0)[1])); self.assertIn("Next", txt(page(0)[1]))
        self.assertIn("Prev", txt(page(1)[1])); self.assertIn("Next", txt(page(1)[1]))
        self.assertNotIn("Next", txt(page(2)[1])); self.assertIn("Page 3/3 · 12 songs", page(2)[0])


class Navigation(Base):
    def test_results_edit_in_place_and_expiry(self):
        run(nav.send_results(self.ctx, 1, [self.db.track(f"t{i}") for i in range(12)], "Found"))
        mid = self.tg.mid
        self.press("n:res:1", mid=mid)
        (a, k), = self.tg.calls("edit_rich"); self.assertEqual((a[0], a[1]), (1, mid)); self.assertIn("Page 2/3", a[2])
        self.press("n:res:1", mid=9999)                                              # unknown/expired list
        self.assertTrue(self.tg.calls("answer_cb")[-1][1]["alert"])

    def test_search_uses_paged_results_and_keeps_state(self):
        self.send("Song")
        self.assertTrue(self.db.kv_get(f"res:1:{self.tg.mid}")["ids"]); self.assertIn("Page 1/2 · 10 songs", self.tg.calls("rich")[-1][0][1])

    def test_privacy_language_and_command_whitelist(self):
        self.press("n:pv"); self.assertEqual(self.db.user(1)["privacy"], 1)
        self.db.add_score(5, 1, "Kasun", "g", 3); self.assertEqual(self.db.leaderboard(5)[0]["name"], "Anonymous")
        self.press("n:pv"); self.assertEqual(self.db.user(1)["privacy"], 0)
        self.press("n:lang:ta"); self.assertEqual(self.db.user(1)["lang"], "ta"); self.press("n:lang:xx"); self.assertEqual(self.db.user(1)["lang"], "ta")
        n = len(self.tg.log); self.press("n:cmd:stats"); self.press("n:cmd:__import__"); 
        self.assertFalse([1 for n_, a, k in self.tg.log[n:] if n_ in ("send", "rich")])   # not whitelisted -> nothing runs
        self.press("n:cmd:fav"); self.assertTrue([1 for n_, a, k in self.tg.log if n_ == "send"])

    def test_admin_screen_owner_only_and_hint(self):
        self.press("n:admin", uid=1); self.assertFalse(self.tg.calls("edit_rich"))
        self.press("n:admin", uid=999); self.assertIn("Stars received", self.tg.calls("edit_rich")[-1][0][2])
        self.press("n:hint:search"); self.assertIn("Type a song", str(self.tg.texts()))

    def test_commands_installed(self):
        run(commands.install(self.tg)); names = [n for n, a, k in self.tg.log]
        self.assertEqual(names.count("set_commands") + names.count("setMyCommands"), 3)

    def test_prune_results(self):
        self.db.kv_set("res:1:1", {"ids": [], "ts": 1}); self.db.kv_set("res:1:2", {"ids": [], "ts": int(time.time())})
        self.assertEqual(sched.prune_results(self.db), 1); self.assertIsNone(self.db.kv_get("res:1:1")); self.assertIsNotNone(self.db.kv_get("res:1:2"))


class Donations(Base):
    def paid(self, uid, stars, cid, payload=None):
        m = self.msg("", uid=uid, successful_payment={"invoice_payload": payload or f"don:{stars}", "currency": "XTR",
                                                      "total_amount": stars, "telegram_payment_charge_id": cid}); del m["text"]
        run(main.on_message(self.ctx, m))

    def test_preset_and_custom_invoices(self):
        self.press("dn:5")
        (a, k), = self.tg.calls("invoice_stars"); self.assertEqual((a[3], a[4]), ("don:5", 5))
        self.press("dn:custom"); self.assertEqual(self.db.kv_get("flow:1")["k"], "don_amount")
        self.send("37"); self.assertEqual(self.tg.calls("invoice_stars")[-1][0][4], 37)
        self.assertIsNone(self.db.kv_get("flow:1"))

    def test_bad_custom_amounts_never_create_invoices(self):
        for bad in ("abc", "0", "-5", "10001", "1.5"):
            self.press("dn:custom"); self.send(bad)
        self.assertFalse(self.tg.calls("invoice_stars"))
        self.send("/donate 0"); self.send("/donate 99999"); self.assertFalse(self.tg.calls("invoice_stars"))
        self.send("/donate 3"); self.assertEqual(len(self.tg.calls("invoice_stars")), 1)

    def test_invoice_refused_by_telegram_is_reported(self):
        async def boom(*a, **k): raise TgError("sendInvoice", 400, "STARS_AMOUNT_INVALID")
        self.tg.invoice_stars = boom
        self.press("dn:5"); self.assertIn("smaller amount", " ".join(self.tg.texts()))

    def test_pre_checkout_accepts_only_our_invoices(self):
        def ask(payload, total, cur="XTR"):
            self.tg.log.clear()
            run(main.on_update(self.ctx, {"update_id": 1, "pre_checkout_query": {"id": "q", "from": {"id": 1}, "invoice_payload": payload,
                                                                                  "total_amount": total, "currency": cur}}))
            return self.tg.calls("precheckout")[-1][0][1]
        self.assertTrue(ask("don:5", 5)); self.assertTrue(ask("don:10000", 10000)); self.assertTrue(ask("prem30", self.cfg.premium_stars_30d))
        self.assertFalse(ask("don:5", 6)); self.assertFalse(ask("don:5", 5, "USD")); self.assertFalse(ask("prem30", 1))
        self.assertFalse(ask("evil", 5)); self.assertFalse(ask("don:abc", 5)); self.assertFalse(ask("don:0", 0)); self.assertFalse(ask("don:10001", 10001))

    def test_payment_is_idempotent_and_awards_tier_badges(self):
        self.paid(1, 1, "c1"); self.paid(1, 1, "c1")                                 # Telegram redelivery
        self.assertEqual(len(self.db.q("SELECT * FROM payments")), 1); self.assertEqual(donate.total_stars(self.db, 1), 1)
        self.assertEqual({r["badge"] for r in self.db.q("SELECT badge FROM badges")}, {"💖 Supporter"})
        self.paid(1, 60, "c2"); self.assertEqual(donate.total_stars(self.db, 1), 61)
        self.assertEqual({r["badge"] for r in self.db.q("SELECT badge FROM badges")}, {"💖 Supporter", "💎 Patron"})
        self.assertEqual(len([1 for n, a, k in self.tg.log if n == "rich" and "Thank you" in a[1]]), 2)

    def test_forged_or_non_star_payments_ignored(self):
        m = self.msg("", successful_payment={"invoice_payload": "don:5", "currency": "USD", "total_amount": 5, "telegram_payment_charge_id": "x"}); del m["text"]
        run(main.on_message(self.ctx, m)); self.assertFalse(self.db.q("SELECT * FROM payments"))
        m = self.msg("", successful_payment={"invoice_payload": "don:5", "currency": "XTR", "total_amount": 5}); del m["text"]
        run(main.on_message(self.ctx, m)); self.assertFalse(self.db.q("SELECT * FROM payments"))

    def test_premium_purchase_still_works(self):
        self.paid(2, self.cfg.premium_stars_30d, "p1", "prem30"); self.assertTrue(self.db.is_premium(2))
        self.assertEqual(donate.total_stars(self.db, 2), 0)                           # premium is not a donation

    def test_wall_respects_privacy_and_refund_flow(self):
        self.paid(1, 10, "a1"); self.paid(2, 5, "b1"); self.db.x("UPDATE users SET privacy=1 WHERE id=2")
        h = donate.wall(self.ctx)[0]; self.assertIn("U1", h); self.assertNotIn("U2", h); self.assertIn("Anonymous", h)
        self.send("/refund a1", uid=1); self.assertFalse(self.tg.calls("refund_stars"))     # not owner
        self.send("/refund a1", uid=999)
        (a, k), = self.tg.calls("refund_stars"); self.assertEqual(a, (1, "a1"))
        self.assertEqual(donate.total_stars(self.db, 1), 0); self.send("/refund a1", uid=999)
        self.assertEqual(len(self.tg.calls("refund_stars")), 1)                             # already refunded


class TgFallbacks(unittest.TestCase):
    def _tg(self, fail):
        tg, log = Tg("1:T"), []
        async def call(method, **p):
            log.append((method, p))
            if method in fail: raise TgError(method, 400, "bad")
            return {"message_id": 7}
        tg.call = call; tg.try_call = lambda m, **p: _safe(call, m, p)
        return tg, log

    def test_rich_send_falls_back_to_plain(self):
        tg, log = self._tg({"sendRichMessage"})
        r = run(tg.rich(1, R.doc(R.heading("Hi"), R.kv_table([("a", "b")])), [[{"text": "x", "callback_data": "y"}]]))
        self.assertEqual([m for m, p in log], ["sendRichMessage", "sendMessage"]); self.assertIn("a — b", log[1][1]["text"])
        self.assertEqual(log[1][1]["reply_markup"]["inline_keyboard"][0][0]["text"], "x")

    def test_rich_edit_falls_back_to_plain_edit(self):
        tg, log = self._tg({"__none__"})
        async def call(method, **p):
            log.append((method, p))
            if "rich_message" in p: raise TgError(method, 400, "bad")
            return {"ok": 1}
        tg.call = call; tg.try_call = lambda m, **p: _safe(call, m, p)
        run(tg.edit_rich(1, 2, R.doc(R.heading("Hi")))); self.assertEqual(len(log), 2); self.assertIn("text", log[1][1])

    def test_stars_invoice_shape(self):
        tg, log = self._tg(set()); run(tg.invoice_stars(1, "T", "D", "don:5", 5))
        p = log[0][1]; self.assertEqual((p["currency"], p["prices"]), ("XTR", [{"label": "T", "amount": 5}])); self.assertNotIn("provider_token", p)


async def _safe(call, m, p):
    try: return await call(m, **p)
    except TgError: return None


if __name__ == "__main__":
    unittest.main()
