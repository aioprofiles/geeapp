"""ffmpeg helpers: Heardle clips, lyric-embedded downloads, lyric reel videos."""
import asyncio
import hashlib
import os
import tempfile

MAX_BYTES = 30 * 1024 * 1024


async def run(*args: str, cwd: str | None = None) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*args, cwd=cwd, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode, out.decode(errors="ignore")[-600:]


async def fetch(url: str, media_dir: str, http=None) -> str:
    """Download (cached) an audio file; refuses anything over 30 MB."""
    os.makedirs(media_dir, exist_ok=True)
    path = os.path.join(media_dir, hashlib.sha1(url.encode()).hexdigest() + ".mp3")
    if os.path.exists(path):
        return path
    import httpx  # lazy: keeps the ffmpeg helpers importable without httpx
    own = http is None
    http = http or httpx.AsyncClient(timeout=60, follow_redirects=True)
    try:
        size = 0
        async with http.stream("GET", url) as r:
            r.raise_for_status()
            with open(path + ".part", "wb") as f:
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("file too large")
                    f.write(chunk)
        os.replace(path + ".part", path)
    finally:
        if own:
            await http.aclose()
    return path


async def cut_clip(src: str, seconds: int, out: str, start: float = 0) -> bool:
    code, _ = await run("ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", src, "-t", str(seconds),
                        "-vn", "-c:a", "libmp3lame", "-q:a", "5", out)
    return code == 0 and os.path.exists(out)


async def embed_lyrics(src: str, out: str, title: str, artist: str, lyrics: str) -> bool:
    """Writes plain lyrics into the ID3 'lyrics' (USLT) tag with ffmpeg - no extra Python deps."""
    code, _ = await run("ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:a", "-c", "copy", "-id3v2_version", "3",
                        "-metadata", f"title={title}", "-metadata", f"artist={artist}",
                        "-metadata", f"lyrics={lyrics}", out)
    return code == 0 and os.path.exists(out)


def reel_filter(lines: list[tuple[float, float, str]], font: str, tmpdir: str) -> str:
    parts = []
    for n, (a, b, txt) in enumerate(lines):
        fn = f"l{n}.txt"
        with open(os.path.join(tmpdir, fn), "w", encoding="utf-8") as f:
            f.write(txt)
        parts.append(f"drawtext=fontfile={font}:textfile={fn}:fontsize=52:fontcolor=white:"
                     f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{a:.2f},{b:.2f})'")
    return ",".join(parts) or "null"


async def make_reel(src: str, start: float, dur: float, lines: list[tuple[float, str]], font: str, out: str) -> bool:
    """Vertical 720x1280 lyric video. `lines` = (absolute_seconds, text); only the clip window is used.
    Only call this for tracks whose licence permits derivative/remix use (e.g. CC BY / CC BY-SA)."""
    window = [(max(0.0, t - start), (lines[i + 1][0] if i + 1 < len(lines) else start + dur) - start, s)
              for i, (t, s) in enumerate(lines) if start <= t < start + dur]
    with tempfile.TemporaryDirectory() as td:
        vf = reel_filter(window, font, td)
        code, log = await run("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                              f"color=c=0x0d1b1e:s=720x1280:d={dur}", "-ss", str(start), "-i", src, "-t", str(dur),
                              "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out,
                              cwd=td)
    return code == 0 and os.path.exists(out)
