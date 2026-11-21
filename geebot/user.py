"""Private-chat features: search, cards, lyrics, download, playlists, Heardle, dedications, diary, wrapped, rhymes, reels."""
import asyncio
import json
import os
import random
import time

from . import cards, features, games, lrc, media, search, textutil as tu, widgets
from .app import Ctx, arg_text, display_name
from .db import Track
from .tg import btn
from .util import esc, fmt_dur, local_now, today, to_utc_ts


# ---------- helpers ----------------------------------------------------------
async def audio_path(ctx: Ctx, t: Track) -> str | None:
    """Local file for a track: CC URL, or an uploaded Telegram file."""
    try:
        if t.audio_url:
            return await media.fetch(t.audio_url, ctx.cfg.media_dir)
        if t.audio_file_id:
            url = await ctx.tg.file_url(t.audio_file_id)
            return await media.fetch(url, ctx.cfg.media_dir) if url else None
    except Exception:
        return None
    return None


async def show_card(ctx: Ctx, chat_id: int, uid: int, t: Track, in_private: bool = True):
    md, html = cards.card_text(t)
    await ctx.tg.send_rich(chat_id, md, html, cards.card_kb(ctx.cfg, t, ctx.db.is_fav(uid, t.id), in_private))


async def show_results(ctx: Ctx, chat_id: int, uid: int, tracks: list[Track]):
    if not tracks:
        return await ctx.tg.send(chat_id, ctx.tr(uid, "nothing"))
    await ctx.tg.send(chat_id, ctx.tr(uid, "pick"), cards.results_kb(tracks))


