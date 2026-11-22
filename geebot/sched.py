"""Background loop: scheduled dedications, diary reminders, game timers, channel 'song of the day'."""
import asyncio
import json
import logging

from . import cards, features, games, group
from .app import Ctx
from .user import send_dedication
from .util import local_now, today

log = logging.getLogger("sched")
_last_prune = 0.0


def prune_results(db, max_age: int = 3 * 86400) -> int:
    """Search-result pages are stored in kv (key 'res:<chat>:<msg>'); drop the old ones. Portable SQL (no LIKE '%')."""
    import time
    n = 0
    for r in db.q("SELECT k, v FROM kv WHERE substr(k,1,4)='res:'"):
        try:
            ts = json.loads(r["v"]).get("ts", 0)
        except ValueError:
            ts = 0
        if ts < time.time() - max_age:
            db.kv_del(r["k"]); n += 1
    return n


async def tick(ctx: Ctx):
    global _last_prune
    db = ctx.db
    import time
    if time.time() - _last_prune > 3600:
        _last_prune = time.time()
        prune_results(db)
    for d in features.due_dedications(db):
        rid = features.recipient_id(db, d["to_username"])
        if rid:
            await send_dedication(ctx, d, rid)
        else:  # recipient never started the bot: tell the sender how to deliver it
            db.x("UPDATE dedications SET sent=2 WHERE id=?", d["id"])
            await ctx.tg.try_call("sendMessage", chat_id=d["from_id"],
                                  text=f"@{d['to_username']} hasn't started the bot yet. Send them this link:\n{cards.deep(ctx.cfg, 'ded_' + str(d['id']))}")
    for r in features.due_diary(db):
        t = db.track(r["track_id"])
        await ctx.tg.try_call("sendMessage", chat_id=r["user_id"],
                              text=f"📔 {t.title if t else ''}\n{r['note']}")
        db.x("UPDATE diary SET reminded=1 WHERE rowid=?", r["rid"])
    for j in db.due_jobs():
        db.job_done(j["id"])
        try:
            await group.run_job(ctx, j["kind"], json.loads(j["payload"]))
        except Exception:
            log.exception("job %s failed", j["kind"])
    now = local_now(ctx.cfg.tz_offset_min)
    day = today(ctx.cfg.tz_offset_min)
    for ch in db.q("SELECT * FROM channels WHERE hour<=? AND last_day!=?", now.hour, day):
        t = games.daily_track("channel:" + day, db.tracks(limit=3000))
        if not t:
            continue
        md, html = cards.card_text(t)
        rows = [[{"text": "Open in bot", "url": cards.deep(ctx.cfg, f"t_{t.id}")}]]
        if ctx.cfg.webapp_url:
            rows[0].append({"text": "▶ Player", "url": cards.app_link(ctx.cfg, f"t_{t.id}")})
        await ctx.tg.send_rich(ch["chat_id"], "### 🎵 Song of the day\n\n" + md, "🎵 <b>Song of the day</b>\n" + html, rows)
        db.x("UPDATE channels SET last_day=? WHERE chat_id=?", day, ch["chat_id"])


async def loop(ctx: Ctx, every: float = 20):
    while True:
        try:
            await tick(ctx)
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(every)
