"""
MegaDL — services/website_downloader.py
Website mirroring via wget: downloads all assets, creates zip archive.
Port of nodejs Website-downloader (https://github.com/AhmadIbrahiim/Website-downloader)
"""

import os
import re
import json
import uuid
import shutil
import time
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse

logger = logging.getLogger('megadl.website')

WGET_FLAGS = [
    '--mirror',
    '--convert-links',
    '--adjust-extension',
    '--page-requisites',
    '--no-parent',
]

BINARIES_CACHE = {}

def _find_binary(name: str) -> Optional[str]:
    if name in BINARIES_CACHE:
        return BINARIES_CACHE[name]
    path = shutil.which(name)
    if path:
        BINARIES_CACHE[name] = path
        return path
    extras = {
        'wget': ['wget.exe', 'wget2', 'wget2.exe'],
    }.get(name, [])
    for e in extras:
        p = shutil.which(e) or e
        if p and Path(p).exists():
            BINARIES_CACHE[name] = p
            return p
    return None


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[^\w\.\-]', '_', name)
    return sanitized.strip('_') or 'website'


class WebsiteDownloaderService:
    """Download complete websites via wget and package as zip."""

    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def get_websites_dir(self) -> Path:
        base = Path(self.settings.get('dl_folder', './downloads'))
        sites_dir = base / 'websites'
        sites_dir.mkdir(parents=True, exist_ok=True)
        return sites_dir

    def start_download(self, job_id: str, url: str, opts: dict,
                       on_progress: Callable = None,
                       on_complete: Callable = None,
                       on_error: Callable = None) -> threading.Thread:
        thread = threading.Thread(
            target=self._run_download,
            args=(job_id, url, opts, on_progress, on_complete, on_error),
            daemon=True,
            name=f'website-{job_id[:8]}',
        )
        thread.start()
        with self._lock:
            self._processes[job_id] = None
        return thread

    def _run_download(self, job_id: str, url: str, opts: dict,
                      on_progress: Callable = None,
                      on_complete: Callable = None,
                      on_error: Callable = None):
        sites_dir = self.get_websites_dir()
        domain = _extract_domain(url) or f'website_{job_id[:8]}'
        safe_domain = _sanitize_filename(domain)
        work_dir = sites_dir / f'{safe_domain}_{job_id[:8]}'
        zip_path = sites_dir / f'{safe_domain}_{job_id[:8]}.zip'

        try:
            # Phase 1: wget mirror
            self.db.update_job(job_id, {'state': 'running'})

            wget_bin = _find_binary('wget')
            if not wget_bin:
                raise RuntimeError('wget not found. Install: apt install wget / pkg install wget')

            cmd = [wget_bin] + WGET_FLAGS + ['--directory-prefix', str(work_dir), url]
            logger.info(f'Starting wget: {" ".join(cmd)}')

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(sites_dir),
            )
            with self._lock:
                self._processes[job_id] = process

            # Parse progress from stderr
            downloaded_files = 0
            for line in iter(process.stderr.readline, ''):
                if not line:
                    break
                line = line.rstrip()
                if on_progress:
                    on_progress(job_id, {'text': line, 'files': downloaded_files})
                if '200 OK' in line or '200 ' in line:
                    downloaded_files += 1
                    if on_progress:
                        on_progress(job_id, {'text': line, 'files': downloaded_files})
                # Update DB progress periodically
                self.db.update_job(job_id, {'progress': min(downloaded_files, 9999)})

            process.wait()

            if process.returncode != 0:
                error_out = process.stderr.read()
                raise RuntimeError(f'wget failed (code {process.returncode}): {error_out[:500]}')

            # Phase 2: Create zip
            if on_progress:
                on_progress(job_id, {'text': 'Compressing website...', 'files': downloaded_files})

            actual_dir = None
            if work_dir.exists():
                items = list(work_dir.iterdir())
                if items:
                    actual_dir = items[0] if items[0].is_dir() else work_dir

            if actual_dir and actual_dir.is_dir():
                archive_name = str(zip_path.with_suffix(''))
                shutil.make_archive(archive_name, 'zip', str(actual_dir))
            elif work_dir.exists():
                archive_name = str(zip_path.with_suffix(''))
                shutil.make_archive(archive_name, 'zip', str(work_dir))
            else:
                raise RuntimeError(f'No files downloaded from {url}')

            if not zip_path.exists():
                raise RuntimeError('Zip creation failed')

            zip_size = zip_path.stat().st_size

            # Clean up wget output directory
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

            # Update DB
            self.db.update_job(job_id, {
                'state': 'done',
                'progress': 100,
                'output_path': str(zip_path),
                'total_bytes': zip_size,
            })
            self.db.add_log(f'Website download complete: {zip_path.name}', 'info', job_id)

            if on_complete:
                on_complete(job_id, str(zip_path))

            if on_progress:
                on_progress(job_id, {'text': 'Completed', 'file': zip_path.name})

        except Exception as e:
            logger.exception(f'Website download failed: {e}')
            self.db.update_job(job_id, {'state': 'error', 'error': str(e)})
            self.db.add_log(f'Website download failed: {e}', 'error', job_id)
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
            if zip_path.exists():
                zip_path.unlink()
            if on_error:
                on_error(job_id, str(e))

        finally:
            with self._lock:
                self._processes.pop(job_id, None)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            process = self._processes.pop(job_id, None)
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            self.db.update_job(job_id, {'state': 'cancelled'})
            self.db.add_log(f'Website download cancelled', 'warn', job_id)
            # Clean up partial files
            sites_dir = self.get_websites_dir()
            for item in sites_dir.iterdir():
                if job_id in item.name:
                    try:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink()
                    except Exception:
                        pass
            return True
        return False

    def cancel_all(self):
        with self._lock:
            for job_id in list(self._processes.keys()):
                self.cancel_job(job_id)