# ---------- commands ---------------------------------------------------------
async def cmd_start(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    if args.startswith("t_"):
        t = ctx.db.track(args[2:])
        if t:
            return await show_card(ctx, chat, uid, t)
    if args.startswith("ded_"):
        return await deliver_dedication(ctx, int(args[4:] or 0), uid)
    await ctx.tg.send(chat, ctx.tr(uid, "welcome"))


async def cmd_help(ctx: Ctx, msg: dict, args: str):
    await ctx.tg.send(msg["chat"]["id"], ctx.tr(msg["from"]["id"], "help"))


async def cmd_search(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    q = args or (msg.get("reply_to_message") or {}).get("text", "")
    if not q:
        return await ctx.tg.send(chat, ctx.tr(uid, "pick"))
    res = await search.combined(ctx.db, ctx.jamendo, q)
    if not res:  # not a title: maybe a half-remembered lyric line
        hit = search.lyric_line_search(ctx.db, q)
        res = [t for _, t, _ in hit]
    if not res:
        res = await search.feeling(ctx.db, ctx.jamendo, ctx.llm, q)
    await show_results(ctx, chat, uid, res)


async def cmd_feel(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    res = await search.feeling(ctx.db, ctx.jamendo, ctx.llm, args or "calm")
    await show_results(ctx, chat, uid, res)


async def cmd_lyric(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    hits = search.lyric_line_search(ctx.db, args)
    if not hits:
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    await show_results(ctx, chat, uid, [t for _, t, _ in hits])


async def cmd_fav(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    rows = ctx.db.q("SELECT track_id FROM favs WHERE user_id=? ORDER BY ts DESC LIMIT 30", uid)
    tr = [ctx.db.track(r["track_id"]) for r in rows]
    await show_results(ctx, chat, uid, [t for t in tr if t])


async def cmd_history(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    rows = ctx.db.q("SELECT DISTINCT track_id FROM history WHERE user_id=? ORDER BY ts DESC LIMIT 20", uid)
    await show_results(ctx, chat, uid, [t for t in (ctx.db.track(r["track_id"]) for r in rows) if t])


async def cmd_playlists(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    pls = ctx.db.q("SELECT id,name FROM playlists WHERE user_id=?", uid)
    rows = [[btn(f"📃 {p['name']}", data=f"po:{p['id']}")] for p in pls] + [[btn("➕ New", data="pn:")]]
    await ctx.tg.send(chat, "Playlists", rows)


async def cmd_lang(ctx: Ctx, msg: dict, args: str):
    await ctx.tg.send(msg["chat"]["id"], "Language / භාෂාව",
                      [[btn("සිංහල", data="lg:si"), btn("English", data="lg:en"), btn("தமிழ்", data="lg:ta")]])


async def cmd_rhyme(ctx: Ctx, msg: dict, args: str):
    """Songwriter tool: rhyming words drawn from the lyrics we hold (own vocabulary, not a dictionary)."""
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    vocab = {w for t in ctx.db.tracks("(lrc!='' OR plain!='')", limit=3000) for w in tu.words(t.lrc or t.plain)}
    res = tu.rhymes(args, sorted(vocab), n=2) or tu.rhymes(args, sorted(vocab), n=1)
    await ctx.tg.send(chat, esc(", ".join(res)) if res else ctx.tr(uid, "nothing"))


async def cmd_wrapped(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    yr = int(args) if args.isdigit() else local_now(ctx.cfg.tz_offset_min).year
    w = features.wrapped(ctx.db, uid, yr, ctx.cfg.tz_offset_min)
    if not w:
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    md, html = features.wrapped_text(w, yr, display_name(msg["from"]), ctx.cfg.bot_username)
    await ctx.tg.send_rich(chat, md, html)


async def cmd_match(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    other = None
    if msg.get("reply_to_message", {}).get("from"):
        other = msg["reply_to_message"]["from"]["id"]
    elif args.startswith("@"):
        other = features.recipient_id(ctx.db, args)
    if not other or other == uid:
        return await ctx.tg.send(chat, "Reply to someone (who has started the bot) or use /match @username")
    m = features.taste(ctx.db, uid, other)
    shared = ", ".join(m["artists"][:5]) or "-"
    await ctx.tg.send(chat, f"🎶 Match <b>{m['percent']}%</b>\nShared artists: {esc(shared)}\nShared songs: {len(m['tracks'])}")


async def cmd_beat(ctx: Ctx, msg: dict, args: str):
    if msg["chat"]["type"] != "private":
        return await ctx.tg.send(msg["chat"]["id"], "Beat Tap runs in a private chat with the bot (widgets are private-chat only in production).")
    m = await ctx.tg.call("sendWidget", chat_id=msg["chat"]["id"], html=widgets.BEAT, caption="🥁 Beat Tap", allow_queries=True)
    ctx.db.kv_set(f"wd:{m['chat']['id']}:{m['message_id']}", {"kind": "beat"})


async def cmd_premium(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    await ctx.tg.try_call("sendInvoice", chat_id=chat, title="Premium · 30 days", description="Unlimited downloads, no limits",
                          payload="prem30", currency="XTR", prices=[{"label": "Premium 30d", "amount": ctx.cfg.premium_stars_30d}])


async def cmd_report(ctx: Ctx, msg: dict, args: str):
    uid = msg["from"]["id"]
    tid, _, reason = args.partition(" ")
    ctx.db.x("INSERT INTO reports(track_id,user_id,reason,ts) VALUES(?,?,?,?)", tid, uid, reason[:300], int(time.time()))
    for o in ctx.cfg.owner_ids:
        await ctx.tg.try_call("sendMessage", chat_id=o, text=f"🚩 report {tid}: {reason[:200]}")
    await ctx.tg.send(msg["chat"]["id"], ctx.tr(uid, "done"))


async def cmd_reel(ctx: Ctx, msg: dict, args: str):
    """/reel <track_id> [start_sec] [dur_sec]  - vertical lyric video for Stories/Status (licence-gated)."""
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    p = args.split()
    t = ctx.db.track(p[0]) if p else None
    if not t:
        return await ctx.tg.send(chat, "/reel &lt;track_id&gt; [start] [seconds]")
    if not features.lyric_reel_ok(t.license) or not t.lrc:
        return await ctx.tg.send(chat, "Reels are only made for tracks with a remix-friendly licence and synced lyrics.")
    start = float(p[1]) if len(p) > 1 else 0.0
    dur = min(float(p[2]) if len(p) > 2 else 20.0, 30.0)
    src = await audio_path(ctx, t)
    if not src or not ctx.cfg.font_file:
        return await ctx.tg.send(chat, "Audio or FONT_FILE (a font with Sinhala glyphs) is not available.")
    out = os.path.join(ctx.cfg.media_dir, f"reel_{int(time.time())}.mp4")
    ok = await media.make_reel(src, start, dur, lrc.parse(t.lrc), ctx.cfg.font_file, out)
    if not ok:
        return await ctx.tg.send(chat, "Could not render the reel.")
    with open(out, "rb") as f:
        await ctx.tg.send_video_bytes(chat, f.read(), "reel.mp4", caption=f"@{ctx.cfg.bot_username}")
    os.remove(out)


# ---------- card callbacks ---------------------------------------------------
async def cb_card(ctx: Ctx, cb: dict, tid: str):
    uid, chat = cb["from"]["id"], cb["message"]["chat"]["id"]
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    if t:
        await show_card(ctx, chat, uid, t, cb["message"]["chat"]["type"] == "private")


async def cb_fav(ctx: Ctx, cb: dict, tid: str):
    uid = cb["from"]["id"]
    on = ctx.db.toggle_fav(uid, tid)
    await ctx.tg.answer_cb(cb["id"], ctx.tr(uid, "fav_on" if on else "fav_off"))
    t = ctx.db.track(tid)
    if t:
        m = cb["message"]
        await ctx.tg.edit_kb(m["chat"]["id"], m["message_id"], cards.card_kb(ctx.cfg, t, on, m["chat"]["type"] == "private"))


async def cb_lyrics(ctx: Ctx, cb: dict, tid: str):
    uid, chat = cb["from"]["id"], cb["message"]["chat"]["id"]
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    lines = lrc.plain_lines((t.lrc or t.plain) if t else "")
    if not lines:
        return await ctx.tg.send(chat, ctx.tr(uid, "no_lyrics"))
    ctx.db.log_play(uid, tid)
    shown = lines[:16]  # a preview; the full synced view lives in the Mini App
    more = "\n…" if len(lines) > 16 else ""
    rows = [[btn("Singlish", data=f"ro:{tid}")]]
    if ctx.cfg.webapp_url and cb["message"]["chat"]["type"] == "private":
        rows.append([btn("▶ Player", webapp=f"{ctx.cfg.webapp_url}/app?t={tid}")])
    await ctx.tg.send(chat, esc("\n".join(shown)) + more, rows)


async def cb_roman(ctx: Ctx, cb: dict, tid: str):
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    lines = lrc.plain_lines((t.lrc or t.plain) if t else "")[:16]
    if lines:
        await ctx.tg.send(cb["message"]["chat"]["id"], esc("\n".join(tu.roman(l) for l in lines)))


async def cb_download(ctx: Ctx, cb: dict, tid: str):
    uid, chat = cb["from"]["id"], cb["message"]["chat"]["id"]
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    await send_download(ctx, chat, uid, t)


async def send_download(ctx: Ctx, chat: int, uid: int, t: Track | None):
    if not t or not t.downloadable or not (t.audio_url or t.audio_file_id):
        return await ctx.tg.send(chat, ctx.tr(uid, "dl_off"))
    day = today(ctx.cfg.tz_offset_min)
    used = ctx.db.one("SELECT COUNT(*) n FROM downloads WHERE user_id=? AND day=?", uid, day)["n"]
    if used >= ctx.cfg.free_dl_per_day and not ctx.db.is_premium(uid):
        return await ctx.tg.send(chat, ctx.tr(uid, "dl_limit", n=ctx.cfg.free_dl_per_day))
    src = await audio_path(ctx, t)
    if not src:
        return await ctx.tg.send(chat, ctx.tr(uid, "dl_off"))
    lyrics = t.lrc or t.plain
    out, name = src, f"{t.artist} - {t.title}".replace("/", "_")[:80]
    if lyrics:
        tmp = os.path.join(ctx.cfg.media_dir, f"dl_{uid}_{int(time.time())}.mp3")
        if await media.embed_lyrics(src, tmp, t.title, t.artist, "\n".join(lrc.plain_lines(lyrics))):
            out = tmp
    with open(out, "rb") as f:
        await ctx.tg.send_audio_bytes(chat, f.read(), name + ".mp3", t.title, t.artist, caption=f"CC · {esc(t.license)}" if t.license else None)
    if t.lrc:
        await ctx.tg.send_doc_bytes(chat, t.lrc.encode(), name + ".lrc")
    if out != src:
        os.remove(out)
    ctx.db.x("INSERT INTO downloads VALUES(?,?,?)", uid, day, t.id)
    ctx.db.log_play(uid, t.id)


async def cb_widget(ctx: Ctx, cb: dict, tid: str):
    uid, chat = cb["from"]["id"], cb["message"]["chat"]["id"]
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    if cb["message"]["chat"]["type"] != "private":
        return await ctx.tg.send(chat, "Widgets work in the private chat with the bot (use ▶ Player in groups).")
    if not t or not t.lrc:
        return await ctx.tg.send(chat, ctx.tr(uid, "no_lyrics"))
    lines = lrc.parse(t.lrc)
    js, nxt = lrc.widget_chunk(lines, 0, 1)
    d = json.loads(js)
    if nxt >= len(lines):
        d["e"] = 1
    pub = {"t": t.title[:40], "a": t.artist[:30], "d": t.duration}
    if ctx.cfg.webapp_url:
        pub["u"] = cards.app_link(ctx.cfg, f"t_{t.id}")
    m = await ctx.tg.call("sendWidget", chat_id=chat, html=widgets.KARAOKE, caption=f"🎤 {t.title} — {t.artist}",
                          chat_data=json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                          public_data=json.dumps(pub, ensure_ascii=False, separators=(",", ":")), allow_queries=True)
    ctx.db.kv_set(f"wd:{chat}:{m['message_id']}", {"kind": "karaoke", "tid": t.id, "rev": 1})
    ctx.db.log_play(uid, t.id)


# ---------- playlists --------------------------------------------------------
async def cb_playlist_pick(ctx: Ctx, cb: dict, tid: str):
    uid = cb["from"]["id"]
    await ctx.tg.answer_cb(cb["id"])
    pls = ctx.db.q("SELECT id,name FROM playlists WHERE user_id=?", uid)
    rows = [[btn(p["name"], data=f"pa:{p['id']}:{tid}")] for p in pls] + [[btn("➕ New", data=f"pn:{tid}")]]
    await ctx.tg.send(cb["message"]["chat"]["id"], "Add to…", rows)


async def cb_playlist_add(ctx: Ctx, cb: dict, arg: str):
    uid = cb["from"]["id"]
    pid, _, tid = arg.partition(":")
    pl = ctx.db.one("SELECT 1 x FROM playlists WHERE id=? AND user_id=?", int(pid), uid)
    if pl:
        ctx.db.x("INSERT OR IGNORE INTO pl_items VALUES(?,?,?)", int(pid), tid, int(time.time()))
    await ctx.tg.answer_cb(cb["id"], ctx.tr(uid, "done"))


async def cb_playlist_open(ctx: Ctx, cb: dict, pid: str):
    uid = cb["from"]["id"]
    await ctx.tg.answer_cb(cb["id"])
    rows = ctx.db.q("SELECT i.track_id FROM pl_items i JOIN playlists p ON p.id=i.pl_id WHERE p.id=? AND p.user_id=? ORDER BY i.ts", int(pid), uid)
    await show_results(ctx, cb["message"]["chat"]["id"], uid, [t for t in (ctx.db.track(r["track_id"]) for r in rows) if t])


async def cb_playlist_new(ctx: Ctx, cb: dict, tid: str):
    uid = cb["from"]["id"]
    await ctx.tg.answer_cb(cb["id"])
    ctx.db.kv_set(f"flow:{uid}", {"k": "plname", "tid": tid})
    await ctx.tg.send(cb["message"]["chat"]["id"], "Playlist name?")


async def cb_lang(ctx: Ctx, cb: dict, code: str):
    ctx.db.x("UPDATE users SET lang=? WHERE id=?", code, cb["from"]["id"])
    await ctx.tg.answer_cb(cb["id"], "✅")


# ---------- Heardle ----------------------------------------------------------
async def cmd_heardle(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    day = today(ctx.cfg.tz_offset_min)
    row = ctx.db.one("SELECT * FROM heardle WHERE user_id=? AND day=?", uid, day)
    if row and row["done"]:
        return await ctx.tg.send(chat, ctx.tr(uid, "heardle_done") + "\n\n" +
                                 games.share_row(day, json.loads(row["attempts"]), bool(row["won"])))
    t = games.daily_track(day, ctx.db.tracks(limit=3000))
    if not t:
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    if not row:
        ctx.db.x("INSERT INTO heardle(user_id,day,attempts) VALUES(?,?,?)", uid, day, "[]")
    ctx.db.kv_set(f"flow:{uid}", {"k": "heardle", "day": day})
    await send_heardle_clip(ctx, chat, uid, t, len(json.loads(row["attempts"])) if row else 0)


async def send_heardle_clip(ctx: Ctx, chat: int, uid: int, t: Track, n: int):
    src = await audio_path(ctx, t)
    if not src:
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    out = os.path.join(ctx.cfg.media_dir, f"hd_{uid}_{n}.mp3")
    if not await media.cut_clip(src, games.clip_seconds(n), out):
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    with open(out, "rb") as f:
        await ctx.tg.send_audio_bytes(chat, f.read(), "heardle.mp3", title=f"Heardle {n + 1}/{len(games.CLIP_STEPS)}", performer="?")
    os.remove(out)
    await ctx.tg.send(chat, ctx.tr(uid, "heardle_intro", n=n + 1, m=len(games.CLIP_STEPS)), [[btn("⏭ Skip", data="hs:"), btn("🏳 Give up", data="hu:")]])


async def heardle_guess(ctx: Ctx, msg: dict, text: str | None, skip: bool = False, giveup: bool = False):
    uid, chat = (msg.get("from") or {}).get("id"), msg["chat"]["id"]
    day = today(ctx.cfg.tz_offset_min)
    row = ctx.db.one("SELECT * FROM heardle WHERE user_id=? AND day=? AND done=0", uid, day)
    t = games.daily_track(day, ctx.db.tracks(limit=3000))
    if not row or not t:
        return False
    att = json.loads(row["attempts"])
    won = bool(text) and games.guess_ok(text, t)
    att.append("w" if won else ("s" if skip else "x"))
    over = won or giveup or len(att) >= len(games.CLIP_STEPS)
    ctx.db.x("UPDATE heardle SET attempts=?, done=?, won=? WHERE user_id=? AND day=?", json.dumps(att), int(over), int(won), uid, day)
    if not over:
        await send_heardle_clip(ctx, chat, uid, t, len(att))
        return True
    ctx.db.kv_del(f"flow:{uid}")
    u = ctx.db.user(uid)
    yday = today(ctx.cfg.tz_offset_min - 1440)
    if won:
        s = games.next_streak(u["last_heardle_day"], day, u["streak"], yday)
        ctx.db.x("UPDATE users SET streak=?, best_streak=MAX(best_streak,?), last_heardle_day=? WHERE id=?", s, s, day, uid)
        ctx.db.add_score(0, uid, display_name(msg["from"]), "heardle", 7 - len(att))
        txt = ctx.tr(uid, "heardle_win", t=esc(t.title), s=s)
    else:
        ctx.db.x("UPDATE users SET streak=0 WHERE id=?", uid)
        txt = ctx.tr(uid, "heardle_lose", t=esc(t.title))
    await ctx.tg.send(chat, txt + "\n\n" + games.share_row(day, att, won) + f"\n@{ctx.cfg.bot_username}")
    await show_card(ctx, chat, uid, t)
    return True


async def cb_heardle(ctx: Ctx, cb: dict, kind: str):
    await ctx.tg.answer_cb(cb["id"])
    m = {"from": cb["from"], "chat": cb["message"]["chat"]}
    await heardle_guess(ctx, m, None, skip=(kind == "hs"), giveup=(kind == "hu"))


# ---------- dedications / diary ----------------------------------------------
async def cmd_dedicate(ctx: Ctx, msg: dict, args: str):
    uid = msg["from"]["id"]
    ctx.db.kv_set(f"flow:{uid}", {"k": "ded_track"})
    await ctx.tg.send(msg["chat"]["id"], "Song name?")


async def cb_dedicate(ctx: Ctx, cb: dict, tid: str):
    uid = cb["from"]["id"]
    await ctx.tg.answer_cb(cb["id"])
    ctx.db.kv_set(f"flow:{uid}", {"k": "ded_who", "tid": tid})
    await ctx.tg.send(cb["message"]["chat"]["id"], ctx.tr(uid, "dedicate_ask"))


async def cb_dedicate_when(ctx: Ctx, cb: dict, when: str):
    """when: n=now, t=tonight 20:00, m=tomorrow 08:00"""
    uid = cb["from"]["id"]
    fl = ctx.db.kv_get(f"flow:{uid}")
    await ctx.tg.answer_cb(cb["id"])
    if not fl or fl.get("k") != "ded_when":
        return
    at, label = dedication_time(when, ctx.cfg.tz_offset_min)
    await finish_dedication(ctx, cb["message"]["chat"]["id"], uid, fl, at, label)


def dedication_time(when: str, tz_min: int) -> tuple[int, str]:
    """n = now, t = next 20:00 local, m = tomorrow 08:00 local."""
    from datetime import timedelta
    now = local_now(tz_min)
    if when == "n":
        return int(time.time()), "→ now"
    if when == "t":
        d = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if d <= now:
            d += timedelta(days=1)
        return int(time.time() + (d - now).total_seconds()), "→ 20:00"
    d = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return int(time.time() + (d - now).total_seconds()), "→ tomorrow 08:00"


async def finish_dedication(ctx: Ctx, chat: int, uid: int, fl: dict, at: int, label: str):
    features.add_dedication(ctx.db, uid, fl["who"], fl["tid"], fl["note"], at)
    ctx.db.kv_del(f"flow:{uid}")
    await ctx.tg.send(chat, ctx.tr(uid, "dedicate_saved", w=label))


async def deliver_dedication(ctx: Ctx, did: int, uid: int):
    d = ctx.db.one("SELECT * FROM dedications WHERE id=? AND sent=2", did)
    u = ctx.db.user(uid)
    if d and u and u["username"] == d["to_username"]:
        await send_dedication(ctx, d, uid)


async def send_dedication(ctx: Ctx, d: dict, to_id: int):
    t = ctx.db.track(d["track_id"])
    frm = ctx.db.user(d["from_id"]) or {}
    who = "" if d["anonymous"] else f"\n— {esc(frm.get('first_name', ''))}"
    if t:
        md, html = cards.card_text(t)
        await ctx.tg.send(to_id, f"{ctx.tr(to_id, 'ded_head')}\n\n{esc(d['note'])}{who}")
        await ctx.tg.send_rich(to_id, md, html, cards.card_kb(ctx.cfg, t, ctx.db.is_fav(to_id, t.id)))
    ctx.db.x("UPDATE dedications SET sent=1 WHERE id=?", d["id"])


async def cb_diary(ctx: Ctx, cb: dict, tid: str):
    uid = cb["from"]["id"]
    await ctx.tg.answer_cb(cb["id"])
    ctx.db.kv_set(f"flow:{uid}", {"k": "diary", "tid": tid})
    await ctx.tg.send(cb["message"]["chat"]["id"], ctx.tr(uid, "diary_ask"))


async def cmd_diary(ctx: Ctx, msg: dict, args: str):
    uid = msg["from"]["id"]
    rows = ctx.db.q("SELECT d.note, d.ts, t.title FROM diary d LEFT JOIN tracks t ON t.id=d.track_id WHERE d.user_id=? ORDER BY d.ts DESC LIMIT 10", uid)
    txt = "\n\n".join(f"📔 <b>{esc(r['title'] or '')}</b>\n{esc(r['note'])}" for r in rows) or ctx.tr(uid, "nothing")
    await ctx.tg.send(msg["chat"]["id"], txt)


# ---------- plain-text flows ---------------------------------------------------
async def handle_flow(ctx: Ctx, msg: dict) -> bool:
    uid, chat, text = msg["from"]["id"], msg["chat"]["id"], msg.get("text", "")
    fl = ctx.db.kv_get(f"flow:{uid}")
    if not fl or not text:
        return False
    k = fl["k"]
    if k == "heardle":
        return await heardle_guess(ctx, msg, text)
    if k == "plname":
        pid = ctx.db.x("INSERT INTO playlists(user_id,name) VALUES(?,?)", uid, text[:40])
        if fl.get("tid"):
            ctx.db.x("INSERT OR IGNORE INTO pl_items VALUES(?,?,?)", pid, fl["tid"], int(time.time()))
        ctx.db.kv_del(f"flow:{uid}")
        await ctx.tg.send(chat, ctx.tr(uid, "done"))
        return True
    if k == "diary":
        features.add_diary(ctx.db, uid, fl["tid"], text)
        ctx.db.kv_del(f"flow:{uid}")
        await ctx.tg.send(chat, ctx.tr(uid, "diary_saved"))
        return True
    if k == "ded_track":
        res = await search.combined(ctx.db, ctx.jamendo, text, 5)
        ctx.db.kv_del(f"flow:{uid}")
        await show_results_dd(ctx, chat, uid, res)
        return True
    if k == "ded_who":
        who, _, note = text.partition(" ")
        if not who.startswith("@"):
            await ctx.tg.send(chat, ctx.tr(uid, "dedicate_ask"))
            return True
        ctx.db.kv_set(f"flow:{uid}", {"k": "ded_when", "tid": fl["tid"], "who": who, "note": note})
        await ctx.tg.send(chat, ctx.tr(uid, "dedicate_when") + "\n(YYYY-MM-DD HH:MM)",
                          [[btn("Now", data="dw:n"), btn("20:00", data="dw:t"), btn("Tomorrow 08:00", data="dw:m")]])
        return True
    if k == "ded_when":
        ts = to_utc_ts(text, ctx.cfg.tz_offset_min)
        if not ts or ts < time.time() - 60:
            await ctx.tg.send(chat, "YYYY-MM-DD HH:MM")
            return True
        await finish_dedication(ctx, chat, uid, fl, ts, text)
        return True
    return False


async def show_results_dd(ctx: Ctx, chat: int, uid: int, tracks: list[Track]):
    if not tracks:
        return await ctx.tg.send(chat, ctx.tr(uid, "nothing"))
    await ctx.tg.send(chat, ctx.tr(uid, "pick"), [[btn(f"{t.title} — {t.artist}"[:60], data=f"dd:{t.id}")] for t in tracks])


async def plain_text_search(ctx: Ctx, msg: dict):
    await cmd_search(ctx, msg, msg.get("text", ""))
