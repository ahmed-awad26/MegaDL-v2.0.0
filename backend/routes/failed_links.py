"""MegaDL — routes/failed_links.py"""

from flask import Blueprint, request
from .ping import ok, err, get_db

failed_bp = Blueprint('failed_links', __name__)


@failed_bp.route('/api/failed-links')
def get_failed_links():
    db = get_db()
    job_id = request.args.get('job_id', '')
    links = db.get_failed_links(job_id if job_id else None)
    return ok({'failed_links': links, 'count': len(links)})


@failed_bp.route('/api/failed-links', methods=['DELETE'])
def clear_failed_links():
    db = get_db()
    job_id = (request.get_json(force=True) or {}).get('job_id', '')
    db.clear_failed_links(job_id if job_id else None)
    return ok({'cleared': True})
