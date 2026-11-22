from .db import DB


def open_db(cfg):
    """DATABASE_URL (Supabase/Neon Postgres) when set, otherwise the local SQLite file."""
    if getattr(cfg, "database_url", ""):
        from .pgdb import PgDB
        return PgDB(cfg.database_url)
    return DB(cfg.db_path)
