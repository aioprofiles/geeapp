"""Song cards: rich-message markdown (+ HTML fallback) and inline keyboards."""
import urllib.parse

from .db import Track
from .ui import btn
from .util import esc, fmt_dur


def deep(cfg, param: str) -> str:
    return f"https://t.me/{cfg.bot_username}?start={urllib.parse.quote(param)}"


def app_link(cfg, param: str) -> str:
    """Direct Mini App link (works in groups and channels, carries chat_instance)."""
    return f"https://t.me/{cfg.bot_username}/{cfg.app_short}?startapp={urllib.parse.quote(param, safe='')}"


def card_text(t: Track) -> tuple[str, str]:
    dur = f" · {fmt_dur(t.duration)}" if t.duration else ""
    lic = "CC" if "creativecommons" in (t.license or "") else (t.license[:20] if t.license else "")
    meta = " · ".join(x for x in [t.album, f"{t.year}" if t.year else "", lic] if x)
    md = f"## {t.title}\n**{t.artist}**{dur}\n\n{meta}"
    html = f"🎵 <b>{esc(t.title)}</b>\n{esc(t.artist)}{dur}\n<i>{esc(meta)}</i>"
    return md, html


def card_kb(cfg, t: Track, is_fav: bool, in_private: bool = True) -> list:
    tid = t.id
    rows = []
    row1 = []
    if cfg.webapp_url:
        if in_private:
            row1.append(btn("▶ Player", webapp=f"{cfg.webapp_url}/app?t={urllib.parse.quote(tid)}"))
        else:
            row1.append(btn("▶ Player", url=app_link(cfg, f"t_{tid}")))
    row1.append(btn("🎤 Widget", data=f"w:{tid}"))
    rows.append(row1)
    rows.append([btn("📄 Lyrics", data=f"ly:{tid}"), btn("⬇ Download", data=f"dl:{tid}")])
    rows.append([btn("💔" if is_fav else "❤", data=f"fv:{tid}"), btn("➕ Playlist", data=f"pl:{tid}"),
                 btn("🎁", data=f"dd:{tid}"), btn("📔", data=f"di:{tid}")])
    return rows


def results_kb(tracks: list[Track]) -> list:
    return [[btn(f"{t.title} — {t.artist}"[:60], data=f"c:{t.id}")] for t in tracks]
