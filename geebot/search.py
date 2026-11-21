"""Search: by title/artist, by half-remembered lyric line, and by feeling."""
from . import lrc as L
from . import textutil as tu
from .db import DB, Track

# Fallback when no LLM: feeling words (si/en) -> Jamendo tags
MOODS = {
    "sad": ["sad", "melancholic"], "සංවේග": ["sad", "melancholic"], "දුක": ["sad"], "ආදරේ": ["romantic", "love"],
    "love": ["romantic", "love"], "romantic": ["romantic"], "happy": ["happy", "upbeat"], "සතුට": ["happy"],
    "calm": ["calm", "relaxing"], "සන්සුන්": ["calm", "relaxing"], "workout": ["energetic", "dance"],
    "night": ["ambient", "chillout"], "රාත්‍රී": ["ambient", "chillout"], "rain": ["ambient", "calm"],
    "වැස්ස": ["ambient", "calm"], "mother": ["acoustic", "emotional"], "අම්මා": ["acoustic", "emotional"],
}

FEEL_SYS = ("Turn the user's feeling/situation (Sinhala, Tamil or English) into search hints for a "
            'Creative-Commons music catalogue. JSON: {"tags": [up to 3 English mood/genre tags], '
            '"query": "short English keyword or empty"}')


def title_search(db: DB, q: str, limit=10) -> list[tuple[float, Track]]:
    scored = []
    for t in db.tracks(limit=2000):
        s = max(tu.similarity(q, t.title), tu.similarity(q, f"{t.title} {t.artist}") * 0.95)
        if s >= 0.55:
            scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def lyric_line_search(db: DB, phrase: str, limit=5) -> list[tuple[float, Track, str]]:
    """Half-remembered line -> tracks. Works on lyrics we hold (community / owner / lrclib)."""
    res = []
    for t in db.tracks("(lrc!='' OR plain!='')", limit=3000):
        best, line = 0.0, ""
        for ln in L.plain_lines(t.lrc or t.plain):
            s = tu.similarity(phrase, ln)
            if s > best:
                best, line = s, ln
        if best >= 0.6:
            res.append((best, t, line))
    res.sort(key=lambda x: -x[0])
    return res[:limit]


async def combined(db: DB, jamendo, q: str, limit=10) -> list[Track]:
    out, seen = [], set()
    for _, t in title_search(db, q, limit):
        out.append(t); seen.add(t.id)
    if jamendo.enabled and len(out) < limit:
        try:
            for t in await jamendo.search(q, limit):
                if t.id not in seen:
                    db.upsert_track(t)
                    out.append(t); seen.add(t.id)
        except Exception:  # catalogue offline: local results still work
            pass
    return out[:limit]


async def feeling(db: DB, jamendo, llm, phrase: str, limit=8) -> list[Track]:
    hints = await llm.json(FEEL_SYS, phrase) if llm.enabled else None
    tags = (hints or {}).get("tags") or []
    if not tags:
        low = phrase.lower()
        for k, v in MOODS.items():
            if k in low:
                tags = v
                break
    out: list[Track] = []
    if jamendo.enabled and tags:
        try:
            out = await jamendo.by_tags(tags, limit)
            for t in out:
                db.upsert_track(t)
        except Exception:
            out = []
    if not out and tags:
        out = [t for t in db.tracks(limit=2000) if any(g in t.tags.lower() for g in tags)][:limit]
    return out
