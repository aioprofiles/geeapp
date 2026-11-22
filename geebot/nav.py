"""Navigation: `n:<screen>[:arg]` callbacks edit the SAME message in place (rich edit with plain fallback)."""
import time

from . import screens
from .app import Ctx

COMMANDS: dict = {}                       # injected by main.py (name -> handler)
CMD_WHITELIST = {"heardle", "fav", "playlists", "top", "wrapped", "history", "diary", "contribs"}
HINTS = {"search": "🔎 Type a song name, a lyric line, or use /search <text>.",
         "feel": "✨ Describe a feeling: /feel calm rainy night",
         "party": "🎉 Add me to a group and send /party (or /duel, /chain, /bingo)."}


async def handle(ctx: Ctx, cb: dict, arg: str):
    parts = arg.split(":")
    name, uid, m = parts[0], cb["from"]["id"], cb["message"]
    chat, mid = m["chat"]["id"], m["message_id"]
    if name == "cmd":
        await ctx.tg.answer_cb(cb["id"])
        fn = COMMANDS.get(parts[1]) if len(parts) > 1 and parts[1] in CMD_WHITELIST else None
        if fn:
            await fn(ctx, {"from": cb["from"], "chat": m["chat"], "text": "", "message_id": mid}, "")
        return
    if name == "hint":
        await ctx.tg.answer_cb(cb["id"])
        return await ctx.tg.send(chat, HINTS.get(parts[1] if len(parts) > 1 else "", "—"))
    if name == "home":
        html, rows = screens.home(ctx, uid)
    elif name == "faq":
        html, rows = screens.faq()
    elif name == "settings":
        html, rows = screens.settings(ctx, uid)
    elif name == "pv":
        u = ctx.db.user(uid) or {}
        ctx.db.x("UPDATE users SET privacy=? WHERE id=?", 0 if u.get("privacy") else 1, uid)
        html, rows = screens.settings(ctx, uid)
    elif name == "lang" and len(parts) > 1 and parts[1] in ("si", "en", "ta"):
        ctx.db.x("UPDATE users SET lang=? WHERE id=?", parts[1], uid)
        html, rows = screens.settings(ctx, uid)
    elif name == "admin" and ctx.is_owner(uid):
        html, rows = screens.admin(ctx)
    elif name == "res" and len(parts) > 1 and parts[1].lstrip("-").isdigit():
        st = ctx.db.kv_get(f"res:{chat}:{mid}")
        if not st:
            return await ctx.tg.answer_cb(cb["id"], "This list has expired — search again.", alert=True)
        page = max(0, int(parts[1]))
        ids = st["ids"]
        start = min(page, max(0, (len(ids) - 1) // screens.PAGE)) * screens.PAGE
        tracks = [t for t in (ctx.db.track(i) for i in ids[start:start + screens.PAGE]) if t]
        html, rows = screens.results(ids, tracks, page, st.get("title") or "Results")
    else:
        return await ctx.tg.answer_cb(cb["id"])
    await ctx.tg.answer_cb(cb["id"])
    await ctx.tg.edit_rich(chat, mid, html, rows)


async def send_results(ctx: Ctx, chat: int, tracks, title: str):
    ids = [t.id for t in tracks][:60]
    shown = [t for t in tracks][:screens.PAGE]
    html, rows = screens.results(ids, shown, 0, title)
    m = await ctx.tg.rich(chat, html, rows)
    ctx.db.kv_set(f"res:{chat}:{m['message_id']}", {"ids": ids, "title": title, "ts": int(time.time())})


async def cmd_menu(ctx: Ctx, msg: dict, args: str):
    html, rows = screens.home(ctx, msg["from"]["id"])
    await ctx.tg.rich(msg["chat"]["id"], html, rows)


async def cmd_about(ctx: Ctx, msg: dict, args: str):
    html, rows = screens.about(ctx)
    await ctx.tg.rich(msg["chat"]["id"], html, rows)


async def cmd_privacy(ctx: Ctx, msg: dict, args: str):
    html, rows = screens.faq()
    await ctx.tg.rich(msg["chat"]["id"], html, rows)
