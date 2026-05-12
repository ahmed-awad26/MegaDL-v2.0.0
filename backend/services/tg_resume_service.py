"""
MegaDL — services/tg_resume_service.py
Resumable download service with 2MB rollback buffer to prevent incomplete chunk corruption.
"""

import os
import json
import shutil
import logging
from pathlib import Path

logger = logging.getLogger('megadl.tg_resume')


class TelegramResumeService:
    """Manages resumable Telegram downloads with offset tracking and rollback."""

    ROLLBACK_BYTES = 2 * 1024 * 1024  # 2MB rollback buffer

    def __init__(self, settings):
        self.settings = settings
        self._jobs: dict = {}  # job_id -> job_state

    def _state_path(self) -> Path:
        """Get the downloads state file path."""
        dl_folder = self.settings.get('dl_folder', './downloads')
        return Path(dl_folder) / '.telegram_downloads_state.json'

    def load_state(self) -> dict:
        """Load download state from disk."""
        if self._jobs:
            return self._jobs
        path = self._state_path()
        try:
            if path.exists():
                self._jobs = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.warning(f'Failed to load resume state: {e}')
            self._jobs = {}
        return self._jobs

    def save_state(self):
        """Save download state to disk."""
        path = self._state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._jobs, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logger.warning(f'Failed to save resume state: {e}')

    def init_job(self, job_id: str, dialog_id: int, msg_id: int,
                 dest_path: str, total_size: int) -> dict:
        """Initialize a new download job."""
        job = {
            'job_id': job_id,
            'dialog_id': dialog_id,
            'msg_id': msg_id,
            'dest_path': dest_path,
            'total_size': total_size,
            'downloaded_bytes': 0,
            'offset': 0,  # Current write offset
            'temp_path': dest_path + '.tmp',
            'status': 'paused',  # paused, downloading, completed, failed
            'rollback_offset': 0,
            'error': None,
        }
        self._jobs[job_id] = job
        self.save_state()
        return job

    def get_job(self, job_id: str) -> dict:
        """Get job state."""
        self.load_state()
        return self._jobs.get(job_id)

    def update_progress(self, job_id: str, downloaded_bytes: int):
        """Update download progress."""
        job = self.get_job(job_id)
        if job:
            job['downloaded_bytes'] = downloaded_bytes
            job['status'] = 'downloading'
            self._jobs[job_id] = job
            self.save_state()

    def mark_completed(self, job_id: str):
        """Mark job as completed and rename temp file."""
        job = self.get_job(job_id)
        if job:
            job['status'] = 'completed'
            job['downloaded_bytes'] = job['total_size']
            job['offset'] = job['total_size']
            self._jobs[job_id] = job
            self.save_state()

            # Rename temp file to final destination
            temp_path = Path(job['temp_path'])
            dest_path = Path(job['dest_path'])
            if temp_path.exists():
                if dest_path.exists():
                    dest_path.unlink()
                try:
                    shutil.move(str(temp_path), str(dest_path))
                except Exception as e:
                    logger.error(f'Failed to rename temp file: {e}')

    def mark_failed(self, job_id: str, error: str):
        """Mark job as failed."""
        job = self.get_job(job_id)
        if job:
            job['status'] = 'failed'
            job['error'] = error
            self._jobs[job_id] = job
            self.save_state()

    def mark_paused(self, job_id: str):
        """Mark job as paused."""
        job = self.get_job(job_id)
        if job:
            # Calculate rollback offset: go back 2MB to ensure clean boundary
            rollback = max(0, job.get('downloaded_bytes', 0) - self.ROLLBACK_BYTES)
            job['rollback_offset'] = rollback
            job['status'] = 'paused'
            self._jobs[job_id] = job
            self.save_state()

            # Truncate temp file to rollback point
            temp_path = Path(job['temp_path'])
            if temp_path.exists():
                try:
                    with open(str(temp_path), 'r+b') as f:
                        f.truncate(rollback)
                    logger.info(f'Rolled back {job_id} to offset {rollback} ({self.ROLLBACK_BYTES} bytes)')
                except Exception as e:
                    logger.warning(f'Failed to truncate temp file for rollback: {e}')

    def get_resume_offset(self, job_id: str) -> int:
        """Get the offset to resume from (accounts for rollback)."""
        job = self.get_job(job_id)
        if not job:
            return 0
        return job.get('rollback_offset') or job.get('downloaded_bytes', 0)

    def remove_job(self, job_id: str):
        """Remove a completed/failed job from state."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self.save_state()

    def clean_temp_files(self, job_id: str = None):
        """Clean up temporary files for a job or all jobs."""
        self.load_state()
        if job_id:
            job = self._jobs.get(job_id)
            if job:
                temp_path = Path(job['temp_path'])
                if temp_path.exists():
                    temp_path.unlink()
                del self._jobs[job_id]
                self.save_state()
        else:
            for jid, job in list(self._jobs.items()):
                if job.get('status') in ('completed', 'failed'):
                    temp_path = Path(job['temp_path'])
                    if temp_path.exists():
                        temp_path.unlink()
                    del self._jobs[jid]
            self.save_state()

    def get_active_jobs(self) -> dict:
        """Get all active download jobs (not completed/failed)."""
        return {
            jid: job for jid, job in self.load_state().items()
            if job.get('status') not in ('completed', 'failed')
        }

    def get_job_stats(self) -> dict:
        """Get overall download stats."""
        self.load_state()
        total = len(self._jobs)
        completed = sum(1 for j in self._jobs.values() if j.get('status') == 'completed')
        failed = sum(1 for j in self._jobs.values() if j.get('status') == 'failed')
        paused = sum(1 for j in self._jobs.values() if j.get('status') == 'paused')
        downloading = sum(1 for j in self._jobs.values() if j.get('status') == 'downloading')
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'paused': paused,
            'downloading': downloading,
        }
