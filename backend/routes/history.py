"""MegaDL — routes/history.py"""
from flask import Blueprint
from .ping import ok, get_db

history_bp = Blueprint('history', __name__)

@history_bp.route('/api/history')
def get_history():
    from flask import request
    limit = int(request.args.get('limit', 100))
    return ok({'history': get_db().get_history(limit)})

@history_bp.route('/api/history', methods=['DELETE'])
def clear_history():
    get_db().clear_history()
    return ok()
