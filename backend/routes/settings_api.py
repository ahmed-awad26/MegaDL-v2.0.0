"""MegaDL — routes/settings_api.py"""
import json
import urllib.request
import urllib.error
import logging
from flask import Blueprint, request
from .ping import ok, err, get_db, get_settings

logger = logging.getLogger('megadl.settings_api')

settings_bp = Blueprint('settings_api', __name__)

@settings_bp.route('/api/settings')
def get_settings_route():
    s = get_settings()
    return ok(s.all())

@settings_bp.route('/api/settings', methods=['POST'])
def save_settings_route():
    data = request.get_json(force=True) or {}
    s    = get_settings()
    s.update(data)
    s.save()
    get_db().save_settings(data)
    return ok(s.all())

@settings_bp.route('/api/settings/validate-youtube-key', methods=['POST'])
def validate_youtube_key():
    """Validate a YouTube Data API v3 key by calling videos?chart=mostPopular (works with API keys)."""
    data = request.get_json(force=True) or {}
    api_key = data.get('api_key', '').strip()

    if not api_key:
        return err('API key is required')

    try:
        url = f'https://www.googleapis.com/youtube/v3/videos?part=id&chart=mostPopular&maxResults=1&key={api_key}'
        req = urllib.request.Request(url, headers={'User-Agent': 'MegaDL/2.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            if 'error' in body:
                return ok({'valid': False, 'error': body['error'].get('message', 'Unknown error')})
            return ok({'valid': True, 'message': 'YouTube API key is valid'})
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        return ok({'valid': False, 'error': msg})
    except Exception as e:
        return ok({'valid': False, 'error': str(e)})


@settings_bp.route('/api/settings/test-dl-folder', methods=['POST'])
def test_dl_folder():
    """Test if a download folder path is writable."""
    data = request.get_json(force=True) or {}
    path = data.get('path', '').strip()
    if not path:
        return err('Path is required')

    try:
        from pathlib import Path
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        test_file = p / '.megadl_write_test'
        test_file.write_text('test')
        test_file.unlink()
        return ok({'writable': True, 'message': f'{path} is writable'})
    except PermissionError:
        return ok({'writable': False, 'error': 'Permission denied'})
    except Exception as e:
        return ok({'writable': False, 'error': str(e)})
