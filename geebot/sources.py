"""Legal catalogue sources. Jamendo = Creative-Commons music with per-track download permission.
Parameter/field names follow Jamendo API v3 as I know it - verify against their docs."""
import re

import httpx

from .db import Track

JAMENDO = "https://api.jamendo.com/v3.0/tracks/"
LRCLIB = "https://lrclib.net/api"
_YT = re.compile(r"(?:youtu\.be/|v=|embed/)([A-Za-z0-9_-]{11})")


def youtube_id(s: str) -> str:
    m = _YT.search(s or "")
    return m.group(1) if m else (s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s or "") else "")


class Jamendo:
    def __init__(self, client_id: str, http: httpx.AsyncClient | None = None):
        self.cid = client_id
        self.http = http or httpx.AsyncClient(timeout=20)

    @property
    def enabled(self) -> bool:
        return bool(self.cid)

    async def _get(self, **params) -> list[Track]:
        if not self.cid:
            return []
        base = {"client_id": self.cid, "format": "json", "limit": 10, "include": "musicinfo",
                "audioformat": "mp32", "imagesize": 300}
        r = await self.http.get(JAMENDO, params={**base, **params})
        r.raise_for_status()
        out = []
        for x in r.json().get("results", []):
            tags = x.get("musicinfo", {}).get("tags", {})
            tg = ",".join(tags.get("genres", []) + tags.get("vartags", []))
            rel = x.get("releasedate") or ""
            out.append(Track(
                id=f"jm:{x['id']}", title=x.get("name", ""), artist=x.get("artist_name", ""),
                album=x.get("album_name", ""), duration=int(x.get("duration") or 0),
                audio_url=x.get("audio", ""), image=x.get("image", ""), license=x.get("license_ccurl", ""),
                source="jamendo", tags=tg, year=int(rel[:4]) if rel[:4].isdigit() else 0,
                downloadable=1 if x.get("audiodownload_allowed") else 0))
        return out

    async def search(self, q: str, limit=10) -> list[Track]:
        return await self._get(search=q, limit=limit, order="relevance")

    async def by_tags(self, tags: list[str], limit=10) -> list[Track]:
        return await self._get(tags="+".join(tags[:3]), limit=limit, order="popularity_week")


class Lrclib:
    """Community synced lyrics. Off by default: lyric licensing is the operator's responsibility."""

    def __init__(self, http: httpx.AsyncClient | None = None):
        self.http = http or httpx.AsyncClient(timeout=15)

    async def find(self, artist: str, title: str, duration: int = 0) -> tuple[str, str]:
        """-> (synced_lrc, plain). Either may be ''."""
        try:
            r = await self.http.get(f"{LRCLIB}/search", params={"track_name": title, "artist_name": artist})
            r.raise_for_status()
            items = r.json()
        except (httpx.HTTPError, ValueError):
            return "", ""
        if duration:
            items = sorted(items, key=lambda i: abs((i.get("duration") or 0) - duration))
        for i in items[:3]:
            if i.get("syncedLyrics") or i.get("plainLyrics"):
                return i.get("syncedLyrics") or "", i.get("plainLyrics") or ""
        return "", ""
