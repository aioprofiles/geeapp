"""Pure game logic (no Telegram calls) so it can be unit-tested. handlers.py wires it to chats."""
import hashlib
import random

from . import lrc as L
from . import textutil as tu
from .db import Track

CLIP_STEPS = [1, 2, 4, 7, 11, 16]          # Heardle: seconds revealed per attempt
GUESS_OK = 0.8                              # similarity needed to accept a title guess


# ---- Daily Heardle ---------------------------------------------------------
def daily_track(day: str, tracks: list[Track]) -> Track | None:
    pool = sorted((t for t in tracks if t.audio_url or t.audio_file_id), key=lambda t: t.id)
    if not pool:
        return None
    return pool[int(hashlib.sha256(day.encode()).hexdigest(), 16) % len(pool)]


def guess_ok(guess: str, t: Track) -> bool:
    return tu.similarity(guess, t.title) >= GUESS_OK


def clip_seconds(attempt_no: int) -> int:
    return CLIP_STEPS[min(attempt_no, len(CLIP_STEPS) - 1)]


def share_row(day: str, attempts: list[str], won: bool) -> str:
    """attempts: list of 'x' (wrong) / 's' (skipped). Wordle-style share line."""
    cells = ["🟥" if a in ("x", "s") else "🟩" for a in attempts]
    if won:
        cells[-1] = "🟩"
    cells += ["⬛"] * (len(CLIP_STEPS) - len(cells))
    return f"🎧 Heardle {day}\n{''.join(cells)}"


def next_streak(last_day: str, today: str, streak: int, yesterday: str) -> int:
    if last_day == today:
        return streak
    return streak + 1 if last_day == yesterday else 1


# ---- Lyrics games ----------------------------------------------------------
def _lines(t: Track) -> list[str]:
    return [l for l in L.plain_lines(t.lrc or t.plain) if len(l.split()) >= 4]


def missing_word(t: Track, rng: random.Random, pool_words: list[str]) -> dict | None:
    """Blank one word of a lyric line -> quiz with 4 options. Shows ONE short line only."""
    lines = _lines(t)
    if not lines:
        return None
    line = rng.choice(lines)
    toks = line.split()
    cands = [i for i, w in enumerate(toks) if len(tu.graphemes(tu.norm(w))) >= 3]
    if not cands:
        return None
    i = rng.choice(cands)
    answer = toks[i]
    distract = [w for w in pool_words if tu.norm(w) != tu.norm(answer) and len(tu.graphemes(tu.norm(w))) >= 3]
    rng.shuffle(distract)
    opts = list(dict.fromkeys([answer] + distract[:3]))
    if len(opts) < 3:
        return None
    rng.shuffle(opts)
    toks[i] = "____"
    return {"question": " ".join(toks), "options": opts, "correct": opts.index(answer), "track": t.id}


def scramble(t: Track, rng: random.Random, n: int = 4) -> dict | None:
    lines = L.plain_lines(t.lrc or t.plain)
    if len(lines) < n:
        return None
    s = rng.randrange(0, len(lines) - n + 1)
    chunk = lines[s:s + n]
    order = list(range(n))
    for _ in range(10):
        rng.shuffle(order)
        if order != sorted(order):
            break
    shown = [chunk[i] for i in order]                     # what the player sees, numbered 1..n
    answer = [order.index(k) + 1 for k in range(n)]       # numbers in the correct reading order
    return {"shown": shown, "answer": answer, "track": t.id}


def check_scramble(text: str, answer: list[int]) -> bool:
    nums = [int(c) for c in text if c.isdigit()]
    return nums == answer


def chain_start(t: Track, rng: random.Random) -> dict | None:
    lines = L.plain_lines(t.lrc or t.plain)
    if len(lines) < 4:
        return None
    i = rng.randrange(0, len(lines) - 2)
    return {"track": t.id, "i": i, "round": 1, "max": 8}


def chain_check(guess: str, expected_line: str) -> bool:
    return tu.similarity(guess, expected_line) >= 0.75


def odd_one_out(tracks: list[Track], rng: random.Random) -> dict | None:
    by: dict[str, list[Track]] = {}
    for t in tracks:
        by.setdefault(t.artist, []).append(t)
    groups = [v for v in by.values() if len(v) >= 3]
    others = [t for t in tracks if groups and t.artist != groups[0][0].artist]
    if not groups or not others:
        return None
    g = rng.choice(groups)
    three = rng.sample(g, 3)
    odd = rng.choice([t for t in tracks if t.artist != g[0].artist])
    opts = three + [odd]
    rng.shuffle(opts)
    return {"question": "Which song is by a DIFFERENT artist?", "options": [f"{t.title}" for t in opts],
            "correct": opts.index(odd), "artist": g[0].artist}


def before_after(tracks: list[Track], rng: random.Random) -> dict | None:
    dated = [t for t in tracks if t.year]
    rng.shuffle(dated)
    for a in dated:
        for b in dated:
            if a.year != b.year:
                first = a if a.year < b.year else b
                opts = [a.title, b.title]
                return {"question": "Which was released FIRST?", "options": opts, "correct": opts.index(first.title)}
    return None


# ---- Word hunt -------------------------------------------------------------
def wordhunt_valid(word: str, title_guess: str, tracks: list[Track]) -> Track | None:
    """A guess counts if it matches a known title whose lyrics/title contain the word."""
    w = tu.norm(word)
    for t in tracks:
        if tu.similarity(title_guess, t.title) < GUESS_OK:
            continue
        hay = tu.norm(f"{t.title} {t.lrc} {t.plain}")
        if w and w in hay:
            return t
    return None


# ---- Bingo -----------------------------------------------------------------
def bingo_card(seed: int, pool: list[str], size: int = 3) -> list[list[str]]:
    rng = random.Random(seed)
    items = rng.sample(pool, size * size)
    return [items[r * size:(r + 1) * size] for r in range(size)]


def bingo_marks(card: list[list[str]], track: Track) -> set[tuple[int, int]]:
    hay = tu.norm(f"{track.artist} {track.tags} {track.album}")
    return {(r, c) for r, row in enumerate(card) for c, item in enumerate(row) if tu.norm(item) and tu.norm(item) in hay}


def bingo_win(marks: set[tuple[int, int]], size: int = 3) -> bool:
    rows = any(all((r, c) in marks for c in range(size)) for r in range(size))
    cols = any(all((r, c) in marks for r in range(size)) for c in range(size))
    d1 = all((i, i) in marks for i in range(size))
    d2 = all((i, size - 1 - i) in marks for i in range(size))
    return rows or cols or d1 or d2


def render_bingo(card, marks) -> str:
    return "\n".join(" | ".join(("✅ " if (r, c) in marks else "") + x for c, x in enumerate(row))
                     for r, row in enumerate(card))


# ---- Taste match -----------------------------------------------------------
def taste_match(a_tracks: set[str], b_tracks: set[str], a_artists: set[str], b_artists: set[str]) -> dict:
    ts = a_tracks & b_tracks
    ar = a_artists & b_artists
    ju = len(ts) / max(1, len(a_tracks | b_tracks))
    ja = len(ar) / max(1, len(a_artists | b_artists))
    return {"percent": round(100 * (0.6 * ja + 0.4 * ju)), "tracks": sorted(ts), "artists": sorted(ar)}


# ---- Points ----------------------------------------------------------------
def speed_points(elapsed: float, base: int = 3) -> int:
    return base + (2 if elapsed < 5 else 1 if elapsed < 15 else 0)
