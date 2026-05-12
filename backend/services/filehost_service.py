"""
MegaDL — services/filehost_service.py
Download from file-hosting sites (Mega.nz, MediaFire, Google Drive,
Dropbox, direct URLs) using site-specific tools or aria2/wget
as fallback, with yt-dlp as primary detector.
"""

import os
import re
import json
import time
import shutil
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse

logger = logging.getLogger('megadl.filehost')

BINARIES_CACHE = {}

def _find_binary(name: str) -> Optional[str]:
    if name in BINARIES_CACHE:
        return BINARIES_CACHE[name]
    path = shutil.which(name)
    if path:
        BINARIES_CACHE[name] = path
        return path
    extras = {
        'aria2c': ['aria2c.exe'],
        'mega-get': ['megatools'],
        'wget': ['wget.exe'],
    }.get(name, [])
    for e in extras:
        p = shutil.which(e) or e
        if p and Path(p).exists():
            BINARIES_CACHE[name] = p
            return p
    return None


class FileHostService:
    """Download files from supported file-hosting platforms."""

    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self._processes = {}
        self._lock = threading.Lock()

    # ── Platform detection ────────────────────────────────────

    @staticmethod
    def detect_platform(url: str) -> str:
        url_lower = url.lower()
        if 'mega.nz' in url_lower or 'mega.co.nz' in url_lower:
            return 'mega'
        if 'mediafire.com' in url_lower:
            return 'mediafire'
        if '4shared.com' in url_lower:
            return '4shared'
        if 'gofile.io' in url_lower:
            return 'gofile'
        if 'drive.google.com' in url_lower or 'docs.google.com' in url_lower:
            return 'gdrive'
        if 'dropbox.com' in url_lower:
            return 'dropbox'
        if 'onedrive.live.com' in url_lower or '1drv.ms' in url_lower:
            return 'onedrive'
        if 'pixeldrain.com' in url_lower:
            return 'pixeldrain'
        return 'direct'

    # ── Main download entry ───────────────────────────────────

    def start_download(self, job_id: str, url: str, opts: dict,
                       on_progress: Callable = None,
                       on_complete: Callable = None,
                       on_error: Callable = None) -> threading.Thread:
        thread = threading.Thread(
            target=self._download_worker,
            args=(job_id, url, opts, on_progress, on_complete, on_error),
            daemon=True,
            name=f'fh-{job_id[:8]}',
        )
        thread.start()
        return thread

    def _download_worker(self, job_id, url, opts, on_progress, on_complete, on_error):
        platform = self.detect_platform(url)
        dl_folder = self.settings.get('dl_folder', './downloads')
        dl_path = Path(dl_folder)
        dl_path.mkdir(parents=True, exist_ok=True)

        def _progress(pct, speed=0, eta=0):
            update = {'progress': pct, 'speed': speed, 'eta': eta}
            self.db.update_job(job_id, update)
            if on_progress:
                on_progress(job_id, update)

        def _done(path):
            self.db.update_job(job_id, {'state': 'done', 'progress': 100, 'output_path': str(path)})
            self.db.add_log(f'Download completed -> {path}', 'info', job_id)
            job = self.db.get_job(job_id)
            if job:
                self.db.add_history(job)
            if on_complete:
                on_complete(job_id, str(path))

        def _error(msg):
            self.db.update_job(job_id, {'state': 'error', 'error': msg})
            self.db.add_log(f'Download failed: {msg}', 'error', job_id)
            if on_error:
                on_error(job_id, msg)

        self.db.update_job(job_id, {'state': 'running'})
        self.db.add_log(f'Starting filehost download ({platform}): {url}', 'info', job_id)

        try:
            if platform == 'mega':
                result = self._download_mega(url, dl_path, job_id, _progress, _done, _error)
            elif platform == 'gdrive':
                result = self._download_gdrive(url, dl_path, job_id, _progress, _done, _error)
            elif platform == 'mediafire':
                result = self._download_with_ytdlp(url, dl_path, job_id, _progress, _done, _error)
            elif platform == 'direct':
                result = self._download_direct(url, dl_path, job_id, _progress, _done, _error)
            else:
                # Try yt-dlp first for all others
                result = self._download_with_ytdlp(url, dl_path, job_id, _progress, _done, _error)
        except Exception as e:
            logger.exception(f'[{job_id[:8]}] Filehost error: {e}')
            _error(str(e))

    # ── Mega.nz ───────────────────────────────────────────────

    def _download_mega(self, url, dl_path, job_id, on_progress, on_done, on_error):
        mega_get = _find_binary('mega-get')
        aria2 = _find_binary('aria2c')

        if mega_get:
            return self._run_command(
                [mega_get, url, str(dl_path)],
                job_id, on_progress, on_done, on_error
            )
        if aria2:
            return self._run_command(
                [aria2, '-x4', '-s4', '--dir', str(dl_path), url],
                job_id, on_progress, on_done, on_error
            )

        # Fallback: use mega.py
        try:
            import mega
            m = mega.Mega()
            link = m.import_mega_url(url)
            filename = link[0] if isinstance(link, list) and link else 'mega_file'
            dest = dl_path / filename
            m.download_url(url, str(dl_path))
            on_done(dest)
        except ImportError:
            on_error('mega.py or megatools not installed')

    # ── Google Drive ──────────────────────────────────────────

    def _download_gdrive(self, url, dl_path, job_id, on_progress, on_done, on_error):
        file_id = self._extract_gdrive_id(url)
        if not file_id:
            # Try yt-dlp
            return self._download_with_ytdlp(url, dl_path, job_id, on_progress, on_done, on_error)

        gdown = _find_binary('gdown')
        if gdown:
            return self._run_command(
                [gdown, f'--id={file_id}', '-O', str(dl_path), '--fuzzy'],
                job_id, on_progress, on_done, on_error
            )

        # Python fallback
        try:
            import gdown as gd
            output = str(dl_path / f'{file_id}')
            result = gd.download(id=file_id, output=output, fuzzy=True)
            if result:
                on_done(result)
            else:
                on_error('gdown download failed')
        except ImportError:
            on_error('gdown not installed')

    @staticmethod
    def _extract_gdrive_id(url: str) -> Optional[str]:
        patterns = [
            r'/file/d/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'/folders/([a-zA-Z0-9_-]+)',
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    # ── Direct URL (aria2/wget) ───────────────────────────────

    def _download_direct(self, url, dl_path, job_id, on_progress, on_done, on_error):
        aria2 = _find_binary('aria2c')
        wget = _find_binary('wget')

        if aria2:
            return self._run_command(
                [aria2, '-x4', '-s4', '--continue', '--dir', str(dl_path), url],
                job_id, on_progress, on_done, on_error
            )
        if wget:
            return self._run_command(
                [wget, '-c', '-P', str(dl_path), url],
                job_id, on_progress, on_done, on_error
            )

        # Python requests
        import requests
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or 'download'
        dest = dl_path / filename

        resp = requests.get(url, stream=True, timeout=30,
                            headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()

        total = int(resp.headers.get('content-length', 0))
        downloaded = 0
        start = time.time()

        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = (downloaded / total) * 100
                        elapsed = time.time() - start
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        remaining = ((total - downloaded) / speed) if speed > 0 else 0
                        on_progress(pct, speed, remaining)

        on_done(dest)

    # ── yt-dlp fallback ───────────────────────────────────────

    def _download_with_ytdlp(self, url, dl_path, job_id, on_progress, on_done, on_error):
        """Delegate to yt-dlp (handles many file hosts)."""
        ytdlp = shutil.which('yt-dlp')
        if not ytdlp:
            on_error('yt-dlp not found')
            return
        return self._run_command(
            [ytdlp, '-o', str(dl_path / '%(title)s.%(ext)s'),
             '--no-playlist', '--newline', '--continue', url],
            job_id, on_progress, on_done, on_error
        )

    # ── Subprocess helper ─────────────────────────────────────

    def _run_command(self, cmd, job_id, on_progress, on_done, on_error):
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
            )
            with self._lock:
                self._processes[job_id] = proc

            output_path = None
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                line = line.rstrip()
                self.db.add_log(line, 'debug', job_id)

                # aria2 progress
                aria_m = re.search(r'\((\d+)%\)', line)
                if aria_m:
                    on_progress(float(aria_m.group(1)))

            proc.wait()

            with self._lock:
                self._processes.pop(job_id, None)

            if proc.returncode == 0:
                on_done(cmd[-1])
            else:
                on_error(f'Process exited with code {proc.returncode}')

        except FileNotFoundError as e:
            on_error(f'Binary not found: {e.filename or e}')
        except Exception as e:
            on_error(str(e))

    def cancel_job(self, job_id: str):
        proc = self._processes.get(job_id)
        if proc:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            self._processes.pop(job_id, None)

    def cancel_all(self):
        for job_id in list(self._processes.keys()):
            self.cancel_job(job_id)
