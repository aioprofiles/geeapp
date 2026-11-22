"""Entry point:  python -m geebot.main     (long polling + scheduler)."""
import asyncio
import logging

from . import admin, commands, donate, group, guest, nav, sched, user, wq
from .app import Ctx
from .config import Config
from .db import DB
from .store import open_db
from .llm import LLM
from .sources import Jamendo, Lrclib
from .tg import Tg

log = logging.getLogger("geebot")

COMMANDS = {
    "start": user.cmd_start, "help": user.cmd_help, "search": user.cmd_search, "feel": user.cmd_feel,
    "lyric": user.cmd_lyric, "fav": user.cmd_fav, "history": user.cmd_history, "playlists": user.cmd_playlists,
    "lang": user.cmd_lang, "rhyme": user.cmd_rhyme, "wrapped": user.cmd_wrapped, "match": user.cmd_match,
    "beat": user.cmd_beat, "premium": user.cmd_premium, "report": user.cmd_report, "reel": user.cmd_reel,
    "heardle": user.cmd_heardle, "dedicate": user.cmd_dedicate, "diary": user.cmd_diary,
    "party": group.cmd_party, "request": group.cmd_request, "queue": group.cmd_queue, "skip": group.cmd_skip,
    "duel": group.cmd_duel, "chain": group.cmd_chain, "missing": group.cmd_missing, "odd": group.cmd_odd,
    "order": group.cmd_order, "scramble": group.cmd_scramble, "wordhunt": group.cmd_wordhunt,
    "bingo": group.cmd_bingo, "roulette": group.cmd_roulette, "singoff": group.cmd_singoff, "hum": group.cmd_hum,
    "team": group.cmd_team, "pick": group.cmd_pick, "g": group.cmd_g, "top": group.cmd_top,
    "tournament": group.cmd_tournament, "settings": group.cmd_settings, "setwelcome": group.cmd_setwelcome,
    "stats": admin.cmd_stats, "takedown": admin.cmd_takedown, "ban": admin.cmd_ban, "unban": admin.cmd_unban,
    "artist": admin.cmd_artist, "ytlink": admin.cmd_ytlink, "setlrc": admin.cmd_setlrc,
    "contribs": admin.cmd_contribs, "channel": admin.cmd_channel,
    "menu": nav.cmd_menu, "about": nav.cmd_about, "privacy": nav.cmd_privacy, "donate": donate.cmd_donate,
    "refund": donate.cmd_refund,
}
nav.COMMANDS = COMMANDS
GATED = {"party", "request", "duel", "chain", "missing", "odd", "order", "scramble", "wordhunt", "bingo",
         "roulette", "singoff", "hum", "team", "pick"}

CALLBACKS = {
    "c": user.cb_card, "fv": user.cb_fav, "ly": user.cb_lyrics, "ro": user.cb_roman, "dl": user.cb_download,
    "w": user.cb_widget, "pl": user.cb_playlist_pick, "pa": user.cb_playlist_add, "po": user.cb_playlist_open,
    "pn": user.cb_playlist_new, "lg": user.cb_lang, "hs": lambda c, cb, a: user.cb_heardle(c, cb, "hs"),
    "hu": lambda c, cb, a: user.cb_heardle(c, cb, "hu"), "dd": user.cb_dedicate, "dw": user.cb_dedicate_when,
    "di": user.cb_diary, "pt": group.cb_party_start, "cv": group.cb_contest_vote, "tj": group.cb_team_join,
    "gs": group.cb_settings, "ap": admin.cb_approve, "n": nav.handle, "dn": donate.cb,
}


async def on_message(ctx: Ctx, msg: dict):
    u = msg.get("from")
    if not u or u.get("is_bot"):
        return
    row = ctx.db.touch_user(u)
    if row and row["banned"]:
        return
    if msg.get("successful_payment"):
        return await donate.on_paid(ctx, msg)
    if msg.get("new_chat_members"):
        return await group.welcome(ctx, msg)
    private = msg["chat"]["type"] == "private"
    text = msg.get("text") or ""
    if text.startswith("/"):
        head, _, rest = text.partition(" ")
        name, _, at = head[1:].partition("@")
        if at and at.lower() != ctx.cfg.bot_username.lower():
            return
        fn = COMMANDS.get(name.lower())
        if not fn or (name == "start" and not private):
            return
        if name in GATED and not await ctx.gate(msg):
            return
        return await fn(ctx, msg, rest.strip())
    if private:
        if await admin.handle_upload(ctx, msg) or await user.handle_flow(ctx, msg):
            return
        if text:
            await user.plain_text_search(ctx, msg)
    elif msg.get("voice") or msg.get("video_note"):
        await group.contest_entry(ctx, msg)
    elif text:
        await group.group_text(ctx, msg)


async def on_callback(ctx: Ctx, cb: dict):
    ctx.db.touch_user(cb["from"])
    prefix, _, arg = (cb.get("data") or "").partition(":")
    fn = CALLBACKS.get(prefix)
    if fn:
        await fn(ctx, cb, arg)
    else:
        await ctx.tg.answer_cb(cb["id"])


async def on_update(ctx: Ctx, u: dict):
    try:
        if "message" in u:
            await on_message(ctx, u["message"])
        elif "callback_query" in u:
            await on_callback(ctx, u["callback_query"])
        elif "guest_message" in u:
            await guest.handle(ctx, u["guest_message"])
        elif "widget_query" in u:
            await wq.handle(ctx, u["widget_query"])
        elif "pre_checkout_query" in u:
            await donate.pre_checkout(ctx, u["pre_checkout_query"])
        elif "poll_answer" in u:
            await group.poll_answer(ctx, u["poll_answer"])
    except Exception:
        log.exception("update %s failed", u.get("update_id"))


ALLOWED = ["message", "callback_query", "guest_message", "widget_query", "shared_widget_query",
           "pre_checkout_query", "poll_answer"]


def build_ctx(cfg: Config, db: DB | None = None) -> Ctx:
    return Ctx(cfg, db or open_db(cfg), Tg(cfg.bot_token, cfg.test_env), LLM(cfg.anthropic_model),
               Jamendo(cfg.jamendo_client_id), Lrclib())


async def poll(ctx: Ctx):
    """Long-polling loop (outbound requests only)."""
    sem, offset = asyncio.Semaphore(20), 0

    async def guarded(u):
        async with sem:
            await on_update(ctx, u)

    while True:
        ups = await ctx.tg.try_call("getUpdates", offset=offset, timeout=50, allowed_updates=ALLOWED) or []
        for u in ups:
            offset = u["update_id"] + 1
            asyncio.create_task(guarded(u))
        if not ups:
            await asyncio.sleep(0.3)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = Config.from_env()
    from . import backup
    backup.restore_sync(cfg)
    ctx = build_ctx(cfg)
    asyncio.create_task(commands.install(ctx.tg))
    asyncio.create_task(sched.loop(ctx))
    asyncio.create_task(backup.loop(ctx))
    log.info("bot started (test_env=%s)", cfg.test_env)
    await poll(ctx)


if __name__ == "__main__":
    asyncio.run(main())
