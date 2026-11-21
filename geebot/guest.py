"""Guest mode (Bot API 10.0): `@bot ...` typed in ANY chat, possibly as a reply. The bot sees only the summoning
message and the message it replies to, and may answer ONCE. Result must be an InlineQueryResult (article here).
Field names `guest_message` / `guest_query_id` should be verified against the Update/Message docs."""
import re

from . import cards, search
from .app import Ctx
from .util import esc

MODES = {
    "translate": ("translate", "පරිවර්තනය", "மொழிபெயர்"),
    "explain": ("explain", "විස්තර", "விளக்கு"),
    "summarize": ("summarize", "summary", "සාරාංශ"),
}
SYS = ("You are summoned as a guest inside a chat. You only see the summoning message and the message it replies to. "
       "Never claim to see other history. Answer in the language of the request. Max 900 characters. "
       "For translate: Sinhala<->English by default. For explain: simple words. Do not reproduce long copyrighted lyrics.")


def parse_mode(req: str) -> str | None:
    low = req.lower()
    for m, words in MODES.items():
        if any(low.startswith(w) or f" {w}" in low for w in words):
            return m
    return None


async def handle(ctx: Ctx, g: dict):
    gid = g.get("guest_query_id")
    if not gid:
        return
    req = re.sub(r"@\w+", "", g.get("text", "")).strip()
    quoted = (g.get("reply_to_message") or {}).get("text") or (g.get("reply_to_message") or {}).get("caption") or ""
    mode = parse_mode(req)

    if mode and ctx.llm.enabled:
        ans = await ctx.llm.ask(SYS, f"Request: {req}\n\nReplied-to message:\n{quoted or '(none)'}", 500)
        if ans:
            return await ctx.tg.answer_guest(gid, esc(ans)[:3800], title=mode)

    q = req or quoted                                   # otherwise: identify the song
    hits = [t for _, t in search.title_search(ctx.db, q, 1)] or [t for _, t, _ in search.lyric_line_search(ctx.db, q, 1)]
    if not hits and ctx.jamendo.enabled:
        hits = await search.combined(ctx.db, ctx.jamendo, q, 1)
    if not hits:
        return await ctx.tg.answer_guest(gid, "🎵 ?", title="No match")
    t = hits[0]
    _, html = cards.card_text(t)
    rows = [[{"text": "Open in bot", "url": cards.deep(ctx.cfg, f"t_{t.id}")}]]
    if ctx.cfg.webapp_url:
        rows[0].append({"text": "▶ Player", "url": cards.app_link(ctx.cfg, f"t_{t.id}")})
    await ctx.tg.answer_guest(gid, html, title=t.title, rows=rows)
