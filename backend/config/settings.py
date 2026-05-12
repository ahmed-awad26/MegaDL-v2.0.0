"""
MegaDL — config/settings.py
Persistent JSON-based settings with smart defaults and path detection.
"""

import json
import os
import sys
import platform
import logging
from pathlib import Path

logger = logging.getLogger('megadl.settings')


class Settings:
    """Manages app configuration with auto-detection and persistence."""

    DEFAULTS = {
        # Paths
        'dl_folder':        '',          # auto-detected at runtime
        'archive_file':     '',          # auto-detected
        'temp_dir':         '',          # auto-detected

        # Quality / Format
        'def_quality':      'best',
        'merge_format':     'mp4',
        'sub_lang':         'en',

        # Network
        'speed_limit':      0,           # KB/s, 0 = unlimited
        'timeout':          30,
        'retries':          3,
        'frag_retries':     5,
        'concurrent_frag':  4,
        'max_parallel':     3,
        'proxy':            '',

        # Embedding
        'embed_thumb':      True,
        'embed_meta':       True,
        'embed_subs':       False,
        'sponsorblock':     False,

        # Behavior
        'auto_retry':       True,
        'auto_resume':      True,
        'archive_mode':     True,
        'verbose':          False,
        'debug_mode':       False,

        # Telegram
        'telegram_api_id':      '',
        'telegram_api_hash':    '',
        'telegram_phone':       '',

        # YouTube
        'youtube_api_key':      '',

        # Custom
        'custom_args':      '',
    }

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {}
        self._load()
        self._auto_detect_paths()

    # ── Load / Save ──────────────────────────────────────────

    def _load(self):
        """Load settings from JSON file, falling back to defaults."""
        self._data = dict(self.DEFAULTS)
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self._data.update(saved)
                logger.info(f'Settings loaded from {self.config_path}')
            except Exception as e:
                logger.warning(f'Could not load settings: {e}')

    def save(self):
        """Persist settings to JSON file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f'Could not save settings: {e}')

    # ── Path auto-detection ──────────────────────────────────

    def _auto_detect_paths(self):
        """Detect sensible default paths for this OS/environment."""
        if not self._data.get('dl_folder'):
            self._data['dl_folder'] = str(self._detect_download_dir())
        if not self._data.get('temp_dir'):
            self._data['temp_dir'] = str(self._detect_temp_dir())
        if not self._data.get('archive_file'):
            self._data['archive_file'] = str(
                Path(self._data['dl_folder']) / '.megadl_archive.txt'
            )

        # Ensure directories exist and validate write access
        for key in ('dl_folder', 'temp_dir'):
            path = Path(self._data[key])
            try:
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / '.megadl_write_test'
                test_file.write_text('test')
                test_file.unlink()
            except PermissionError:
                logger.warning(f'[PERM] Cannot write to {path} — check storage permissions')
            except Exception as e:
                logger.warning(f'[PERM] Cannot access {path}: {e}')

    def _detect_download_dir(self) -> Path:
        """Return the best writable download directory for this platform.
        Always prefers a dedicated 'MegaDL' subfolder in the system's Downloads folder."""
        candidates = []
        system = platform.system().lower()

        if system == 'android' or os.path.exists('/sdcard'):
            candidates += [
                Path('/storage/emulated/0/Download/MegaDL'),
                Path('/sdcard/Download/MegaDL'),
                Path('/storage/emulated/0/Download'),
                Path('/sdcard/Download'),
            ]

        if system in ('linux', 'darwin') or 'linux' in sys.platform:
            home = Path.home()
            candidates += [
                home / 'Downloads' / 'MegaDL',
                home / 'megadl_downloads',
                home / 'Downloads',
            ]

        if system == 'windows' or 'win' in sys.platform:
            user_profile = os.environ.get('USERPROFILE', 'C:/Users/User')
            candidates += [
                Path(user_profile) / 'Downloads' / 'MegaDL',
                Path(user_profile) / 'Downloads',
            ]

        for path in candidates:
            try:
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / '.megadl_write_test'
                test_file.write_text('test')
                test_file.unlink()
                logger.info(f'Download directory: {path}')
                return path
            except (PermissionError, OSError):
                continue

        # Ultimate fallback: system temp
        import tempfile
        fallback = Path(tempfile.gettempdir()) / 'MegaDL' / 'downloads'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _detect_temp_dir(self) -> Path:
        """Return writable temp directory outside the project."""
        import tempfile
        tmp = Path(tempfile.gettempdir()) / 'MegaDL' / 'temp'
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            return tmp
        except Exception:
            return Path(os.environ.get('TMP', '/tmp')) / 'MegaDL' / 'temp'

    # ── Getters / Setters ────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def update(self, data: dict):
        self._data.update(data)

    def all(self) -> dict:
        return dict(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data
