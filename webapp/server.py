"""Mini App backend.  uvicorn webapp.server:app --host 0.0.0.0 --port 8080   (put HTTPS in front: Telegram requires it)
Shares the SQLite file with the bot (WAL mode)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from geebot import lrc, textutil
from geebot.config import Config
from geebot.db import DB
from geebot.webauth import validate_init_data

cfg = Config.from_env()
db = DB(cfg.db_path)
app = FastAPI(title="geebot miniapp")
STATIC = os.path.join(os.path.dirname(__file__), "static")
API = f"https://api.telegram.org/bot{cfg.bot_token}" + ("/test" if cfg.test_env else "")
FILE = f"https://api.telegram.org/file/bot{cfg.bot_token}" + ("/test" if cfg.test_env else "")
_hits: dict[int, list[float]] = {}


def auth(init_data: str) -> dict:
    p = validate_init_data(init_data or "", cfg.bot_token)
    if not p or "user" not in p:
        raise HTTPException(401, "bad initData")
    uid = p["user"]["id"]
    now = time.time()
    h = [x for x in _hits.get(uid, []) if now - x < 60]
    if len(h) >= 20:
        raise HTTPException(429, "slow down")
    _hits[uid] = h + [now]
    return p


@app.get("/app")
async def player():
    return FileResponse(os.path.join(STATIC, "player.html"), headers={"Cache-Control": "no-cache"})


@app.get("/api/track/{tid:path}")
async def track(tid: str):
    t = db.track(tid)
    if not t:
        raise HTTPException(404)
    synced = lrc.parse(t.lrc)
    if synced:
        lines = [{"t": ts, "s": s, "r": textutil.roman(s)} for ts, s in synced]
    else:
        lines = [{"t": None, "s": s, "r": textutil.roman(s)} for s in lrc.plain_lines(t.plain)]
    audio = f"{cfg.webapp_url}/media/{t.id}" if t.audio_file_id else t.audio_url
    return {"id": t.id, "title": t.title, "artist": t.artist, "image": t.image, "duration": t.duration,
            "audio": audio, "video_id": t.video_id, "synced": bool(synced), "lines": lines,
            "license": t.license, "downloadable": bool(t.downloadable)}


@app.get("/media/{tid:path}")
async def media(tid: str, request: Request):
    """Streams an uploaded Telegram file WITHOUT exposing the bot token. Supports Range for seeking."""
    t = db.track(tid)
    if not t or not t.audio_file_id:
        raise HTTPException(404)
    async with httpx.AsyncClient(timeout=20) as c:
        f = (await c.post(f"{API}/getFile", json={"file_id": t.audio_file_id})).json()
    if not f.get("ok"):
        raise HTTPException(502)
    client = httpx.AsyncClient(timeout=60)
    h = {"Range": request.headers["range"]} if "range" in request.headers else {}
    r = await client.send(client.build_request("GET", f"{FILE}/{f['result']['file_path']}", headers=h), stream=True)
    keep = {k: r.headers[k] for k in ("content-type", "content-length", "content-range", "accept-ranges") if k in r.headers}
    async def close():
        await r.aclose()
        await client.aclose()

    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=keep, background=BackgroundTask(close))


# ---- listening party ---------------------------------------------------------------------
def party_view(ci: str) -> dict:
    p = db.one("SELECT * FROM party WHERE chat_instance=?", ci)
    if not p:
        return {"track_id": None, "pos": 0, "paused": True}
    paused = p["paused_at"] is not None
    pos = (p["paused_at"] if paused else time.time()) - p["started_at"]
    return {"track_id": p["track_id"], "pos": max(0.0, pos), "paused": paused}


@app.get("/api/party/{ci}")
async def party_get(ci: str):
    return party_view(ci)


@app.post("/api/party")
async def party_set(body: dict):
    p = auth(body.get("initData"))
    ci = p.get("chat_instance")
    if not ci:
        raise HTTPException(400, "open the player from a group")
    cur = party_view(ci)
    action, now = body.get("action"), time.time()
    pos = float(body.get("pos", cur["pos"]) or 0)
    if action == "track" and db.track(str(body.get("track_id"))):
        db.x("INSERT INTO party VALUES(?,?,?,?,?) ON CONFLICT(chat_instance) DO UPDATE SET track_id=excluded.track_id, "
             "started_at=excluded.started_at, paused_at=NULL, updated=excluded.updated", ci, body["track_id"], now, None, int(now))
    elif action in ("play", "seek", "pause") and cur["track_id"]:
        paused = action == "pause" or (action == "seek" and cur["paused"])
        db.x("UPDATE party SET started_at=?, paused_at=?, updated=? WHERE chat_instance=?",
             now - pos, now if paused else None, int(now), ci)
    return party_view(ci)


# ---- community lyric timing --------------------------------------------------------------
@app.post("/api/sync")
async def sync_submit(body: dict):
    p = auth(body.get("initData"))
    t = db.track(str(body.get("track_id")))
    raw = body.get("lines")
    if not t or not isinstance(raw, list) or not 3 <= len(raw) <= 400:
        raise HTTPException(400, "bad payload")
    lines, last = [], -1.0
    for item in raw:
        try:
            ts, txt = float(item[0]), str(item[1])[:200]
        except (TypeError, ValueError, IndexError):
            raise HTTPException(400, "bad line")
        if ts < last or ts > (t.duration or 7200) + 5:
            raise HTTPException(400, "timestamps must increase and fit the song")
        last = ts
        lines.append((ts, txt))
    cid = db.x("INSERT INTO contribs(user_id,track_id,lrc,ts) VALUES(?,?,?,?)", p["user"]["id"], t.id, lrc.dumps(lines), int(time.time()))
    async with httpx.AsyncClient(timeout=10) as c:
        for o in cfg.owner_ids:
            await c.post(f"{API}/sendMessage", json={"chat_id": o, "text": f"⏳ new lyric timing #{cid} for {t.id} (/contribs)"})
    return JSONResponse({"ok": True, "id": cid})
