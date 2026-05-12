"""MegaDL — routes/stats.py"""
import shutil
from flask import Blueprint
from .ping import ok, get_db, get_settings

stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/stats')
def get_stats():
    db    = get_db()
    stats = db.get_stats()

    # Storage info
    dl_folder = get_settings().get('dl_folder', './downloads')
    try:
        usage = shutil.disk_usage(dl_folder)
        stats['storage'] = {
            'total': usage.total,
            'used':  usage.used,
            'free':  usage.free,
        }
    except Exception:
        stats['storage'] = None

    return ok(stats)
