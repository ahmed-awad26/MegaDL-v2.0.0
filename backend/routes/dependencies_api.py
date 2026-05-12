"""
MegaDL — routes/dependencies_api.py
Dependencies Dashboard: check installed versions, install missing deps.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
from flask import Blueprint
from .ping import ok, err, get_settings

logger = logging.getLogger('megadl.deps')

deps_bp = Blueprint('dependencies', __name__)

# Known dependencies: name → pip package name
DEPS = {
    'yt-dlp':           'yt-dlp',
    'ffmpeg':           None,
    'telethon':         'telethon',
    'cryptg':           'cryptg',
    'aiofiles':         'aiofiles',
    'psutil':           'psutil',
    'requests':         'requests',
    'openpyxl':         'openpyxl',
    'mega.py':          'mega.py',
    'pillow':           'pillow',
    'yt-dlp[default]':  'yt-dlp',
    'google-api-python-client': 'google-api-python-client',
    'google-auth-oauthlib':     'google-auth-oauthlib',
    'gdown':            'gdown',
    'requests[socks]':  'requests[socks]',
    'beautifulsoup4':   'beautifulsoup4',
    'lxml':             'lxml',
    'cloudscraper':     'cloudscraper',
    'selenium':         'selenium',
    'undetected-chromedriver': 'undetected-chromedriver',
    'aria2p':           'aria2p',
}


def _get_version(binary: str) -> str:
    try:
        r = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=5)
        return r.stdout.strip().split('\n')[0] or 'installed'
    except Exception:
        return ''


def _import_check(pkg: str) -> tuple:
    """Try to detect a package via import. Returns (bool, version_str)."""
    try:
        import importlib
        mod = importlib.import_module(pkg.replace('-', '_'))
        ver = getattr(mod, '__version__', getattr(mod, 'version', ''))
        return True, str(ver) or 'installed'
    except Exception:
        pass
    # Try alternative import names
    alt = {'pillow': 'PIL', 'mega.py': 'mega'}.get(pkg)
    if alt:
        try:
            importlib.import_module(alt)
            return True, 'installed'
        except ImportError:
            pass
    return False, ''


def _pip_installed(pkg: str) -> tuple:
    """Check if a pip package is installed. Returns (bool, version_str).
    Uses import first (reliable), falls back to pip show."""
    # Import check is more reliable (pip 26.0.1 has broken 'pip show')
    imported, ver = _import_check(pkg)
    if imported:
        return True, ver

    # Fallback: try pip show
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', pkg],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.split('\n'):
                if line.lower().startswith('version:'):
                    return True, line.split(':', 1)[1].strip()
            return True, 'installed'
    except Exception:
        pass

    return False, ''


@deps_bp.route('/api/dependencies/check')
def check_deps():
    """Check all known dependencies."""
    results = {}

    for name, pkg in DEPS.items():
        if pkg is None:
            # System binary
            vers = _get_version(name)
            results[name] = {
                'installed': bool(vers),
                'version': vers or '',
                'type': 'binary',
            }
        else:
            installed, vers = _pip_installed(pkg)
            results[name] = {
                'installed': installed,
                'version': vers,
                'type': 'pip',
                'pip_package': pkg,
            }

    return ok({'dependencies': results})


@deps_bp.route('/api/dependencies/install', methods=['POST'])
def install_dep():
    """Install a pip dependency."""
    from flask import request
    data = request.get_json(force=True) or {}
    name = data.get('name', '').strip()

    if not name:
        return err('Dependency name required')

    pkg = DEPS.get(name)
    if pkg is None:
        # Try system install for binaries
        if name == 'ffmpeg':
            return _install_ffmpeg()
        return err(f'Unknown dependency: {name}')

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', pkg,
             '--break-system-packages'],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            installed, vers = _pip_installed(pkg)
            return ok({
                'success': True,
                'name': name,
                'version': vers,
                'output': result.stdout[-500:],
            })
        else:
            return err(f'Install failed: {result.stderr[-300:]}')
    except subprocess.TimeoutExpired:
        return err('Install timed out (120s)')
    except Exception as e:
        return err(str(e))


def _install_ffmpeg():
    """Provide platform-specific ffmpeg install instructions."""
    system = sys.platform.lower()
    instructions = ''

    if 'linux' in system:
        instructions = 'apt install ffmpeg -y'
    elif 'darwin' in system:
        instructions = 'brew install ffmpeg'
    elif 'win' in system:
        instructions = 'Download from https://ffmpeg.org/download.html'

    return ok({
        'success': False,
        'system': True,
        'instructions': instructions,
        'message': f'Cannot auto-install ffmpeg. Run: {instructions}',
    })
