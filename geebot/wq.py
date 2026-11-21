"""Widget queries (Bot API 10.4): the widget asks (<=64 bytes), we answer within 15 s and edit its state."""
import json

from . import lrc
from .app import Ctx
from .user import audio_path, send_download


async def handle(ctx: Ctx, q: dict):
    qid, user = q["id"], q["from"]
    chat = (q.get("chat") or {}).get("id")
    mid = q.get("message_id")
    data = q.get("data", "")
    meta = ctx.db.kv_get(f"wd:{chat}:{mid}") if chat and mid else None
    if not meta:
        return await ctx.tg.answer_widget(qid, "expired")

    if meta["kind"] == "beat" and data.startswith("s:"):
        try:
            sc = int(data[2:])
        except ValueError:
            return await ctx.tg.answer_widget(qid, "bad")
        if not 0 <= sc <= 60:                       # 20 taps x max 3 points: anything else is tampering
            return await ctx.tg.answer_widget(qid, "invalid")
        ctx.db.add_score(chat, user["id"], user.get("first_name", ""), "beat", sc // 6)
        best = ctx.db.one("SELECT MAX(points) m FROM scores WHERE user_id=? AND game='beat'", user["id"])["m"]
        return await ctx.tg.answer_widget(qid, f"saved · best {best}")

    t = ctx.db.track(meta.get("tid", ""))
    if not t:
        return await ctx.tg.answer_widget(qid, "gone")

    if data.startswith("m:"):                       # next lyric chunk
        try:
            last_t = float(data[2:])
        except ValueError:
            return await ctx.tg.answer_widget(qid, "bad")
        await ctx.tg.answer_widget(qid, "")
        lines = lrc.parse(t.lrc)
        start = lrc.index_after(lines, last_t)
        if start >= len(lines):
            d = {"r": meta["rev"] + 1, "L": [], "e": 1}
            js = json.dumps(d, separators=(",", ":"))
        else:
            js, nxt = lrc.widget_chunk(lines, start, meta["rev"] + 1)
            if nxt >= len(lines):
                d = json.loads(js); d["e"] = 1
                js = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        meta["rev"] += 1
        ctx.db.kv_set(f"wd:{chat}:{mid}", meta)
        # keep the previous line visible: only replace when there is something new
        if json.loads(js)["L"]:
            await ctx.tg.edit_widget(chat, mid, chat_data=js)
        return

    if data == "a":                                 # audio message (only for tracks we may redistribute)
        if not t.downloadable:
            return await ctx.tg.answer_widget(qid, "Use ▶ Player")
        await ctx.tg.answer_widget(qid, "sending…")
        src = await audio_path(ctx, t)
        if src:
            with open(src, "rb") as f:
                await ctx.tg.send_audio_bytes(chat, f.read(), f"{t.title}.mp3", t.title, t.artist)
            ctx.db.log_play(user["id"], t.id)
        return

    if data == "dl":
        await ctx.tg.answer_widget(qid, "…")
        return await send_download(ctx, chat, user["id"], t)

    await ctx.tg.answer_widget(qid, "?")
