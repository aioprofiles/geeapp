"""Synced-lyrics (.lrc) helpers + chunking for the 1024-byte widget state."""
import json
import re

_TS = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]")


def parse(text: str) -> list[tuple[float, str]]:
    out = []
    for raw in (text or "").splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        line = _TS.sub("", raw).strip()
        for m, s in stamps:
            out.append((int(m) * 60 + float(s), line))
    out.sort(key=lambda x: x[0])
    return out


def dumps(lines) -> str:
    return "\n".join(f"[{int(t // 60):02d}:{t % 60:05.2f}]{txt}" for t, txt in lines)


def plain_lines(text: str) -> list[str]:
    """Lyrics as plain lines whether the input is lrc or plain text."""
    parsed = parse(text)
    if parsed:
        return [l for _, l in parsed if l]
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def current_index(lines, t: float) -> int:
    idx = -1
    for i, (ts, _) in enumerate(lines):
        if ts <= t:
            idx = i
        else:
            break
    return idx


def shift(lines, dt: float):
    return [(max(0.0, t + dt), s) for t, s in lines]


def build_from_plain(plain: list[str], stamps: list[float]):
    return [(t, s) for t, s in zip(stamps, plain)]


def widget_chunk(lines, start_idx: int, rev: int, max_bytes: int = 900) -> tuple[str, int]:
    """Return (chat_data_json, next_index). Lines carry ABSOLUTE song seconds so the widget's
    own clock can place them. Stays under max_bytes (state limit is 1024 bytes of UTF-8)."""
    items: list[list] = []
    i = start_idx
    while i < len(lines):
        t, s = lines[i]
        cand = items + [[round(t, 1), s[:60]]]
        js = json.dumps({"r": rev, "L": cand}, ensure_ascii=False, separators=(",", ":"))
        if len(js.encode()) > max_bytes:
            break
        items = cand
        i += 1
    if not items and i < len(lines):  # one very long line: hard-trim
        t, s = lines[i]
        items, i = [[round(t, 1), s[:40]]], i + 1
    return json.dumps({"r": rev, "L": items}, ensure_ascii=False, separators=(",", ":")), i


def index_after(lines, t: float) -> int:
    """First line index whose timestamp is strictly after t (where the next chunk should start)."""
    for i, (ts, _) in enumerate(lines):
        if ts > t + 0.01:
            return i
    return len(lines)
