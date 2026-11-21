"""Group features: listening party, queue, games, voice contests, leaderboard, tournaments, settings."""
import asyncio
import json
import os
import random
import time

from . import cards, games, lrc, media, search, textutil as tu
from .app import Ctx, arg_text, display_name, pick_audio_track
from .db import Track
from .tg import btn
from .user import audio_path
from .util import esc

rng = random.Random()
WEEK = 7 * 86400


def _chat(msg): return msg["chat"]["id"]
def _uid(msg): return msg["from"]["id"]


async def award(ctx: Ctx, chat: int, user: dict, game: str, pts: int):
    ctx.db.add_score(chat, user["id"], display_name(user), game, pts)


# ---------- party / queue ------------------------------------------------------
async def cmd_party(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    t = None
    if args:
        res = await search.combined(ctx.db, ctx.jamendo, args, 1)
        t = res[0] if res else None
    t = t or pick_audio_track(ctx.db, rng)
    if not t:
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "nothing"))
    await ctx.tg.send(chat, f"🎉 <b>Listening party</b>\n{esc(t.title)} — {esc(t.artist)}",
                      [[btn("▶ Start", data=f"pt:{t.id}")]])


async def cb_party_start(ctx: Ctx, cb: dict, tid: str):
    """The callback carries chat_instance - the key a Mini App sees in initData, so everyone syncs on it."""
    ci = cb.get("chat_instance")
    t = ctx.db.track(tid)
    await ctx.tg.answer_cb(cb["id"])
    if not ci or not t:
        return
    ctx.db.x("INSERT INTO party VALUES(?,?,?,?,?) ON CONFLICT(chat_instance) DO UPDATE SET track_id=excluded.track_id, "
             "started_at=excluded.started_at, paused_at=NULL, updated=excluded.updated", ci, tid, time.time(), None, int(time.time()))
    m = cb["message"]
    await ctx.tg.edit(m["chat"]["id"], m["message_id"], f"🎉 <b>Party</b>: {esc(t.title)} — {esc(t.artist)}",
                      [[btn("🎧 Join", url=cards.app_link(ctx.cfg, f"p_{tid}"))]])
    await bingo_tick(ctx, m["chat"]["id"], t)


async def cmd_request(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    res = await search.combined(ctx.db, ctx.jamendo, args, 1) if args else []
    if not res:
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "nothing"))
    q = ctx.db.kv_get(f"queue:{chat}", [])
    q.append(res[0].id)
    ctx.db.kv_set(f"queue:{chat}", q[-20:])
    await ctx.tg.send(chat, f"➕ {esc(res[0].title)} ({len(q)})")


async def cmd_queue(ctx: Ctx, msg: dict, args: str):
    q = ctx.db.kv_get(f"queue:{_chat(msg)}", [])
    ts = [t for t in (ctx.db.track(i) for i in q) if t]
    await ctx.tg.send(_chat(msg), "\n".join(f"{i}. {esc(t.title)}" for i, t in enumerate(ts, 1)) or "—")


async def cmd_skip(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    if not await ctx.is_chat_admin(chat, _uid(msg)):
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "admins_only"))
    q = ctx.db.kv_get(f"queue:{chat}", [])
    if not q:
        return await ctx.tg.send(chat, "—")
    t = ctx.db.track(q.pop(0))
    ctx.db.kv_set(f"queue:{chat}", q)
    if t:
        await ctx.tg.send(chat, f"▶ {esc(t.title)} — {esc(t.artist)}", [[btn("🎧 Open", url=cards.app_link(ctx.cfg, f"t_{t.id}"))]])
        await bingo_tick(ctx, chat, t)


