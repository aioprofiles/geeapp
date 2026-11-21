"""Owner / artist / channel tools."""
import time

from . import features, lrc
from .app import Ctx, arg_text, display_name
from .db import Track
from .sources import youtube_id
from .tg import btn
from .util import esc, today


async def cmd_stats(ctx: Ctx, msg: dict, args: str):
    if not ctx.is_owner(msg["from"]["id"]):
        return
    d = ctx.db

    def n(sql, *a):
        return d.one(sql, *a)["n"]

    now = int(time.time())
    users = n("SELECT COUNT(*) n FROM users")
    tracks = n("SELECT COUNT(*) n FROM tracks WHERE takedown=0")
    plays = n("SELECT COUNT(*) n FROM history WHERE ts>?", now - 86400)
    prem = n("SELECT COUNT(*) n FROM users WHERE premium_until>?", now)
    reports = n("SELECT COUNT(*) n FROM reports")
    pending = n("SELECT COUNT(*) n FROM contribs WHERE status='pending'")
    await ctx.tg.send(msg["chat"]["id"],
                      f"👥 {users} users · 🎵 {tracks} tracks\n▶ plays 24h: {plays} · ⭐ premium: {prem}\n"
                      f"🚩 reports: {reports} · ⏳ lyric contribs: {pending}")


async def cmd_takedown(ctx: Ctx, msg: dict, args: str):
    if not ctx.is_owner(msg["from"]["id"]):
        return
    ctx.db.x("UPDATE tracks SET takedown=1 WHERE id=?", args.strip())
    await ctx.tg.send(msg["chat"]["id"], f"removed {esc(args.strip())}")


async def cmd_ban(ctx: Ctx, msg: dict, args: str, val: int = 1):
    if ctx.is_owner(msg["from"]["id"]) and args.strip().isdigit():
        ctx.db.x("UPDATE users SET banned=? WHERE id=?", val, int(args))
        await ctx.tg.send(msg["chat"]["id"], "ok")


async def cmd_unban(ctx: Ctx, msg: dict, args: str):
    await cmd_ban(ctx, msg, args, 0)


async def cmd_artist(ctx: Ctx, msg: dict, args: str):
    """/artist <user_id>  - owner grants the artist role (may upload tracks they own the rights to)."""
    if ctx.is_owner(msg["from"]["id"]) and args.strip().isdigit():
        ctx.db.x("UPDATE users SET role='artist' WHERE id=?", int(args))
        await ctx.tg.send(msg["chat"]["id"], "ok")


async def cmd_ytlink(ctx: Ctx, msg: dict, args: str):
    """/ytlink <track_id> <youtube url>  - attaches the official YouTube embed (play only, never downloaded)."""
    if not ctx.is_artist(msg["from"]["id"]):
        return
    tid, _, url = args.partition(" ")
    vid = youtube_id(url)
    if vid and ctx.db.track(tid):
        ctx.db.x("UPDATE tracks SET video_id=? WHERE id=?", vid, tid)
        await ctx.tg.send(msg["chat"]["id"], "ok")


async def cmd_setlrc(ctx: Ctx, msg: dict, args: str):
    """/setlrc <track_id> as a reply to a message (or .lrc/.txt document) holding the lyrics."""
    uid = msg["from"]["id"]
    t = ctx.db.track(args.strip())
    if not t or not (ctx.is_owner(uid) or (ctx.is_artist(uid) and t.uploader == uid)):
        return await ctx.tg.send(msg["chat"]["id"], "not allowed")
    src = msg.get("reply_to_message") or {}
    text = src.get("text", "")
    if not text and src.get("document"):
        url = await ctx.tg.file_url(src["document"]["file_id"])
        if url:
            text = (await ctx.tg.http.get(url)).text
    if not text:
        return await ctx.tg.send(msg["chat"]["id"], "reply to the lyrics")
    col = "lrc" if lrc.parse(text) else "plain"
    ctx.db.x(f"UPDATE tracks SET {col}=? WHERE id=?", text, t.id)
    await ctx.tg.send(msg["chat"]["id"], f"saved ({col})")


