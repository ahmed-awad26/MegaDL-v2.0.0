"""MegaDL — routes/ping.py + shared helpers"""

from flask import Blueprint, jsonify, current_app
from functools import wraps

ping_bp = Blueprint('ping', __name__)


@ping_bp.route('/api/ping')
def ping():
    return jsonify({'ok': True, 'backend': 'python', 'version': '2.0.0'})


# ── Shared route helpers ─────────────────────────────────────

def get_db():
    return current_app.config['DB']

def get_settings():
    return current_app.config['SETTINGS']

def get_queue():
    return current_app.config.get('QUEUE')

def get_ytdlp():
    return current_app.config.get('YTDLP')

def ok(data: dict = None, **kwargs):
    payload = {'ok': True}
    if data:
        payload.update(data)
    payload.update(kwargs)
    return jsonify(payload)

def err(message: str, status: int = 400):
    return jsonify({'ok': False, 'error': message}), status

def validate_url(url: str) -> tuple[str | None, str | None]:
    """Validate and sanitize a URL. Returns (clean_url, error_message)."""
    if not url:
        return None, 'URL is required'
    url = url.strip()
    if not url.startswith(('http://', 'https://', 'ftp://')):
        return None, 'Invalid URL scheme'
    # Basic path traversal guard
    if '..' in url:
        return None, 'Invalid URL'
    # Block known ad domains
    BLOCKED = ['doubleclick.net', 'adnxs.com', 'propellerads.com',
               'ouo.io', 'linkvertise.com']
    for domain in BLOCKED:
        if domain in url:
            return None, f'URL blocked: {domain}'
    return url, None