# ---------- generic helpers ------------------------------------------------------
async def _clip_to_chat(ctx: Ctx, chat: int, t: Track, secs: int) -> bool:
    src = await audio_path(ctx, t)
    if not src:
        return False
    out = os.path.join(ctx.cfg.media_dir, f"g_{chat}_{int(time.time())}.mp3")
    if not await media.cut_clip(src, secs, out, start=min(20, max(0, t.duration // 4))):
        return False
    with open(out, "rb") as f:
        await ctx.tg.send_audio_bytes(chat, f.read(), "clip.mp3", title="🎧 ?", performer="?")
    os.remove(out)
    return True


def _lyric_tracks(ctx: Ctx) -> list[Track]:
    return ctx.db.tracks("(lrc!='' OR plain!='')", limit=2000)


# ---------- duel (blind test, first correct answer wins) --------------------------
async def cmd_duel(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    st = {"left": 5, "scores": {}}
    ctx.db.game_set(chat, "duel", st)
    await duel_round(ctx, chat)


async def duel_round(ctx: Ctx, chat: int):
    st = ctx.db.game_get(chat, "duel")
    t = pick_audio_track(ctx.db, rng)
    if not st or not t:
        ctx.db.game_end(chat, "duel")
        return await ctx.tg.send(chat, "—")
    st.update(track=t.id, started=time.time())
    ctx.db.game_set(chat, "duel", st)
    if not await _clip_to_chat(ctx, chat, t, 8):
        ctx.db.game_end(chat, "duel")
        return await ctx.tg.send(chat, "—")
    await ctx.tg.send(chat, f"🎧 Round {6 - st['left']}/5 — type the title (or /g title)")


async def duel_guess(ctx: Ctx, msg: dict, text: str) -> bool:
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "duel")
    if not st:
        return False
    t = ctx.db.track(st["track"])
    if not t or not games.guess_ok(text, t):
        return False
    pts = games.speed_points(time.time() - st["started"])
    await award(ctx, chat, msg["from"], "duel", pts)
    st["scores"][str(_uid(msg))] = st["scores"].get(str(_uid(msg)), 0) + pts
    st["left"] -= 1
    await ctx.tg.send(chat, f"✅ {esc(display_name(msg['from']))} +{pts} — <b>{esc(t.title)}</b>")
    if st["left"] <= 0:
        ctx.db.game_end(chat, "duel")
        return await ctx.tg.send(chat, "🏁 Duel finished — /top") or True
    ctx.db.game_set(chat, "duel", st)
    await asyncio.sleep(2)
    await duel_round(ctx, chat)
    return True


# ---------- lyrics chain ---------------------------------------------------------
async def cmd_chain(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    pool = _lyric_tracks(ctx)
    t = rng.choice(pool) if pool else None
    st = games.chain_start(t, rng) if t else None
    if not st:
        return await ctx.tg.send(chat, "Needs a track with lyrics in the catalogue.")
    ctx.db.game_set(chat, "chain", st)
    lines = lrc.plain_lines(t.lrc or t.plain)
    await ctx.tg.send(chat, f"🔗 Lyrics chain — send the NEXT line (round 1/{st['max']}):\n\n<i>{esc(lines[st['i']])}</i>")


async def chain_guess(ctx: Ctx, msg: dict, text: str) -> bool:
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "chain")
    if not st:
        return False
    t = ctx.db.track(st["track"])
    lines = lrc.plain_lines((t.lrc or t.plain) if t else "")
    nxt = st["i"] + 1
    if nxt >= len(lines) or not games.chain_check(text, lines[nxt]):
        return False
    await award(ctx, chat, msg["from"], "chain", 3)
    st["i"], st["round"] = nxt, st["round"] + 1
    if st["round"] > st["max"] or st["i"] + 1 >= len(lines):
        ctx.db.game_end(chat, "chain")
        await ctx.tg.send(chat, f"✅ {esc(display_name(msg['from']))} +3\n🏁 Chain finished — <b>{esc(t.title)}</b> /top")
        return True
    ctx.db.game_set(chat, "chain", st)
    await ctx.tg.send(chat, f"✅ {esc(display_name(msg['from']))} +3\nNext (round {st['round']}/{st['max']}):\n<i>{esc(lines[st['i']])}</i>")
    return True


# ---------- quizzes (polls) -------------------------------------------------------
async def cmd_missing(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    pool = _lyric_tracks(ctx)
    words = [w for t in pool for w in (t.lrc or t.plain).split() if "[" not in w]
    q = next((x for x in (games.missing_word(t, rng, words) for t in rng.sample(pool, min(8, len(pool)))) if x), None) if pool else None
    if not q:
        return await ctx.tg.send(chat, "Needs tracks with lyrics.")
    await quiz(ctx, chat, "🧩 " + q["question"], q["options"], q["correct"])


async def cmd_odd(ctx: Ctx, msg: dict, args: str):
    q = games.odd_one_out(ctx.db.tracks(limit=2000), rng)
    if not q:
        return await ctx.tg.send(_chat(msg), "Needs 3+ tracks by one artist.")
    await quiz(ctx, _chat(msg), "🕵 " + q["question"], q["options"], q["correct"])


async def cmd_order(ctx: Ctx, msg: dict, args: str):
    q = games.before_after(ctx.db.tracks(limit=2000), rng)
    if not q:
        return await ctx.tg.send(_chat(msg), "Needs tracks with release years.")
    await quiz(ctx, _chat(msg), "📅 " + q["question"], q["options"], q["correct"])


async def cmd_scramble(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    pool = _lyric_tracks(ctx)
    s = next((x for x in (games.scramble(t, rng) for t in rng.sample(pool, min(8, len(pool)))) if x), None) if pool else None
    if not s:
        return await ctx.tg.send(chat, "Needs tracks with lyrics.")
    ctx.db.game_set(chat, "scramble", s)
    await ctx.tg.send(chat, "🔀 Put in order — reply like <code>2 4 1 3</code>:\n\n" +
                      "\n".join(f"{i}. {esc(l)}" for i, l in enumerate(s["shown"], 1)))


async def scramble_guess(ctx: Ctx, msg: dict, text: str) -> bool:
    chat = _chat(msg)
    s = ctx.db.game_get(chat, "scramble")
    if not s or not games.check_scramble(text, s["answer"]):
        return False
    ctx.db.game_end(chat, "scramble")
    await award(ctx, chat, msg["from"], "scramble", 4)
    await ctx.tg.send(chat, f"✅ {esc(display_name(msg['from']))} +4")
    return True


async def quiz(ctx: Ctx, chat: int, question: str, options: list[str], correct: int):
    m = await ctx.tg.poll_quiz(chat, question, options, correct)
    ctx.db.kv_set(f"poll:{m['poll']['id']}", {"chat": chat, "correct": correct})


async def poll_answer(ctx: Ctx, pa: dict):
    """Quiz poll answers are non-anonymous, so right answers earn points in that chat."""
    info = ctx.db.kv_get(f"poll:{pa['poll_id']}")
    if info and pa.get("option_ids") == [info["correct"]]:
        u = pa.get("user") or {}
        if u.get("id"):
            ctx.db.add_score(info["chat"], u["id"], display_name(u), "quiz", 2)


# ---------- word hunt -------------------------------------------------------------
async def cmd_wordhunt(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    if not args:
        return await ctx.tg.send(chat, "/wordhunt &lt;word&gt;")
    ctx.db.game_set(chat, "wordhunt", {"word": args.split()[0], "found": [], "scores": {}})
    ctx.db.add_job(time.time() + 60, "wordhunt_end", {"chat": chat})
    await ctx.tg.send(chat, f"🔎 60 s! Send song titles that contain <b>{esc(args.split()[0])}</b> (in the title or lyrics).")


async def wordhunt_guess(ctx: Ctx, msg: dict, text: str) -> bool:
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "wordhunt")
    if not st:
        return False
    t = games.wordhunt_valid(st["word"], text, ctx.db.tracks(limit=3000))
    if not t or t.id in st["found"]:
        return False
    st["found"].append(t.id)
    st["scores"][str(_uid(msg))] = st["scores"].get(str(_uid(msg)), 0) + 1
    st.setdefault("names", {})[str(_uid(msg))] = display_name(msg["from"])
    ctx.db.game_set(chat, "wordhunt", st)
    await ctx.tg.send(chat, f"✅ {esc(t.title)} (+1 {esc(display_name(msg['from']))})")
    return True


async def wordhunt_end(ctx: Ctx, chat: int):
    st = ctx.db.game_get(chat, "wordhunt")
    ctx.db.game_end(chat, "wordhunt")
    if not st:
        return
    board = sorted(st["scores"].items(), key=lambda x: -x[1])
    for uid, n in board:
        ctx.db.add_score(chat, int(uid), st.get("names", {}).get(uid, uid), "wordhunt", n)
    await ctx.tg.send(chat, "🏁 " + (", ".join(f"{esc(st.get('names', {}).get(u, u))}: {n}" for u, n in board) or "no answers"))


# ---------- bingo -----------------------------------------------------------------
async def cmd_bingo(ctx: Ctx, msg: dict, args: str):
    chat, uid = _chat(msg), _uid(msg)
    st = ctx.db.game_get(chat, "bingo")
    if args.strip() == "stop":
        ctx.db.game_end(chat, "bingo")
        return await ctx.tg.send(chat, "—")
    if not st:
        pool = sorted({x.strip() for t in ctx.db.tracks(limit=3000) for x in [t.artist] + t.tags.split(",") if x.strip()})
        if len(pool) < 9:
            return await ctx.tg.send(chat, "Needs more tracks (9+ distinct artists/tags).")
        st = {"pool": pool, "players": {}}
    p = st["players"].setdefault(str(uid), {"seed": uid ^ int(time.time()) % 100000, "marks": [], "name": display_name(msg["from"])})
    ctx.db.game_set(chat, "bingo", st)
    card = games.bingo_card(p["seed"], st["pool"])
    await ctx.tg.send(chat, "🎯 <b>Music bingo</b> — marks fill in as songs are played (/party, /skip)\n\n" +
                      esc(games.render_bingo(card, {tuple(m) for m in p["marks"]})))


async def bingo_tick(ctx: Ctx, chat: int, t: Track):
    st = ctx.db.game_get(chat, "bingo")
    if not st:
        return
    for uid, p in st["players"].items():
        card = games.bingo_card(p["seed"], st["pool"])
        marks = {tuple(m) for m in p["marks"]} | games.bingo_marks(card, t)
        p["marks"] = sorted(marks)
        if games.bingo_win(marks):
            ctx.db.add_score(chat, int(uid), p["name"], "bingo", 10)
            ctx.db.game_end(chat, "bingo")
            return await ctx.tg.send(chat, f"🎉 BINGO! {esc(p['name'])} +10")
    ctx.db.game_set(chat, "bingo", st)


# ---------- voice contests: karaoke roulette & sing-off ----------------------------
async def cmd_roulette(ctx: Ctx, msg: dict, args: str, kind: str = "roulette"):
    chat = _chat(msg)
    pool = _lyric_tracks(ctx)
    prompt = args
    if kind == "roulette":
        t = rng.choice(pool) if pool else None
        lines = lrc.plain_lines(t.lrc or t.plain) if t else []
        if not lines:
            return await ctx.tg.send(chat, "Needs a track with lyrics (or use /singoff theme).")
        prompt = rng.choice(lines)
    if not prompt:
        return await ctx.tg.send(chat, "/singoff &lt;theme&gt;")
    m = await ctx.tg.send(chat, f"🎤 <b>{'Karaoke roulette' if kind == 'roulette' else 'Sing-off'}</b> (2 min)\n\n<i>{esc(prompt)}</i>\n\n"
                                "Reply to THIS message with a voice note of YOUR OWN voice. Then everyone votes ❤.")
    ctx.db.game_set(chat, "contest", {"prompt_msg": m["message_id"], "entries": {}, "kind": kind})
    ctx.db.add_job(time.time() + 120, "contest_end", {"chat": chat})


async def cmd_singoff(ctx: Ctx, msg: dict, args: str):
    await cmd_roulette(ctx, msg, args, kind="singoff")


async def contest_entry(ctx: Ctx, msg: dict) -> bool:
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "contest")
    rt = msg.get("reply_to_message") or {}
    if not st or rt.get("message_id") != st["prompt_msg"] or not (msg.get("voice") or msg.get("video_note")):
        return False
    uid = str(_uid(msg))
    if any(e["uid"] == uid for e in st["entries"].values()):
        return True
    eid = str(len(st["entries"]) + 1)
    st["entries"][eid] = {"uid": uid, "name": display_name(msg["from"]), "votes": []}
    ctx.db.game_set(chat, "contest", st)
    await ctx.tg.send(chat, f"🎤 #{eid} {esc(display_name(msg['from']))}", [[btn("❤ 0", data=f"cv:{eid}")]], reply_parameters={"message_id": msg["message_id"]})
    return True


async def cb_contest_vote(ctx: Ctx, cb: dict, eid: str):
    chat, uid = cb["message"]["chat"]["id"], str(cb["from"]["id"])
    st = ctx.db.game_get(chat, "contest")
    e = st["entries"].get(eid) if st else None
    if not e:
        return await ctx.tg.answer_cb(cb["id"], "—")
    if e["uid"] == uid:
        return await ctx.tg.answer_cb(cb["id"], "You can't vote for yourself")
    if uid in e["votes"]:
        e["votes"].remove(uid)
    else:
        e["votes"].append(uid)
    ctx.db.game_set(chat, "contest", st)
    await ctx.tg.answer_cb(cb["id"])
    await ctx.tg.edit_kb(chat, cb["message"]["message_id"], [[btn(f"❤ {len(e['votes'])}", data=f"cv:{eid}")]])


async def contest_end(ctx: Ctx, chat: int):
    st = ctx.db.game_get(chat, "contest")
    ctx.db.game_end(chat, "contest")
    if not st or not st["entries"]:
        return await ctx.tg.send(chat, "🎤 No entries.")
    win = max(st["entries"].values(), key=lambda e: len(e["votes"]))
    ctx.db.add_score(chat, int(win["uid"]), win["name"], "contest", 5 + len(win["votes"]))
    await ctx.tg.send(chat, f"🏆 {esc(win['name'])} — {len(win['votes'])} ❤  (+{5 + len(win['votes'])})")


# ---------- hum it ------------------------------------------------------------------
async def cmd_hum(ctx: Ctx, msg: dict, args: str):
    """Private: /hum <title>  stores the secret answer.  Group: /hum  starts the round for the stored answer."""
    chat, uid = _chat(msg), _uid(msg)
    if msg["chat"]["type"] == "private":
        res = await search.combined(ctx.db, ctx.jamendo, args, 1) if args else []
        if not res:
            return await ctx.tg.send(chat, "/hum &lt;song title&gt; — then run /hum in the group")
        ctx.db.kv_set(f"hum:{uid}", {"tid": res[0].id})
        return await ctx.tg.send(chat, f"🤫 Secret set: {esc(res[0].title)}. Now go to the group and send /hum, then hum it as a voice note.")
    secret = ctx.db.kv_get(f"hum:{uid}")
    if not secret:
        return await ctx.tg.send(chat, f"First DM me: /hum &lt;title&gt; → t.me/{ctx.cfg.bot_username}")
    ctx.db.game_set(chat, "hum", {"hummer": uid, "tid": secret["tid"], "name": display_name(msg["from"])})
    ctx.db.kv_del(f"hum:{uid}")
    await ctx.tg.send(chat, f"🎶 {esc(display_name(msg['from']))} will hum a song — send the voice note now, others guess with /g title")


async def hum_guess(ctx: Ctx, msg: dict, text: str) -> bool:
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "hum")
    t = ctx.db.track(st["tid"]) if st else None
    if not st or not t or _uid(msg) == st["hummer"] or not games.guess_ok(text, t):
        return False
    ctx.db.game_end(chat, "hum")
    await award(ctx, chat, msg["from"], "hum", 4)
    ctx.db.add_score(chat, st["hummer"], st["name"], "hum", 2)
    await ctx.tg.send(chat, f"✅ {esc(display_name(msg['from']))} +4, {esc(st['name'])} +2 — <b>{esc(t.title)}</b>")
    return True


# ---------- team battle ---------------------------------------------------------------
async def cmd_team(ctx: Ctx, msg: dict, args: str):
    """/team  -> join buttons; /team theme <text> -> round: each captain /pick, then vote poll."""
    chat = _chat(msg)
    st = ctx.db.game_get(chat, "team") or {"A": [], "B": [], "picks": {}, "theme": ""}
    sub, _, rest = args.partition(" ")
    if sub == "theme":
        st["theme"], st["picks"] = rest, {}
        ctx.db.game_set(chat, "team", st)
        return await ctx.tg.send(chat, f"🎵 Theme: <b>{esc(rest)}</b>\nCaptains (first in each team): /pick &lt;song&gt;")
    ctx.db.game_set(chat, "team", st)
    await ctx.tg.send(chat, "⚔ Team battle — pick a side", [[btn("Team A", data="tj:A"), btn("Team B", data="tj:B")]])


async def cb_team_join(ctx: Ctx, cb: dict, side: str):
    chat, u = cb["message"]["chat"]["id"], cb["from"]
    st = ctx.db.game_get(chat, "team")
    if not st:
        return await ctx.tg.answer_cb(cb["id"])
    for s in ("A", "B"):
        st[s] = [x for x in st[s] if x[0] != u["id"]]
    st[side].append([u["id"], display_name(u)])
    ctx.db.game_set(chat, "team", st)
    await ctx.tg.answer_cb(cb["id"], f"Team {side}")


async def cmd_pick(ctx: Ctx, msg: dict, args: str):
    chat, uid = _chat(msg), _uid(msg)
    st = ctx.db.game_get(chat, "team")
    if not st:
        return
    side = next((s for s in ("A", "B") if st[s] and st[s][0][0] == uid), None)
    res = await search.combined(ctx.db, ctx.jamendo, args, 1) if args else []
    if not side or not res:
        return await ctx.tg.send(chat, "Only a team captain can /pick (and the song must exist).")
    st["picks"][side] = res[0].title
    ctx.db.game_set(chat, "team", st)
    if len(st["picks"]) == 2:
        p = await ctx.tg.call("sendPoll", chat_id=chat, question=f"🎵 {st['theme']}: which pick is better?",
                              options=[{"text": f"A: {st['picks']['A']}"[:100]}, {"text": f"B: {st['picks']['B']}"[:100]}], is_anonymous=False)
        ctx.db.add_job(time.time() + 90, "team_end", {"chat": chat, "poll": p["message_id"]})
    else:
        await ctx.tg.send(chat, f"✅ Team {side} locked in.")


async def team_end(ctx: Ctx, chat: int, poll_msg: int):
    r = await ctx.tg.try_call("stopPoll", chat_id=chat, message_id=poll_msg)
    st = ctx.db.game_get(chat, "team")
    if not r or not st:
        return
    va, vb = (o["voter_count"] for o in r["options"])
    win = "A" if va > vb else "B" if vb > va else None
    if win:
        for uid, name in st[win]:
            ctx.db.add_score(chat, uid, name, "team", 5)
    await ctx.tg.send(chat, f"🏆 Team {win or 'tie'} ({va}–{vb})")


# ---------- guesses (plain text or /g) -------------------------------------------------
async def cmd_g(ctx: Ctx, msg: dict, args: str):
    await group_text(ctx, msg, args)


async def group_text(ctx: Ctx, msg: dict, text: str | None = None) -> bool:
    text = text if text is not None else msg.get("text", "")
    if not text:
        return False
    for fn in (duel_guess, chain_guess, scramble_guess, wordhunt_guess, hum_guess):
        if await fn(ctx, msg, text):
            return True
    return False


# ---------- leaderboard / tournament / settings -------------------------------------------
async def cmd_top(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    since = ctx.db.kv_get(f"tour:{chat}") if args.strip() != "week" else None
    since = since or int(time.time()) - WEEK
    rows = ctx.db.leaderboard(None if msg["chat"]["type"] == "private" else chat, since)
    title = "🏆 Tournament" if ctx.db.kv_get(f"tour:{chat}") and args.strip() != "week" else "🏆 This week"
    await ctx.tg.send(chat, title + "\n" + ("\n".join(f"{i}. {esc(r['name'])} — {r['p']}" for i, r in enumerate(rows, 1)) or "—"))


async def cmd_tournament(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    if not await ctx.is_chat_admin(chat, _uid(msg)):
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "admins_only"))
    if args.strip() == "end":
        since = ctx.db.kv_get(f"tour:{chat}") or 0
        rows = ctx.db.leaderboard(chat, since, 3)
        ctx.db.kv_del(f"tour:{chat}")
        return await ctx.tg.send(chat, "🏁 Tournament over\n" + "\n".join(f"{'🥇🥈🥉'[i]} {esc(r['name'])} — {r['p']}" for i, r in enumerate(rows)))
    ctx.db.kv_set(f"tour:{chat}", int(time.time()))
    await ctx.tg.send(chat, "🏆 Tournament started! Scores from now on count. /top to follow, /tournament end to finish.")


def settings_kb(gs: dict) -> list:
    return [[btn(f"Who: {gs['who']}", data="gs:who")],
            [btn(f"Cooldown: {gs['cooldown']}s", data="gs:cd")],
            [btn(f"Downloads: {'on' if gs['download'] else 'off'}", data="gs:dl")],
            [btn(f"Explicit filter: {'on' if gs['explicit'] else 'off'}", data="gs:ex")]]


async def cmd_settings(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    if not await ctx.is_chat_admin(chat, _uid(msg)):
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "admins_only"))
    await ctx.tg.send(chat, "⚙ Group settings", settings_kb(ctx.db.gs(chat)))


async def cb_settings(ctx: Ctx, cb: dict, key: str):
    chat = cb["message"]["chat"]["id"]
    if not await ctx.is_chat_admin(chat, cb["from"]["id"]):
        return await ctx.tg.answer_cb(cb["id"], ctx.tr(cb["from"]["id"], "admins_only"), alert=True)
    gs = ctx.db.gs(chat)
    if key == "who":
        ctx.db.x("UPDATE gsettings SET who=? WHERE chat_id=?", "admins" if gs["who"] == "all" else "all", chat)
    elif key == "cd":
        nxt = {0: 10, 10: 30, 30: 60, 60: 0}[gs["cooldown"] if gs["cooldown"] in (0, 10, 30, 60) else 0]
        ctx.db.x("UPDATE gsettings SET cooldown=? WHERE chat_id=?", nxt, chat)
    elif key == "dl":
        ctx.db.x("UPDATE gsettings SET download=? WHERE chat_id=?", 1 - gs["download"], chat)
    elif key == "ex":
        ctx.db.x("UPDATE gsettings SET explicit=? WHERE chat_id=?", 1 - gs["explicit"], chat)
    await ctx.tg.answer_cb(cb["id"])
    await ctx.tg.edit_kb(chat, cb["message"]["message_id"], settings_kb(ctx.db.gs(chat)))


async def cmd_setwelcome(ctx: Ctx, msg: dict, args: str):
    chat = _chat(msg)
    if not await ctx.is_chat_admin(chat, _uid(msg)):
        return await ctx.tg.send(chat, ctx.tr(_uid(msg), "admins_only"))
    ctx.db.gs(chat)
    ctx.db.x("UPDATE gsettings SET welcome=? WHERE chat_id=?", args[:400], chat)
    await ctx.tg.send(chat, ctx.tr(_uid(msg), "done"))


async def welcome(ctx: Ctx, msg: dict):
    gs = ctx.db.gs(_chat(msg))
    if gs["welcome"]:
        for u in msg.get("new_chat_members", []):
            if not u.get("is_bot"):
                await ctx.tg.send(_chat(msg), esc(gs["welcome"]).replace("{name}", esc(display_name(u))))


async def run_job(ctx: Ctx, kind: str, p: dict):
    if kind == "wordhunt_end":
        await wordhunt_end(ctx, p["chat"])
    elif kind == "contest_end":
        await contest_end(ctx, p["chat"])
    elif kind == "team_end":
        await team_end(ctx, p["chat"], p["poll"])
