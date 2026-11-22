import os
from dataclasses import dataclass, field


def _ids(s: str) -> set[int]:
    return {int(x) for x in s.split(",") if x.strip().lstrip("-").isdigit()}


@dataclass
class Config:
    bot_token: str = ""
    bot_username: str = ""
    owner_ids: set[int] = field(default_factory=set)
    webapp_url: str = ""
    app_short: str = "player"
    test_env: bool = False
    db_path: str = "geebot.sqlite"
    media_dir: str = "media"
    jamendo_client_id: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    use_lrclib: bool = False
    font_file: str = ""
    tz_offset_min: int = 330
    free_dl_per_day: int = 3
    premium_stars_30d: int = 150
    backup_chat_id: int = 0
    backup_every_min: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        return cls(
            bot_token=e("BOT_TOKEN", ""),
            bot_username=e("BOT_USERNAME", "").lstrip("@"),
            owner_ids=_ids(e("OWNER_IDS", "")),
            webapp_url=e("WEBAPP_URL", "").rstrip("/"),
            app_short=e("APP_SHORT", "player"),
            test_env=e("TEST_ENV", "0") == "1",
            db_path=e("DB_PATH", "geebot.sqlite"),
            media_dir=e("MEDIA_DIR", "media"),
            jamendo_client_id=e("JAMENDO_CLIENT_ID", ""),
            anthropic_model=e("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            use_lrclib=e("USE_LRCLIB", "0") == "1",
            font_file=e("FONT_FILE", ""),
            tz_offset_min=int(e("TZ_OFFSET_MIN", "330")),
            free_dl_per_day=int(e("FREE_DL_PER_DAY", "3")),
            premium_stars_30d=int(e("PREMIUM_STARS_30D", "150")),
            backup_chat_id=int(e("BACKUP_CHAT_ID", "0") or 0),
            backup_every_min=int(e("BACKUP_EVERY_MIN", "5")),
        )
