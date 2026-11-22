"""Every screen = (rich HTML, button rows). Handlers never build text or keyboards themselves."""
import math
import time
import urllib.parse

from . import rich as R
from .app import Ctx
from .cards import app_link
from .db import Track
from .theme import B, grid
from .util import fmt_dur

PAGE = 5


def _lic(t: Track) -> str:
    if "creativecommons" in (t.license or ""):
        return "Creative Commons"
    return (t.license or "—")[:40]


def home(ctx: Ctx, uid: int) -> tuple[str, list]:
    u = ctx.db.user(uid) or {}
    favs = ctx.db.one("SELECT COUNT(*) n FROM favs WHERE user_id=?", uid)["n"]
    badges = ", ".join(r["badge"] for r in ctx.db.q("SELECT badge FROM badges WHERE user_id=?", uid)) or "—"
    prem = time.strftime("until %Y-%m-%d", time.gmtime(u["premium_until"])) if ctx.db.is_premium(uid) else "—"
    html = R.doc(
        R.heading("🎵 ගී · Music Portal", 2),
        R.para("Search songs, follow synced lyrics, play daily games and support the project."),
        R.details("What you can do here", R.table([
            ("🔎 Search", "By title, a half-remembered lyric line, or a feeling"),
            ("🎤 Lyrics", "Karaoke widget and a Mini App player with video"),
            ("🎧 Heardle", "Daily clip game with a streak and a share card"),
            ("🎉 Groups", "Party, duels, quizzes, bingo, voice contests"),
            ("🎁 Dedications", "Send a song to someone, even scheduled"),
            ("📈 Wrapped", "Your yearly listening summary"),
            ("💖 Support", "Stars from 1 ⭐: badges and perks")])),
        R.kv_table([("🔥 Heardle streak", u.get("streak", 0)), ("❤ Favorites", favs),
                    ("⭐ Premium", prem), ("🏅 Badges", badges)]),
        R.callout("Pick a quick action below, or just type a song name."))
    rows = [
        [B("🔎 Search", "n:hint:search", "primary"), B("✨ By feeling", "n:hint:feel", "primary")],
        [B("🎧 Daily Heardle", "n:cmd:heardle", "success"), B("🎉 Group party", "n:hint:party", "success")],
        [B("⭐ Favorites", "n:cmd:fav"), B("📃 Playlists", "n:cmd:playlists")],
        [B("🏆 Top players", "n:cmd:top"), B("📈 Wrapped", "n:cmd:wrapped")],
        [B("💖 Support", "dn:home", "success"), B("❓ Help & FAQ", "n:faq")],
        [B("⚙ Settings", "n:settings")]]
    if ctx.is_owner(uid):
        rows.append([B("🛠 Admin Panel", "n:admin", "danger")])
    return html, rows


def song_card(ctx: Ctx, uid: int, t: Track, in_private: bool = True) -> tuple[str, list]:
    lyr = "synced" if t.lrc else ("plain" if t.plain else "—")
    html = R.doc(R.heading(t.title, 3), R.table([
        ("Artist", t.artist), ("Album", t.album or "—"), ("Year", t.year or "—"),
        ("Duration", fmt_dur(t.duration) if t.duration else "—"), ("Licence", _lic(t)),
        ("Lyrics", lyr), ("Download", "allowed" if t.downloadable else "not permitted"),
        ("Video", "yes" if t.video_id else "—")]))
    tid = t.id
    first = []
    if ctx.cfg.webapp_url:
        first.append(B("▶ Player", role="primary", **({"webapp": f"{ctx.cfg.webapp_url}/app?t={urllib.parse.quote(tid)}"}
                                                      if in_private else {"url": app_link(ctx.cfg, f"t_{tid}")})))
    first.append(B("🎤 Karaoke widget", f"w:{tid}", "primary"))
    fav = ctx.db.is_fav(uid, tid)
    rows = [first,
            [B("📄 Lyrics", f"ly:{tid}"), B("⬇ Download", f"dl:{tid}", "success" if t.downloadable else "muted")],
            [B("💔 Unfavorite" if fav else "❤ Favorite", f"fv:{tid}"), B("➕ Playlist", f"pl:{tid}")],
            [B("🎁 Dedicate", f"dd:{tid}"), B("📔 Diary", f"di:{tid}")],
            [B("🏠 Menu", "n:home")]]
    return html, rows


