"""One process for Render's free tier:  uvicorn geebot.serve:app --host 0.0.0.0 --port $PORT
Mini App API + bot long-polling + scheduler + Telegram backups share a single free web service
(free tier = 750 instance-hours/month per workspace, i.e. one always-on service)."""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from geebot import backup  # noqa: E402
from geebot.config import Config  # noqa: E402

cfg = Config.from_env()
backup.restore_sync(cfg)                       # must happen before the DB file is opened

from fastapi import FastAPI  # noqa: E402
from geebot import commands, main as bot_main, sched  # noqa: E402
from webapp import server  # noqa: E402       (opens the SQLite file)


@asynccontextmanager
async def lifespan(app):
    ctx = bot_main.build_ctx(cfg, db=server.db)
    tasks = [asyncio.create_task(commands.install(ctx.tg)), asyncio.create_task(bot_main.poll(ctx)), asyncio.create_task(sched.loop(ctx)),
             asyncio.create_task(backup.loop(ctx))]
    try:
        yield
    finally:                                     # SIGTERM on redeploy / spin-down: one last backup
        for t in tasks:
            t.cancel()
        try:
            await asyncio.wait_for(backup.backup_once(ctx, force=True), 20)
        except Exception:
            logging.getLogger("serve").exception("final backup failed")


app = FastAPI(title="geebot", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.mount("/", server.app)
