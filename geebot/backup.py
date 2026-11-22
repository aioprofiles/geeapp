"""SQLite survives Render's ephemeral disk by living in Telegram: every few minutes the DB is snapshotted, gzipped and
sent to BACKUP_CHAT_ID as a *pinned* document; on boot, if the DB file is missing, the pinned backup is downloaded.
Limits: Bot API getFile downloads max 20 MB (compressed DB must stay below that); you can lose up to
BACKUP_EVERY_MIN minutes of data on a hard crash (a SIGTERM shutdown does one last backup)."""
import asyncio
import gzip
import logging
import os
import sqlite3
import tempfile
import time

log = logging.getLogger("backup")
NAME = "geebot-backup.sqlite.gz"
MAX_UPLOAD = 45 * 1024 * 1024
_state: dict = {"msg": None, "sig": None}


def snapshot(db_path: str) -> bytes:
    """Consistent copy using SQLite's online backup API (safe while the bot is writing)."""
    fd, tmp = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        src, dst = sqlite3.connect(db_path), sqlite3.connect(tmp)
        src.backup(dst)
        dst.close(); src.close()
        with open(tmp, "rb") as f:
            return gzip.compress(f.read(), 6)
    finally:
        os.remove(tmp)


def _sig(db_path: str) -> tuple:
    """(mtime_ns, size) of the DB and its WAL: changes whenever anything is written."""
    out = []
    for p in (db_path, db_path + "-wal"):
        st = os.stat(p) if os.path.exists(p) else None
        out.append((st.st_mtime_ns, st.st_size) if st else None)
    return tuple(out)


def restore_sync(cfg, http=None) -> bool:
    """Call BEFORE the DB is opened. Returns True if a backup was restored."""
    if (os.path.exists(cfg.db_path) and os.path.getsize(cfg.db_path) > 0) or not (cfg.backup_chat_id and cfg.bot_token):
        return False
    if http is None:
        import httpx
        http = httpx.Client(timeout=60, follow_redirects=True)
    t = "/test" if cfg.test_env else ""
    base, fbase = f"https://api.telegram.org/bot{cfg.bot_token}{t}", f"https://api.telegram.org/file/bot{cfg.bot_token}{t}"
    try:
        doc = ((http.post(f"{base}/getChat", json={"chat_id": cfg.backup_chat_id}).json().get("result") or {})
               .get("pinned_message") or {}).get("document")
        if not doc or doc.get("file_name") != NAME:
            log.info("no backup found")
            return False
        path = http.post(f"{base}/getFile", json={"file_id": doc["file_id"]}).json()["result"]["file_path"]
        raw = gzip.decompress(http.get(f"{fbase}/{path}").content)
    except Exception as e:
        log.warning("restore failed: %s", e)
        return False
    os.makedirs(os.path.dirname(os.path.abspath(cfg.db_path)), exist_ok=True)
    tmp = cfg.db_path + ".restore"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, cfg.db_path)
    log.info("database restored from Telegram backup (%d bytes)", len(raw))
    return True


async def backup_once(ctx, force: bool = False) -> bool:
    cfg = ctx.cfg
    if not cfg.backup_chat_id or not os.path.exists(cfg.db_path):
        return False
    sig = _sig(cfg.db_path)                 # taken BEFORE the snapshot: later writes still count as changes
    if not force and sig == _state["sig"]:
        return False
    data = await asyncio.to_thread(snapshot, cfg.db_path)
    if len(data) > MAX_UPLOAD:
        log.error("backup too large (%d bytes) - move to a real database", len(data))
        return False
    if _state["msg"] is None:  # first run after a restart: remember the previous pinned backup so we can delete it
        info = await ctx.tg.try_call("getChat", chat_id=cfg.backup_chat_id)
        _state["msg"] = ((info or {}).get("pinned_message") or {}).get("message_id")
    m = await ctx.tg.upload("sendDocument", "document", NAME, data, "application/gzip", chat_id=cfg.backup_chat_id,
                            caption=time.strftime("backup %Y-%m-%d %H:%M UTC", time.gmtime()), disable_notification=True)
    await ctx.tg.try_call("pinChatMessage", chat_id=cfg.backup_chat_id, message_id=m["message_id"], disable_notification=True)
    if _state["msg"]:
        await ctx.tg.try_call("deleteMessage", chat_id=cfg.backup_chat_id, message_id=_state["msg"])
    _state.update(msg=m["message_id"], sig=sig)
    return True


async def loop(ctx):
    while True:
        await asyncio.sleep(max(60, ctx.cfg.backup_every_min * 60))
        try:
            await backup_once(ctx)
        except Exception:
            log.exception("backup failed")
