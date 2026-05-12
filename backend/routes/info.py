"""MegaDL — routes/info.py  (Video info extraction)"""

from flask import Blueprint, request
from .ping import ok, err, validate_url, get_ytdlp, get_db

info_bp = Blueprint('info', __name__)


@info_bp.route('/api/info', methods=['POST'])
def fetch_info():
    data = request.get_json(force=True) or {}
    url  = data.get('url', '').strip()
    clean, error = validate_url(url)
    if error:
        return err(error)

    ytdlp = get_ytdlp()
    if not ytdlp:
        return err('yt-dlp service not available', 503)

    try:
        info = ytdlp.extract_info(clean, opts=data.get('opts', {}))
        return ok(info)
    except Exception as e:
        return err(str(e), 500)
