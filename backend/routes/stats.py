"""MegaDL — routes/stats.py"""
import shutil
import subprocess
from datetime import datetime
from flask import Blueprint
from .ping import ok, get_db, get_settings

stats_bp = Blueprint('stats', __name__)

def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip().split('\n')[0] if r.returncode == 0 else None
    except Exception:
        return None

def _fetch(db, sql, params=()):
    try:
        with db.conn() as con:
            row = con.execute(sql, params).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0

def _fetch_all(db, sql, params=()):
    try:
        with db.conn() as con:
            con.row_factory = None
            rows = con.execute(sql, params).fetchall()
            return rows
    except Exception:
        return []

@stats_bp.route('/api/stats')
def get_stats():
    db     = get_db()
    s      = get_settings()
    stats  = db.get_stats()

    # Today's downloads
    today = datetime.now().strftime('%Y-%m-%d')
    stats['today'] = _fetch(db,
        "SELECT COUNT(*) FROM jobs WHERE state='done' AND date(created_at) = ?", (today,)
    )

    # Failed count
    stats['failed'] = _fetch(db,
        "SELECT COUNT(*) FROM jobs WHERE state='error'"
    )

    # Queue length
    stats['queued'] = _fetch(db,
        "SELECT COUNT(*) FROM jobs WHERE state='queued'"
    )

    # Storage info
    dl_folder = s.get('dl_folder', './downloads')
    try:
        usage = shutil.disk_usage(dl_folder)
        stats['storage'] = {
            'total': usage.total,
            'used':  usage.used,
            'free':  usage.free,
        }
    except Exception:
        stats['storage'] = None

    # System info
    stats['system'] = {
        'ytdlp_version': _run(['yt-dlp', '--version']),
        'ffmpeg_version': (_run(['ffmpeg', '-version']) or '').split(' ')[2] if _run(['ffmpeg', '-version']) else None,
        'python_version': _run(['python3', '--version']) or _run(['python', '--version']),
    }

    # Recent activity (last 5 completed)
    stats['recent'] = []
    try:
        rows = _fetch_all(db,
            "SELECT title, url, output_path, total_bytes, created_at FROM jobs WHERE state='done' ORDER BY updated_at DESC LIMIT 5"
        )
        stats['recent'] = [
            {'title': r[0], 'url': r[1], 'output_path': r[2],
             'total_bytes': r[3], 'created_at': r[4]}
            for r in (rows or [])
        ]
    except Exception:
        pass

    return ok(stats)
