"""Features that are mostly data logic: wrapped, dedications, diary, taste match, hall of fame."""
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import games
from .db import DB
from .util import esc


def year_bounds(year: int, tz_min: int = 330) -> tuple[int, int]:
    a = datetime(year, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=tz_min)
    b = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=tz_min)
    return int(a.timestamp()), int(b.timestamp())


def wrapped(db: DB, uid: int, year: int, tz_min: int = 330) -> dict | None:
    a, b = year_bounds(year, tz_min)
    rows = db.q("SELECT h.track_id, h.ts, t.title, t.artist, t.duration FROM history h "
                "LEFT JOIN tracks t ON t.id=h.track_id WHERE h.user_id=? AND h.ts>=? AND h.ts<?", uid, a, b)
    if not rows:
        return None
    tracks = Counter((r["title"] or r["track_id"], r["artist"] or "") for r in rows)
    artists = Counter(r["artist"] for r in rows if r["artist"])
    days = Counter(datetime.fromtimestamp(r["ts"] + tz_min * 60, timezone.utc).strftime("%Y-%m-%d") for r in rows)
    minutes = sum((r["duration"] or 180) for r in rows) // 60
    u = db.user(uid) or {}
    return {"plays": len(rows), "minutes": minutes, "top_tracks": tracks.most_common(5),
            "top_artists": artists.most_common(3), "busiest_day": days.most_common(1)[0],
            "best_streak": u.get("best_streak", 0)}


def wrapped_text(w: dict, year: int, name: str, bot: str) -> tuple[str, str]:
    tt = "\n".join(f"{i}. {t[0]} — {t[1]}" for i, (t, _) in enumerate(w["top_tracks"], 1))
    aa = ", ".join(a for a, _ in w["top_artists"]) or "-"
    md = (f"## {name}ගේ {year} 🎧\n**{w['plays']}** plays · **{w['minutes']}** minutes\n\n"
          f"**Top songs**\n{tt}\n\n**Top artists:** {aa}\n**Busiest day:** {w['busiest_day'][0]} ({w['busiest_day'][1]} plays)\n"
          f"**Best Heardle streak:** {w['best_streak']} 🔥\n\n@{bot}")
    html = (f"🎧 <b>{esc(name)} — {year}</b>\n<b>{w['plays']}</b> plays · <b>{w['minutes']}</b> min\n\n"
            + esc(tt) + f"\n\n<b>Top artists:</b> {esc(aa)}\n<b>Busiest day:</b> {w['busiest_day'][0]}\n"
            f"<b>Heardle streak:</b> {w['best_streak']} 🔥\n@{bot}")
    return md, html


def taste(db: DB, a: int, b: int) -> dict:
    def sets(uid):
        rows = db.q("SELECT track_id FROM favs WHERE user_id=? UNION SELECT track_id FROM history WHERE user_id=?", uid, uid)
        ids = {r["track_id"] for r in rows}
        arts = {r["artist"] for r in db.q(f"SELECT DISTINCT artist FROM tracks WHERE id IN ({','.join('?' * len(ids))})", *ids)} if ids else set()
        return ids, arts
    (ta, aa), (tb, ab) = sets(a), sets(b)
    return games.taste_match(ta, tb, aa, ab)


# ---- dedications -----------------------------------------------------------
def add_dedication(db: DB, from_id: int, to_username: str, track_id: str, note: str, send_at: int, anonymous=False) -> int:
    return db.x("INSERT INTO dedications(from_id,to_username,track_id,note,anonymous,send_at) VALUES(?,?,?,?,?,?)",
                from_id, to_username.lstrip("@").lower(), track_id, note[:500], int(anonymous), send_at)


def due_dedications(db: DB) -> list[dict]:
    return db.q("SELECT * FROM dedications WHERE sent=0 AND send_at<=? LIMIT 50", int(time.time()))


def recipient_id(db: DB, username: str) -> int | None:
    r = db.one("SELECT id FROM users WHERE username=?", username.lstrip("@").lower())
    return r["id"] if r else None


# ---- diary (time capsule) ----------------------------------------------------
def add_diary(db: DB, uid: int, track_id: str, note: str, remind_after_days: int = 365):
    now = int(time.time())
    db.x("INSERT INTO diary(user_id,track_id,note,ts,remind_at) VALUES(?,?,?,?,?)",
         uid, track_id, note[:800], now, now + remind_after_days * 86400)


def due_diary(db: DB) -> list[dict]:
    return db.q("SELECT rowid AS rid, * FROM diary WHERE reminded=0 AND remind_at<=? LIMIT 50", int(time.time()))


# ---- lyric-sync community ---------------------------------------------------
def approve_contrib(db: DB, cid: int) -> dict | None:
    c = db.one("SELECT * FROM contribs WHERE id=? AND status='pending'", cid)
    if not c:
        return None
    db.x("UPDATE tracks SET lrc=? WHERE id=?", c["lrc"], c["track_id"])
    db.x("UPDATE contribs SET status='approved' WHERE id=?", cid)
    n = db.one("SELECT COUNT(*) n FROM contribs WHERE user_id=? AND status='approved'", c["user_id"])["n"]
    badges = [b for th, b in ((1, "Lyrics Helper"), (5, "Lyrics Pro"), (20, "Lyrics Master")) if n >= th and db.give_badge(c["user_id"], b)]
    return {"user_id": c["user_id"], "track_id": c["track_id"], "new_badges": badges}


def lyric_reel_ok(license_url: str) -> bool:
    """Reels remix the audio, so only allow licences that permit derivatives."""
    u = (license_url or "").lower()
    return "creativecommons.org" in u and "/nd" not in u and "-nd" not in u
