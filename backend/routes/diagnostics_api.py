"""MegaDL — routes/diagnostics_api.py"""

import shutil
import subprocess
import platform
from pathlib import Path
from flask import Blueprint
from .ping import ok, get_settings
from services.ytdlp_service import YtdlpService

diag_bp = Blueprint('diagnostics_api', __name__)


def _check_binary(name: str) -> dict:
    binary = YtdlpService.find_binary(name)
    if not binary:
        return {'ok': False, 'available': False}
    version = YtdlpService.get_version(binary)
    return {'ok': True, 'available': True, 'path': binary, 'version': version or 'unknown'}


def _check_storage(dl_folder: str) -> dict:
    try:
        usage = shutil.disk_usage(dl_folder)
        return {
            'ok':    True,
            'total': usage.total,
            'used':  usage.used,
            'free':  usage.free,
            'path':  dl_folder,
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _check_writable(dl_folder: str) -> dict:
    try:
        test = Path(dl_folder) / '.megadl_write_test'
        test.write_text('test')
        test.unlink()
        return {'ok': True, 'writable': True, 'path': dl_folder}
    except Exception as e:
        return {'ok': False, 'writable': False, 'error': str(e)}


def _check_network() -> dict:
    try:
        import urllib.request
        urllib.request.urlopen('https://www.google.com', timeout=5)
        return {'ok': True, 'online': True}
    except Exception:
        return {'ok': False, 'online': False}


def _check_php() -> dict:
    binary = shutil.which('php')
    if not binary:
        return {'ok': False, 'available': False}
    try:
        r = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=5)
        ver = r.stdout.strip().split('\n')[0]
        return {'ok': True, 'available': True, 'version': ver}
    except Exception:
        return {'ok': False, 'available': False}


@diag_bp.route('/api/diagnostics')
def run_diagnostics():
    s = get_settings()
    dl_folder = s.get('dl_folder', './downloads')
    checks = {
        'python':  {'ok': True, 'version': platform.python_version()},
        'ytdlp':   _check_binary('yt-dlp'),
        'ffmpeg':  _check_binary('ffmpeg'),
        'php':     _check_php(),
        'storage': _check_storage(dl_folder),
        'writable': _check_writable(dl_folder),
        'network': _check_network(),
    }
    all_ok = all(v.get('ok', False) for v in checks.values())
    return ok({'checks': checks, 'all_ok': all_ok, 'backend': 'python'})
