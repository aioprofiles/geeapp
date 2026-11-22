import asyncio, gzip, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.fakes import FakeTg
from geebot import backup
from geebot.app import Ctx
from geebot.config import Config
from geebot.db import DB, SCHEMA, Track
from geebot.llm import LLM
from geebot.pgdb import translate_schema, translate_sql
from geebot.sources import Jamendo, Lrclib


class Translator(unittest.TestCase):
    def test_placeholders_and_ignore_and_rowid(self):
        self.assertEqual(translate_sql("SELECT * FROM t WHERE a=? AND b=?"), "SELECT * FROM t WHERE a=%s AND b=%s")
        self.assertEqual(translate_sql("INSERT OR IGNORE INTO pl_items VALUES(?,?,?)"),
                         "INSERT INTO pl_items VALUES(%s,%s,%s) ON CONFLICT DO NOTHING")
        self.assertEqual(translate_sql("UPDATE diary SET reminded=1 WHERE rowid=?"), "UPDATE diary SET reminded=1 WHERE id=%s")
        with self.assertRaises(ValueError): translate_sql("SELECT * FROM t WHERE n LIKE '%x'")

    def test_schema_conversion(self):
        stmts = translate_schema(SCHEMA)
        txt = "\n".join(stmts)
        self.assertNotIn("INTEGER", txt); self.assertNotIn("AUTOINCREMENT", txt); self.assertNotIn(" REAL", txt)
        self.assertIn("playlists(id BIGSERIAL PRIMARY KEY", txt); self.assertIn("started_at DOUBLE PRECISION", txt)
        self.assertIn("id BIGINT PRIMARY KEY", txt)                                   # telegram ids need 64-bit
        self.assertTrue(all(s.upper().startswith(("CREATE TABLE", "CREATE INDEX")) for s in stmts))
        self.assertGreater(len(stmts), 20)

    def test_all_sql_in_codebase_translates(self):
        import re, glob
        bad = []
        for f in glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)), "geebot", "*.py")):
            for sql in re.findall(r'\.(?:q|one|x)\(\s*f?"((?:SELECT|INSERT|UPDATE|DELETE)[^"]*)"', open(f, encoding="utf-8").read()):
                try: translate_sql(sql.replace("{", "").replace("}", ""))
                except ValueError: bad.append((f, sql))
        self.assertEqual(bad, [])

    def test_no_sqlite_only_constructs_left(self):
        import glob
        for f in glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)), "geebot", "*.py")):
            if f.endswith(("db.py", "pgdb.py")): continue
            t = open(f, encoding="utf-8").read()
            self.assertNotIn("SELECT DISTINCT track_id", t, f); self.assertNotIn("=MAX(", t, f)


class Export(unittest.TestCase):
    def test_pg_style_export_roundtrips(self):
        d = tempfile.mkdtemp(); db = DB(os.path.join(d, "a.sqlite")); db.upsert_track(Track("x", "සින්දුව", "a"))
        db.touch_user({"id": 1, "first_name": "A"})
        data = json.loads(gzip.decompress(backup.export_tables(db)))
        self.assertEqual(data["tracks"][0]["title"], "සින්දුව"); self.assertEqual(data["users"][0]["id"], 1)

    def test_backup_once_in_pg_mode_sends_export_and_skips_restore(self):
        d = tempfile.mkdtemp(); db = DB(os.path.join(d, "a.sqlite")); tg = FakeTg(); backup._state.update(msg=None, sig=None)
        cfg = Config(bot_token="1:T", db_path=os.path.join(d, "a.sqlite"), backup_chat_id=5, database_url="postgresql://x")
        self.assertTrue(asyncio.run(backup.backup_once(Ctx(cfg, db, tg, LLM("x"), Jamendo(""), Lrclib()))))
        up = [a for n, a, k in tg.log if n == "upload"][0]; self.assertEqual(up[2], backup.PG_NAME)
        self.assertFalse(backup.restore_sync(cfg, http=object()))                      # never restore SQLite in PG mode


if __name__ == "__main__":
    unittest.main()
