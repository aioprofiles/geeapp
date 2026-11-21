"""Shared context + small helpers used by every handler module."""
import time
from dataclasses import dataclass, field

from .config import Config
from .db import DB, Track
from .i18n import t as _t
from .llm import LLM
from .sources import Jamendo, Lrclib
from .tg import Tg


@dataclass
class Ctx:
    cfg: Config
    db: DB
    tg: Tg
    llm: LLM
    jamendo: Jamendo
    lrclib: Lrclib
    last_cmd: dict = field(default_factory=dict)     # (chat,user) -> ts, for cooldowns

    def lang(self, uid: int) -> str:
        u = self.db.user(uid)
        return u["lang"] if u else "si"

    def tr(self, uid: int, key: str, **kw) -> str:
        return _t(self.lang(uid), key, **kw)

    def is_owner(self, uid: int) -> bool:
        return uid in self.cfg.owner_ids

    def is_artist(self, uid: int) -> bool:
        u = self.db.user(uid)
        return bool(u and u["role"] == "artist") or self.is_owner(uid)

    async def is_chat_admin(self, chat_id: int, uid: int) -> bool:
        if self.is_owner(uid):
            return True
        m = await self.tg.try_call("getChatMember", chat_id=chat_id, user_id=uid)
        return bool(m and m.get("status") in ("creator", "administrator"))

    async def gate(self, msg: dict) -> bool:
        """Group permission + cooldown. Returns True when the command may run."""
        chat, user = msg["chat"], msg.get("from") or {}
        if chat["type"] == "private":
            return True
        gs = self.db.gs(chat["id"])
        if gs["who"] == "admins" and not await self.is_chat_admin(chat["id"], user["id"]):
            await self.tg.try_call("sendMessage", chat_id=chat["id"], text=self.tr(user["id"], "admins_only"))
            return False
        if gs["cooldown"]:
            k, now = (chat["id"], user["id"]), time.time()
            left = gs["cooldown"] - (now - self.last_cmd.get(k, 0))
            if left > 0:
                await self.tg.try_call("sendMessage", chat_id=chat["id"], text=self.tr(user["id"], "cooldown", s=int(left) + 1))
                return False
            self.last_cmd[k] = now
        return True


def display_name(u: dict) -> str:
    return u.get("first_name") or u.get("username") or str(u.get("id"))


def arg_text(text: str) -> str:
    parts = (text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def pick_audio_track(db: DB, rng, need_clip: bool = True) -> Track | None:
    pool = [t for t in db.tracks(limit=2000) if t.audio_url or t.audio_file_id]
    return rng.choice(pool) if pool else None
