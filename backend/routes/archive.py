"""MegaDL — routes/archive.py"""
from flask import Blueprint
from .ping import ok, get_db

archive_bp = Blueprint('archive', __name__)

@archive_bp.route('/api/archive')
def get_archive():
    return ok({'archive': get_db().get_archive()})

@archive_bp.route('/api/archive', methods=['DELETE'])
def clear_archive():
    get_db().clear_archive()
    return ok()
