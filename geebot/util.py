import time
from datetime import datetime, timedelta, timezone


def local_now(tz_min: int = 330) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=tz_min)


def today(tz_min: int = 330) -> str:
    return local_now(tz_min).strftime("%Y-%m-%d")


def to_utc_ts(local_str: str, tz_min: int = 330) -> int | None:
    """'YYYY-MM-DD HH:MM' in local time -> unix ts (UTC)."""
    try:
        d = datetime.strptime(local_str.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return int((d - timedelta(minutes=tz_min)).replace(tzinfo=timezone.utc).timestamp())


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_dur(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def now() -> int:
    return int(time.time())
