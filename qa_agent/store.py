import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "qa.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT, updated TEXT, status TEXT, stage TEXT, request TEXT, summary TEXT);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, at TEXT, stage TEXT, message TEXT);
                CREATE TABLE IF NOT EXISTS fingerprints(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES(1);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='interrupted', updated=? WHERE status IN ('queued','running')", (now(),))

    def create(self, request):
        rid = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (rid, now(), now(), "queued", "queued", json.dumps(request), "{}"))
        (self.root / rid).mkdir()
        return rid

    def update(self, rid, status=None, stage=None, summary=None):
        updates = {"updated": now()}
        if status is not None: updates["status"] = status
        if stage is not None: updates["stage"] = stage
        if summary is not None: updates["summary"] = json.dumps(summary)
        with self.connect() as db:
            db.execute("UPDATE runs SET " + ",".join(f"{k}=?" for k in updates) + " WHERE id=?", [*updates.values(), rid])

    def event(self, rid, stage, message):
        with self.connect() as db:
            db.execute("INSERT INTO events(run_id,at,stage,message) VALUES(?,?,?,?)", (rid, now(), stage, message))

    def get(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if not row: return None
        value = dict(row)
        for key in ("request", "summary"): value[key] = json.loads(value[key])
        return value

    def list(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM runs ORDER BY created DESC LIMIT 100")]
        return [self.get(rid) for rid in ids]

    def events(self, rid):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (rid,))]

    def artifact(self, rid, name, value):
        path = self.root / rid / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)

    def read(self, rid, name, default=None):
        path = self.root / rid / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def fingerprint(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO fingerprints VALUES(?,?)", (key, json.dumps(value)))
                return value
            row = db.execute("SELECT value FROM fingerprints WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
