"""MegaDL — routes/logs_api.py"""
from flask import Blueprint, request
from .ping import ok, get_db

logs_bp = Blueprint('logs_api', __name__)

@logs_bp.route('/api/logs')
def get_logs():
    level  = request.args.get('level', 'all')
    job_id = request.args.get('job_id')
    limit  = int(request.args.get('limit', 500))
    logs   = get_db().get_logs(
        level  = level if level != 'all' else None,
        limit  = limit,
        job_id = job_id or None
    )
    return ok({'logs': logs})

@logs_bp.route('/api/logs', methods=['DELETE'])
def clear_logs():
    get_db().clear_logs()
    return ok()
