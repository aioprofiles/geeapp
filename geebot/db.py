import json
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict, fields

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, lang TEXT DEFAULT 'si',
  premium_until INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, best_streak INTEGER DEFAULT 0,
  last_heardle_day TEXT DEFAULT '', banned INTEGER DEFAULT 0, role TEXT DEFAULT '', created INTEGER);
CREATE INDEX IF NOT EXISTS ix_users_name ON users(username);
CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT DEFAULT '',
  duration INTEGER DEFAULT 0, audio_url TEXT DEFAULT '', image TEXT DEFAULT '', license TEXT DEFAULT '',
  source TEXT DEFAULT 'local', video_id TEXT DEFAULT '', tags TEXT DEFAULT '', lrc TEXT DEFAULT '',
  plain TEXT DEFAULT '', year INTEGER DEFAULT 0, downloadable INTEGER DEFAULT 0, audio_file_id TEXT DEFAULT '',
  uploader INTEGER DEFAULT 0, takedown INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS favs(user_id INTEGER, track_id TEXT, ts INTEGER, PRIMARY KEY(user_id, track_id));
CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT);
CREATE TABLE IF NOT EXISTS pl_items(pl_id INTEGER, track_id TEXT, ts INTEGER, PRIMARY KEY(pl_id, track_id));
CREATE TABLE IF NOT EXISTS history(user_id INTEGER, track_id TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS ix_hist ON history(user_id, ts);
CREATE TABLE IF NOT EXISTS downloads(user_id INTEGER, day TEXT, track_id TEXT);
CREATE TABLE IF NOT EXISTS dedications(id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_username TEXT,
  track_id TEXT, note TEXT, anonymous INTEGER DEFAULT 0, send_at INTEGER, sent INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS diary(user_id INTEGER, track_id TEXT, note TEXT, ts INTEGER, remind_at INTEGER, reminded INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contribs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, track_id TEXT, lrc TEXT,
  status TEXT DEFAULT 'pending', ts INTEGER);
CREATE TABLE IF NOT EXISTS badges(user_id INTEGER, badge TEXT, ts INTEGER, PRIMARY KEY(user_id, badge));
CREATE TABLE IF NOT EXISTS scores(chat_id INTEGER, user_id INTEGER, name TEXT, game TEXT, points INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS ix_scores ON scores(chat_id, ts);
CREATE TABLE IF NOT EXISTS games(chat_id INTEGER, kind TEXT, state TEXT, updated INTEGER, PRIMARY KEY(chat_id, kind));
CREATE TABLE IF NOT EXISTS heardle(user_id INTEGER, day TEXT, attempts TEXT, done INTEGER DEFAULT 0, won INTEGER DEFAULT 0,
  PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS gsettings(chat_id INTEGER PRIMARY KEY, who TEXT DEFAULT 'all', cooldown INTEGER DEFAULT 0,
  download INTEGER DEFAULT 1, lang TEXT DEFAULT 'si', explicit INTEGER DEFAULT 0, welcome TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS channels(chat_id INTEGER PRIMARY KEY, owner_id INTEGER, hour INTEGER DEFAULT 9, last_day TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT, track_id TEXT, user_id INTEGER, reason TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS tips(track_id TEXT, from_id INTEGER, stars INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, run_at INTEGER, kind TEXT, payload TEXT, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS party(chat_instance TEXT PRIMARY KEY, track_id TEXT, started_at REAL, paused_at REAL, updated INTEGER);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str = ""
    duration: int = 0
    audio_url: str = ""
    image: str = ""
    license: str = ""
    source: str = "local"
    video_id: str = ""
    tags: str = ""
    lrc: str = ""
    plain: str = ""
    year: int = 0
    downloadable: int = 0
    audio_file_id: str = ""
    uploader: int = 0
    takedown: int = 0

    @classmethod
    def from_row(cls, r: dict | None):
        if not r:
            return None
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in r.items() if k in names})


class DB:
    def __init__(self, path: str):
        self.c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(SCHEMA)
        self.lock = threading.Lock()

    def q(self, sql, *a) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.c.execute(sql, a).fetchall()]

    def one(self, sql, *a) -> dict | None:
        rows = self.q(sql, *a)
        return rows[0] if rows else None

    def x(self, sql, *a) -> int:
        with self.lock:
            return self.c.execute(sql, a).lastrowid

    # ---- kv / json state ---------------------------------------------------
    def kv_get(self, k, default=None):
        r = self.one("SELECT v FROM kv WHERE k=?", k)
        return json.loads(r["v"]) if r else default

    def kv_set(self, k, v):
        self.x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, json.dumps(v))

    def kv_del(self, k):
        self.x("DELETE FROM kv WHERE k=?", k)

    def game_get(self, chat_id, kind):
        r = self.one("SELECT state FROM games WHERE chat_id=? AND kind=?", chat_id, kind)
        return json.loads(r["state"]) if r else None

    def game_set(self, chat_id, kind, state):
        self.x("INSERT INTO games VALUES(?,?,?,?) ON CONFLICT(chat_id,kind) DO UPDATE SET state=excluded.state, updated=excluded.updated",
               chat_id, kind, json.dumps(state), int(time.time()))

    def game_end(self, chat_id, kind):
        self.x("DELETE FROM games WHERE chat_id=? AND kind=?", chat_id, kind)

    # ---- users -------------------------------------------------------------
    def touch_user(self, u: dict, lang_hint: str | None = None):
        if not u or u.get("is_bot"):
            return None
        row = self.one("SELECT * FROM users WHERE id=?", u["id"])
        uname = (u.get("username") or "").lower()
        if not row:
            lang = "si" if (lang_hint or u.get("language_code") or "").startswith("si") else \
                   ("ta" if (u.get("language_code") or "").startswith("ta") else
                    ("en" if (u.get("language_code") or "") else "si"))
            self.x("INSERT INTO users(id,username,first_name,lang,created) VALUES(?,?,?,?,?)",
                   u["id"], uname, u.get("first_name", ""), lang, int(time.time()))
        else:
            self.x("UPDATE users SET username=?, first_name=? WHERE id=?", uname, u.get("first_name", ""), u["id"])
        return self.one("SELECT * FROM users WHERE id=?", u["id"])

    def user(self, uid):
        return self.one("SELECT * FROM users WHERE id=?", uid)

    def is_premium(self, uid) -> bool:
        u = self.user(uid)
        return bool(u and u["premium_until"] > time.time())

    def add_premium(self, uid, days):
        u = self.user(uid)
        base = max(int(time.time()), u["premium_until"] if u else 0)
        self.x("UPDATE users SET premium_until=? WHERE id=?", base + days * 86400, uid)

    def give_badge(self, uid, badge) -> bool:
        if self.one("SELECT 1 x FROM badges WHERE user_id=? AND badge=?", uid, badge):
            return False
        self.x("INSERT INTO badges VALUES(?,?,?)", uid, badge, int(time.time()))
        return True

    # ---- tracks ------------------------------------------------------------
    def upsert_track(self, t: Track):
        d = asdict(t)
        cols = ",".join(d)
        ph = ",".join("?" * len(d))
        # never overwrite community/owner lyrics with empty values
        upd = ",".join(f"{k}=CASE WHEN excluded.{k}='' THEN tracks.{k} ELSE excluded.{k} END"
                       if k in ("lrc", "plain", "video_id", "audio_file_id") else f"{k}=excluded.{k}"
                       for k in d if k not in ("id", "takedown"))
        self.x(f"INSERT INTO tracks({cols}) VALUES({ph}) ON CONFLICT(id) DO UPDATE SET {upd}", *d.values())

    def track(self, tid) -> Track | None:
        return Track.from_row(self.one("SELECT * FROM tracks WHERE id=? AND takedown=0", tid))

    def tracks(self, where="1=1", *a, limit=500) -> list[Track]:
        return [Track.from_row(r) for r in self.q(f"SELECT * FROM tracks WHERE takedown=0 AND {where} LIMIT {int(limit)}", *a)]

    # ---- plays / favourites ------------------------------------------------
    def log_play(self, uid, tid):
        self.x("INSERT INTO history VALUES(?,?,?)", uid, tid, int(time.time()))

    def toggle_fav(self, uid, tid) -> bool:
        if self.one("SELECT 1 x FROM favs WHERE user_id=? AND track_id=?", uid, tid):
            self.x("DELETE FROM favs WHERE user_id=? AND track_id=?", uid, tid)
            return False
        self.x("INSERT INTO favs VALUES(?,?,?)", uid, tid, int(time.time()))
        return True

    def is_fav(self, uid, tid) -> bool:
        return bool(self.one("SELECT 1 x FROM favs WHERE user_id=? AND track_id=?", uid, tid))

    # ---- scores ------------------------------------------------------------
    def add_score(self, chat_id, uid, name, game, pts):
        self.x("INSERT INTO scores VALUES(?,?,?,?,?,?)", chat_id, uid, name, game, pts, int(time.time()))

    def leaderboard(self, chat_id=None, since=0, limit=10):
        if chat_id is None:
            return self.q("SELECT user_id, name, SUM(points) p FROM scores WHERE ts>=? GROUP BY user_id ORDER BY p DESC LIMIT ?", since, limit)
        return self.q("SELECT user_id, name, SUM(points) p FROM scores WHERE chat_id=? AND ts>=? GROUP BY user_id ORDER BY p DESC LIMIT ?",
                      chat_id, since, limit)

    # ---- jobs --------------------------------------------------------------
    def add_job(self, run_at, kind, payload):
        return self.x("INSERT INTO jobs(run_at,kind,payload) VALUES(?,?,?)", int(run_at), kind, json.dumps(payload))

    def due_jobs(self):
        return self.q("SELECT * FROM jobs WHERE done=0 AND run_at<=? ORDER BY run_at LIMIT 50", int(time.time()))

    def job_done(self, jid):
        self.x("UPDATE jobs SET done=1 WHERE id=?", jid)

    # ---- group settings ----------------------------------------------------
    def gs(self, chat_id) -> dict:
        r = self.one("SELECT * FROM gsettings WHERE chat_id=?", chat_id)
        if not r:
            self.x("INSERT INTO gsettings(chat_id) VALUES(?)", chat_id)
            r = self.one("SELECT * FROM gsettings WHERE chat_id=?", chat_id)
        return r