async def handle_upload(ctx: Ctx, msg: dict) -> bool:
    """Owner/artist sends an audio file, caption: `Title | Artist | licence | download=yes/no`.
    By uploading, the sender declares they hold the rights (see README: takedown policy)."""
    uid = msg["from"]["id"]
    a = msg.get("audio")
    if not a or msg["chat"]["type"] != "private" or not ctx.is_artist(uid):
        return False
    parts = [p.strip() for p in (msg.get("caption") or "").split("|")]
    title = parts[0] if parts and parts[0] else a.get("title") or "Untitled"
    artist = parts[1] if len(parts) > 1 and parts[1] else a.get("performer") or display_name(msg["from"])
    lic = parts[2] if len(parts) > 2 else "all rights reserved by uploader"
    dl = len(parts) > 3 and parts[3].lower().startswith("download=y")
    t = Track(id=f"up:{a['file_unique_id']}", title=title, artist=artist, duration=a.get("duration", 0), license=lic,
              source="upload", downloadable=int(dl), audio_file_id=a["file_id"], uploader=uid)
    ctx.db.upsert_track(t)
    await ctx.tg.send(msg["chat"]["id"], f"✅ <code>{esc(t.id)}</code> saved. /ytlink {t.id} &lt;url&gt; · /setlrc {t.id}")
    return True


async def cmd_contribs(ctx: Ctx, msg: dict, args: str):
    if not ctx.is_owner(msg["from"]["id"]):
        return
    rows = ctx.db.q("SELECT id,track_id,user_id FROM contribs WHERE status='pending' ORDER BY id LIMIT 10")
    await ctx.tg.send(msg["chat"]["id"], "\n".join(f"#{r['id']} {esc(r['track_id'])} by {r['user_id']}" for r in rows) or "—",
                      [[btn(f"✅ #{r['id']}", data=f"ap:{r['id']}")] for r in rows])


async def cb_approve(ctx: Ctx, cb: dict, cid: str):
    if not ctx.is_owner(cb["from"]["id"]):
        return await ctx.tg.answer_cb(cb["id"])
    r = features.approve_contrib(ctx.db, int(cid))
    await ctx.tg.answer_cb(cb["id"], "approved" if r else "gone")
    if r:
        txt = "🎉 Your lyric timings were approved!" + ("".join(f"\n🏅 {b}" for b in r["new_badges"]))
        await ctx.tg.try_call("sendMessage", chat_id=r["user_id"], text=txt)


# ---------- channels ----------------------------------------------------------------------
async def cmd_channel(ctx: Ctx, msg: dict, args: str):
    """/channel add <@name|id> [hour] | /channel off <@name|id>. Posts a 'song of the day' card daily."""
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    sub, _, rest = args.partition(" ")
    target, _, hr = rest.strip().partition(" ")
    if sub not in ("add", "off") or not target:
        return await ctx.tg.send(chat, "/channel add @channel [hour 0-23]  ·  /channel off @channel")
    info = await ctx.tg.try_call("getChat", chat_id=target)
    if not info:
        return await ctx.tg.send(chat, "I can't see that channel. Add me as an admin first.")
    cid = info["id"]
    if not await ctx.is_chat_admin(cid, uid):
        return await ctx.tg.send(chat, ctx.tr(uid, "admins_only"))
    if sub == "off":
        ctx.db.x("DELETE FROM channels WHERE chat_id=?", cid)
    else:
        hour = int(hr) if hr.isdigit() and 0 <= int(hr) <= 23 else 9
        ctx.db.x("INSERT INTO channels(chat_id,owner_id,hour) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET hour=excluded.hour", cid, uid, hour)
    await ctx.tg.send(chat, ctx.tr(uid, "done"))
