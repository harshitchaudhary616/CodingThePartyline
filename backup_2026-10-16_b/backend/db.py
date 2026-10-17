"""SQLite storage (WAL, per-call connections, foreign keys). Stores datasets, raw positions and runs."""
import gzip, json, os, sqlite3, time, threading
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source TEXT NOT NULL,
  is_real INTEGER NOT NULL, bbox TEXT, created REAL NOT NULL, n_rows INTEGER NOT NULL DEFAULT 0,
  t_min REAL, t_max REAL, status TEXT NOT NULL DEFAULT 'ready', note TEXT);
CREATE TABLE IF NOT EXISTS positions(
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  ts REAL NOT NULL, icao24 TEXT NOT NULL, callsign TEXT, lat REAL NOT NULL, lon REAL NOT NULL,
  alt REAL, onground INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_pos ON positions(dataset_id, icao24, ts);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id INTEGER, created REAL NOT NULL, params TEXT NOT NULL,
  summary TEXT NOT NULL, payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, dataset_id INTEGER, state TEXT NOT NULL,
  started REAL NOT NULL, finished REAL, polls INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
  rows INTEGER DEFAULT 0, message TEXT);
"""

_lock = threading.Lock()


class DB:
    def __init__(self, path):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ---- datasets
    def create_dataset(self, name, source, is_real, bbox=None, status="ready", note=None):
        with _lock, self.conn() as c:
            cur = c.execute("INSERT INTO datasets(name,source,is_real,bbox,created,status,note) VALUES(?,?,?,?,?,?,?)",
                            (name, source, int(is_real), json.dumps(bbox) if bbox else None, time.time(), status, note))
            return cur.lastrowid

    def add_positions(self, dataset_id, rows):
        """rows: (ts, icao24, callsign, lat, lon, alt, onground)"""
        rows = list(rows)
        if not rows:
            return 0
        with _lock, self.conn() as c:
            c.executemany("INSERT INTO positions VALUES(?,?,?,?,?,?,?,?)", [(dataset_id, *r) for r in rows])
            c.execute("""UPDATE datasets SET n_rows=(SELECT COUNT(*) FROM positions WHERE dataset_id=?),
                         t_min=(SELECT MIN(ts) FROM positions WHERE dataset_id=?),
                         t_max=(SELECT MAX(ts) FROM positions WHERE dataset_id=?) WHERE id=?""",
                      (dataset_id, dataset_id, dataset_id, dataset_id))
        return len(rows)

    def set_dataset_status(self, dataset_id, status, note=None):
        with _lock, self.conn() as c:
            c.execute("UPDATE datasets SET status=?, note=COALESCE(?,note) WHERE id=?", (status, note, dataset_id))

    def datasets(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM datasets ORDER BY id DESC")]

    def dataset(self, did):
        with self.conn() as c:
            r = c.execute("SELECT * FROM datasets WHERE id=?", (did,)).fetchone()
            return dict(r) if r else None

    def delete_dataset(self, did):
        with _lock, self.conn() as c:
            c.execute("DELETE FROM datasets WHERE id=?", (did,))
            c.execute("DELETE FROM runs WHERE dataset_id=?", (did,))

    def tracks(self, did, t_from=None, t_to=None):
        q = "SELECT ts, icao24, lat, lon, alt, onground FROM positions WHERE dataset_id=?"
        a = [did]
        if t_from is not None:
            q += " AND ts>=?"; a.append(t_from)
        if t_to is not None:
            q += " AND ts<=?"; a.append(t_to)
        with self.conn() as c:
            return [tuple(r) for r in c.execute(q + " ORDER BY icao24, ts", a)]

    # ---- runs
    def save_run(self, dataset_id, params, summary, payload):
        blob = gzip.compress(json.dumps(payload, separators=(",", ":")).encode())
        with _lock, self.conn() as c:
            cur = c.execute("INSERT INTO runs(dataset_id,created,params,summary,payload) VALUES(?,?,?,?,?)",
                            (dataset_id, time.time(), json.dumps(params), json.dumps(summary), blob))
            return cur.lastrowid

    def run(self, rid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["payload"] = json.loads(gzip.decompress(d["payload"]))
        d["params"] = json.loads(d["params"]); d["summary"] = json.loads(d["summary"])
        return d

    def runs(self, limit=30):
        with self.conn() as c:
            return [dict(id=r["id"], dataset_id=r["dataset_id"], created=r["created"], summary=json.loads(r["summary"]))
                    for r in c.execute("SELECT id,dataset_id,created,summary FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- jobs
    def create_job(self, kind, dataset_id):
        with _lock, self.conn() as c:
            return c.execute("INSERT INTO jobs(kind,dataset_id,state,started) VALUES(?,?,?,?)",
                             (kind, dataset_id, "running", time.time())).lastrowid

    def update_job(self, jid, **kw):
        if not kw:
            return
        cols = ",".join(f"{k}=?" for k in kw)
        with _lock, self.conn() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*kw.values(), jid))

    def job(self, jid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            return dict(r) if r else None

    def mark_stale_jobs(self):
        """On start-up: jobs left 'running' by a crash/restart are marked failed, their datasets 'partial'."""
        with _lock, self.conn() as c:
            c.execute("UPDATE jobs SET state='failed', finished=?, message='interrupted by restart' WHERE state='running'", (time.time(),))
            c.execute("UPDATE datasets SET status='partial' WHERE status='recording'")
