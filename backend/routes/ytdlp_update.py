"""MegaDL — routes/ytdlp_update.py"""
from flask import Blueprint
from .ping import ok, err, get_ytdlp

ytdlp_update_bp = Blueprint('ytdlp_update', __name__)


@ytdlp_update_bp.route('/api/ytdlp/check-update')
def check_update():
    svc = get_ytdlp()
    return ok(svc.check_ytdlp_update())


@ytdlp_update_bp.route('/api/ytdlp/update', methods=['POST'])
def do_update():
    svc = get_ytdlp()
    return ok(svc.update_ytdlp())