def results(ids: list[str], tracks: list[Track], page: int, title: str) -> tuple[str, list]:
    pages = max(1, math.ceil(len(ids) / PAGE))
    page = max(0, min(page, pages - 1))
    shown = tracks
    html = R.doc(R.heading(title, 3), R.footer(f"Page {page + 1}/{pages} · {len(ids)} songs"))
    rows = [[B(f"{t.title} — {t.artist}"[:60], f"c:{t.id}")] for t in shown]
    nav = []
    if page > 0:
        nav.append(B("‹ Prev", f"n:res:{page - 1}", "primary"))
    if page < pages - 1:
        nav.append(B("Next ›", f"n:res:{page + 1}", "primary"))
    if nav:
        rows.append(nav)
    rows.append([B("🏠 Main Menu", "n:home", "success")])
    return html, rows


def faq() -> tuple[str, list]:
    html = R.doc(
        R.heading("❓ Help & FAQ", 3),
        R.details("Where do the songs come from?", "Creative-Commons music (Jamendo) and tracks uploaded by approved artists. "
                  "We do not rip YouTube or TikTok. Videos are the official YouTube embed (play only).", open=True),
        R.details("Downloads", "Only tracks whose licence allows it. Free users get a few downloads per day; "
                  "supporters and Premium get more. Lyrics are embedded in the file and a .lrc is included."),
        R.details("Lyrics & timings", "Lyrics come from owners, artists and the community. Use the Sync tab in the player "
                  "to time a song; approved timings earn badges. Report a problem with /report <track id> <reason>."),
        R.details("Stars & supporters", "Donate any amount from 1 ⭐ with /donate. Telegram processes the payment. "
                  "You get a Supporter badge by tier. Stars purchases are final unless the owner refunds them."),
        R.details("Privacy", "We store your Telegram id, username, favorites, play history and game scores. "
                  "Voice notes sent in group games are not stored by the bot. Turn on Privacy Mode in Settings to hide "
                  "your name on boards. To delete your data, contact the owner."),
        R.details("Groups", "Add the bot to a group and use /party, /duel, /chain, /missing, /bingo, /roulette. "
                  "Admins control who can start games in /settings."))
    return html, [[B("🏠 Main Menu", "n:home", "success")]]


def settings(ctx: Ctx, uid: int) -> tuple[str, list]:
    u = ctx.db.user(uid) or {}
    cur, pv = u.get("lang", "si"), bool(u.get("privacy"))
    html = R.doc(R.heading("⚙ Settings", 3), R.kv_table([("Language", {"si": "සිංහල", "en": "English", "ta": "தமிழ்"}.get(cur, cur)),
                                                          ("Privacy Mode", "ON — your name is hidden on boards" if pv else "OFF")]))
    rows = [[B(("✓ " if cur == c else "") + n, f"n:lang:{c}", "primary" if cur == c else "muted")
             for c, n in (("si", "සිංහල"), ("en", "English"), ("ta", "தமிழ்"))],
            [B("🕶 Privacy Mode: " + ("ON" if pv else "OFF"), "n:pv", "success" if pv else "muted")],
            [B("🏠 Main Menu", "n:home", "success")]]
    return html, rows


def about(ctx: Ctx) -> tuple[str, list]:
    html = R.doc(R.heading("🎵 ගී", 3), R.para("A music companion for Telegram: legal catalogue, synced lyrics, daily games, "
                                              "dedications and a Mini App player."),
                 R.kv_table([("Catalogue", "Creative Commons + artist uploads"), ("Downloads", "licence permitting"),
                             ("Support", "Stars via /donate")]))
    return html, [[B("💖 Support", "dn:home", "success"), B("🏠 Menu", "n:home")]]


def admin(ctx: Ctx) -> tuple[str, list]:
    d, now = ctx.db, int(time.time())

    def n(sql, *a):
        return d.one(sql, *a)["n"]
    stars = d.one("SELECT COALESCE(SUM(stars),0) n FROM payments WHERE refunded=0")["n"]
    html = R.doc(R.heading("🛠 Admin Panel", 3), R.kv_table([
        ("Users", n("SELECT COUNT(*) n FROM users")), ("Tracks", n("SELECT COUNT(*) n FROM tracks WHERE takedown=0")),
        ("Plays (24h)", n("SELECT COUNT(*) n FROM history WHERE ts>?", now - 86400)),
        ("Premium users", n("SELECT COUNT(*) n FROM users WHERE premium_until>?", now)),
        ("Stars received", stars), ("Open reports", n("SELECT COUNT(*) n FROM reports")),
        ("Pending lyric timings", n("SELECT COUNT(*) n FROM contribs WHERE status='pending'"))]))
    return html, [[B("⏳ Review lyric timings", "n:cmd:contribs", "primary")], [B("🏠 Main Menu", "n:home", "success")]]
