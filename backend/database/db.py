"""
MegaDL — database/db.py
SQLite database with schema for jobs, history, archive, favorites, settings, logs.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from contextlib import contextmanager

logger = logging.getLogger('megadl.db')


class Database:
    """Thread-safe SQLite wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @contextmanager
    def conn(self):
        """Context manager for a database connection."""
        con = sqlite3.connect(str(self.db_path), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        """Create all tables if they don't exist."""
        with self.conn() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id           TEXT PRIMARY KEY,
                    url          TEXT NOT NULL,
                    title        TEXT,
                    thumbnail    TEXT,
                    uploader     TEXT,
                    duration     REAL,
                    resolution   TEXT,
                    state        TEXT NOT NULL DEFAULT 'queued',
                    progress     REAL DEFAULT 0,
                    speed        REAL DEFAULT 0,
                    eta          REAL DEFAULT 0,
                    total_bytes  INTEGER DEFAULT 0,
                    downloaded   INTEGER DEFAULT 0,
                    fragment     TEXT,
                    error        TEXT,
                    options      TEXT,
                    output_path  TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    pid          INTEGER
                );

                CREATE TABLE IF NOT EXISTS history (
                    id          TEXT PRIMARY KEY,
                    job_id      TEXT,
                    url         TEXT NOT NULL,
                    title       TEXT,
                    thumbnail   TEXT,
                    state       TEXT,
                    output_path TEXT,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS archive (
                    id         TEXT PRIMARY KEY,
                    extractor  TEXT,
                    title      TEXT,
                    ts         TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    id         TEXT PRIMARY KEY,
                    job_id     TEXT,
                    url        TEXT,
                    title      TEXT,
                    thumbnail  TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    level    TEXT NOT NULL DEFAULT 'info',
                    message  TEXT NOT NULL,
                    job_id   TEXT,
                    time     TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_state      ON jobs(state);
                CREATE INDEX IF NOT EXISTS idx_jobs_created    ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_created    ON logs(time DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_job        ON logs(job_id);

                CREATE TABLE IF NOT EXISTS telegram_sessions (
                    id         TEXT PRIMARY KEY,
                    phone      TEXT,
                    user_id    INTEGER,
                    username   TEXT,
                    first_name TEXT,
                    last_name  TEXT,
                    session    TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS failed_links (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id     TEXT,
                    url        TEXT NOT NULL,
                    error      TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dependencies (
                    name       TEXT PRIMARY KEY,
                    installed  INTEGER DEFAULT 0,
                    version    TEXT,
                    checked_at TEXT
                );
            """)
        logger.info('Database initialized')

    # ── Job methods ──────────────────────────────────────────

    def create_job(self, job: dict) -> dict:
        with self._lock, self.conn() as con:
            now = _now()
            con.execute("""
                INSERT INTO jobs (id, url, title, thumbnail, uploader, duration,
                    resolution, state, progress, options, created_at, updated_at)
                VALUES (:id, :url, :title, :thumbnail, :uploader, :duration,
                    :resolution, :state, 0, :options, :created_at, :updated_at)
            """, {
                'id':          job['id'],
                'url':         job['url'],
                'title':       job.get('title', ''),
                'thumbnail':   job.get('thumbnail', ''),
                'uploader':    job.get('uploader', ''),
                'duration':    job.get('duration', 0),
                'resolution':  job.get('resolution', ''),
                'state':       job.get('state', 'queued'),
                'options':     json.dumps(job.get('options', {})),
                'created_at':  now,
                'updated_at':  now,
            })
        return self.get_job(job['id'])

    def get_job(self, job_id: str) -> dict | None:
        with self.conn() as con:
            row = con.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
            return _row_to_dict(row) if row else None

    def get_jobs(self, state_filter: str = None, limit: int = 200,
                 sort: str = 'date_desc', q: str = None) -> list:
        clauses, params = [], []

        if state_filter and state_filter != 'all':
            if state_filter == 'done':
                clauses.append("state = 'done'")
            elif state_filter == 'error':
                clauses.append("state = 'error'")
            elif state_filter == 'video':
                clauses.append("(resolution != '' OR resolution IS NOT NULL)")
            else:
                clauses.append('state = ?')
                params.append(state_filter)

        if q:
            clauses.append('(title LIKE ? OR url LIKE ?)')
            like = f'%{q}%'
            params.extend([like, like])

        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''

        order_map = {
            'date_desc': 'created_at DESC',
            'date_asc':  'created_at ASC',
            'name_asc':  'title ASC',
            'size_desc': 'total_bytes DESC',
        }
        order = order_map.get(sort, 'created_at DESC')

        with self.conn() as con:
            rows = con.execute(
                f'SELECT * FROM jobs {where} ORDER BY {order} LIMIT ?',
                params + [limit]
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_active_jobs(self) -> list:
        with self.conn() as con:
            rows = con.execute(
                "SELECT * FROM jobs WHERE state IN ('queued','fetching','running','paused') ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def update_job(self, job_id: str, fields: dict):
        fields['updated_at'] = _now()
        # Serialize dict/list values to JSON for SQLite binding
        for k, v in fields.items():
            if isinstance(v, (dict, list)):
                fields[k] = json.dumps(v)
        cols = ', '.join(f'{k} = :{k}' for k in fields)
        fields['id'] = job_id
        with self._lock, self.conn() as con:
            con.execute(f'UPDATE jobs SET {cols} WHERE id = :id', fields)

    def delete_job(self, job_id: str):
        with self._lock, self.conn() as con:
            con.execute('DELETE FROM jobs WHERE id = ?', (job_id,))

    # ── History methods ──────────────────────────────────────

    def add_history(self, job: dict):
        with self._lock, self.conn() as con:
            import uuid
            con.execute("""
                INSERT OR REPLACE INTO history
                (id, job_id, url, title, thumbnail, state, output_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), job.get('id', ''),
                job.get('url', ''), job.get('title', ''),
                job.get('thumbnail', ''), job.get('state', ''),
                job.get('output_path', ''), _now()
            ))

    def get_history(self, limit: int = 100) -> list:
        with self.conn() as con:
            rows = con.execute(
                'SELECT * FROM history ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def clear_history(self):
        with self._lock, self.conn() as con:
            con.execute('DELETE FROM history')

    # ── Archive methods ──────────────────────────────────────

    def add_archive(self, extractor: str, video_id: str, title: str = ''):
        with self._lock, self.conn() as con:
            con.execute(
                'INSERT OR IGNORE INTO archive (id, extractor, title, ts) VALUES (?, ?, ?, ?)',
                (video_id, extractor, title, _now())
            )

    def get_archive(self) -> list:
        with self.conn() as con:
            rows = con.execute('SELECT * FROM archive ORDER BY ts DESC').fetchall()
        return [_row_to_dict(r) for r in rows]

    def clear_archive(self):
        with self._lock, self.conn() as con:
            con.execute('DELETE FROM archive')

    # ── Favorites methods ────────────────────────────────────

    def add_favorite(self, job: dict):
        with self._lock, self.conn() as con:
            import uuid
            con.execute("""
                INSERT OR IGNORE INTO favorites
                (id, job_id, url, title, thumbnail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), job.get('id', ''),
                job.get('url', ''), job.get('title', ''),
                job.get('thumbnail', ''), _now()
            ))

    def remove_favorite(self, job_id: str):
        with self._lock, self.conn() as con:
            con.execute('DELETE FROM favorites WHERE job_id = ?', (job_id,))

    def get_favorites(self) -> list:
        with self.conn() as con:
            rows = con.execute('SELECT * FROM favorites ORDER BY created_at DESC').fetchall()
        return [_row_to_dict(r) for r in rows]

    # ── Settings methods ─────────────────────────────────────

    def get_settings(self) -> dict:
        with self.conn() as con:
            rows = con.execute('SELECT key, value FROM settings').fetchall()
        result = {}
        for row in rows:
            try: result[row['key']] = json.loads(row['value'])
            except (json.JSONDecodeError, TypeError): result[row['key']] = row['value']
        return result

    def save_settings(self, settings: dict):
        with self._lock, self.conn() as con:
            for k, v in settings.items():
                con.execute(
                    'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                    (k, json.dumps(v))
                )

    # ── Log methods ──────────────────────────────────────────

    def add_log(self, message: str, level: str = 'info', job_id: str = None):
        with self._lock, self.conn() as con:
            con.execute(
                'INSERT INTO logs (level, message, job_id, time) VALUES (?, ?, ?, ?)',
                (level, message, job_id, _now_time())
            )

    def get_logs(self, level: str = None, limit: int = 500, job_id: str = None) -> list:
        clauses, params = [], []
        if level and level != 'all':
            clauses.append('level = ?')
            params.append(level)
        if job_id:
            clauses.append('job_id = ?')
            params.append(job_id)
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        with self.conn() as con:
            rows = con.execute(
                f'SELECT * FROM logs {where} ORDER BY time DESC LIMIT ?',
                params + [limit]
            ).fetchall()
        return [_row_to_dict(r) for r in reversed(rows)]

    def clear_logs(self):
        with self._lock, self.conn() as con:
            con.execute('DELETE FROM logs')

    # ── Failed Links ──────────────────────────────────────────

    def add_failed_link(self, job_id: str, url: str, error: str):
        with self._lock, self.conn() as con:
            con.execute(
                'INSERT INTO failed_links (job_id, url, error, created_at) VALUES (?, ?, ?, ?)',
                (job_id, url, error, _now())
            )

    def get_failed_links(self, job_id: str = None) -> list:
        with self.conn() as con:
            if job_id:
                rows = con.execute(
                    'SELECT * FROM failed_links WHERE job_id = ? ORDER BY created_at DESC',
                    (job_id,)
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT * FROM failed_links ORDER BY created_at DESC LIMIT 200'
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def clear_failed_links(self, job_id: str = None):
        with self._lock, self.conn() as con:
            if job_id:
                con.execute('DELETE FROM failed_links WHERE job_id = ?', (job_id,))
            else:
                con.execute('DELETE FROM failed_links')

    # ── Stats ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self.conn() as con:
            total  = con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            active = con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('running','queued','fetching')").fetchone()[0]
            done   = con.execute("SELECT COUNT(*) FROM jobs WHERE state = 'done'").fetchone()[0]
            total_bytes = con.execute("SELECT COALESCE(SUM(total_bytes),0) FROM jobs WHERE state='done'").fetchone()[0]
        return {
            'total':       total,
            'active':      active,
            'done':        done,
            'total_bytes': total_bytes,
        }


# ── Helpers ──────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _now_time() -> str:
    return datetime.now().strftime('%H:%M:%S')

def _row_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    # Deserialize JSON fields
    for key in ('options',):
        if key in d and d[key]:
            try: d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError): pass
    return d
