"""MegaDL — routes/favorites.py"""
from flask import Blueprint, request
from .ping import ok, err, get_db

favorites_bp = Blueprint('favorites', __name__)

@favorites_bp.route('/api/favorites')
def get_favorites():
    return ok({'favorites': get_db().get_favorites()})

@favorites_bp.route('/api/favorites', methods=['POST'])
def add_favorite():
    data   = request.get_json(force=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return err('job_id required')
    db  = get_db()
    job = db.get_job(job_id)
    if not job:
        return err('Job not found', 404)
    db.add_favorite(job)
    return ok()

@favorites_bp.route('/api/favorites/<job_id>', methods=['DELETE'])
def remove_favorite(job_id):
    get_db().remove_favorite(job_id)
    return ok({'removed': job_id})
