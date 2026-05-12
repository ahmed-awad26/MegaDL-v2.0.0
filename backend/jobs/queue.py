"""
MegaDL — jobs/queue.py
Manages download queue: limits parallel jobs, auto-retries, and restarts.
"""

import uuid
import logging
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger('megadl.queue')


class DownloadQueue:
    """
    Thread-safe download queue with configurable parallelism.
    Manages job lifecycle: queued → running → done/error.
    """

    def __init__(self, ytdlp_service, db, settings, filehost_service=None):
        self.svc      = ytdlp_service
        self.fh_svc   = filehost_service
        self.db       = db
        self.settings = settings

        self._queue:    deque[dict] = deque()
        self._running:  dict[str, threading.Thread] = {}
        self._lock      = threading.Lock()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def max_parallel(self) -> int:
        return int(self.settings.get('max_parallel', 3))

    # ── Start / Stop ─────────────────────────────────────────

    def start(self):
        """Start the scheduler loop."""
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name='dl-scheduler'
        )
        self._scheduler_thread.start()
        logger.info('Download queue started')

        # Resume any queued/interrupted jobs from DB
        self._restore_from_db()

    def stop(self):
        """Stop the scheduler gracefully."""
        self._stop_event.set()
        self.svc.cancel_all()

    # ── Enqueue ──────────────────────────────────────────────

    def enqueue(self, url: str, opts: dict = None, job_id: str = None) -> dict:
        """
        Add a download to the queue.
        Returns the created job dict.
        """
        opts     = opts or {}
        job_id   = job_id or str(uuid.uuid4())

        # Extract basic info for DB record
        job_data = {
            'id':      job_id,
            'url':     url,
            'title':   opts.pop('title', ''),
            'thumbnail': opts.pop('thumbnail', ''),
            'uploader':  opts.pop('uploader', ''),
            'duration':  opts.pop('duration', 0),
            'resolution': opts.pop('resolution', ''),
            'state':   'queued',
            'options': opts,
        }

        # Save to DB
        self.db.create_job(job_data)
        self.db.add_log(f'Queued: {url}', 'info', job_id)

        # Add to in-memory queue
        with self._lock:
            self._queue.append({'id': job_id, 'url': url, 'opts': opts})

        logger.info(f'Queued job {job_id[:8]}: {url}')
        return self.db.get_job(job_id)

    def enqueue_batch(self, urls: list, opts: dict = None) -> list:
        """Enqueue multiple URLs."""
        jobs = []
        base_opts = opts or {}
        for url in urls:
            job = self.enqueue(url.strip(), dict(base_opts))
            jobs.append(job)
        return jobs

    # ── Scheduler loop ────────────────────────────────────────

    def _scheduler_loop(self):
        """Main loop: pulls from queue and starts downloads up to max_parallel."""
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(timeout=1.0)

    def _tick(self):
        """One scheduler cycle: start jobs if slots available."""
        with self._lock:
            # Clean up finished threads
            finished = [jid for jid, t in self._running.items() if not t.is_alive()]
            for jid in finished:
                del self._running[jid]

            # Start new jobs up to max_parallel
            slots = self.max_parallel - len(self._running)
            started = 0
            while slots > started and self._queue:
                item = self._queue.popleft()
                job_id = item['id']

                # Verify job is still in queued state (not cancelled)
                job = self.db.get_job(job_id)
                if not job or job.get('state') not in ('queued',):
                    continue

                opts = item.get('opts', {})
                mode = opts.get('mode', '')

                # Route filehost downloads to FileHostService
                if mode == 'filehost' and self.fh_svc:
                    thread = self.fh_svc.start_download(
                        job_id  = job_id,
                        url     = item['url'],
                        opts    = opts,
                        on_progress = self._on_progress,
                        on_complete = self._on_complete,
                        on_error    = self._on_error,
                    )
                else:
                    thread = self.svc.start_download(
                        job_id  = job_id,
                        url     = item['url'],
                        opts    = opts,
                        on_progress = self._on_progress,
                        on_complete = self._on_complete,
                        on_error    = self._on_error,
                    )
                self._running[job_id] = thread
                started += 1

    # ── Callbacks ────────────────────────────────────────────

    def _on_progress(self, job_id: str, progress: dict):
        pass  # DB is already updated in ytdlp_service

    def _on_complete(self, job_id: str, output_path: str):
        logger.info(f'Job {job_id[:8]} completed: {output_path}')
        with self._lock:
            self._running.pop(job_id, None)

    def _on_error(self, job_id: str, error: str):
        logger.error(f'Job {job_id[:8]} failed: {error}')
        with self._lock:
            self._running.pop(job_id, None)

        # Auto-retry logic
        job = self.db.get_job(job_id)
        if job and self.settings.get('auto_retry', True):
            retries = job.get('options', {}).get('_retry_count', 0)
            max_retries = int(self.settings.get('retries', 3))
            if retries < max_retries:
                logger.info(f'Auto-retry {retries + 1}/{max_retries} for {job_id[:8]}')
                opts = job.get('options', {})
                opts['_retry_count'] = retries + 1
                self.db.update_job(job_id, {'state': 'queued', 'error': None, 'options': opts})
                with self._lock:
                    self._queue.append({'id': job_id, 'url': job['url'], 'opts': opts})

    # ── Job control ──────────────────────────────────────────

    def pause_job(self, job_id: str) -> bool:
        # Remove from queue if still waiting
        with self._lock:
            self._queue = deque(item for item in self._queue if item['id'] != job_id)
        return self.svc.pause_job(job_id)

    def resume_job(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job:
            return False
        if job['state'] == 'paused':
            # Re-add to front of queue
            self.db.update_job(job_id, {'state': 'queued'})
            with self._lock:
                self._queue.appendleft({'id': job_id, 'url': job['url'], 'opts': job.get('options', {})})
            return True
        return self.svc.resume_job(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            self._queue = deque(item for item in self._queue if item['id'] != job_id)
        return self.svc.cancel_job(job_id)

    def retry_job(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job:
            return False
        opts = job.get('options', {})
        opts['_retry_count'] = 0
        self.db.update_job(job_id, {'state': 'queued', 'error': None, 'progress': 0})
        with self._lock:
            self._queue.appendleft({'id': job_id, 'url': job['url'], 'opts': opts})
        return True

    def pause_all(self):
        self.svc.pause_all()
        with self._lock:
            for item in self._queue:
                self.db.update_job(item['id'], {'state': 'paused'})
            self._queue.clear()

    def resume_all(self):
        paused = self.db.get_jobs(state_filter='paused')
        for job in paused:
            self.resume_job(job['id'])

    def cancel_all(self):
        """Cancel all running jobs."""
        self.svc.cancel_all()
        if self.fh_svc:
            self.fh_svc.cancel_all()
        # Also clear queued items
        with self._lock:
            self._queue.clear()

    # ── Restore on startup ────────────────────────────────────

    def _restore_from_db(self):
        """Re-queue any jobs that were running when the server stopped."""
        interrupted = self.db.get_active_jobs()
        for job in interrupted:
            if job['state'] in ('running', 'fetching'):
                # These were mid-download — re-queue them
                self.db.update_job(job['id'], {'state': 'queued', 'progress': 0})
                with self._lock:
                    self._queue.append({
                        'id':   job['id'],
                        'url':  job['url'],
                        'opts': job.get('options', {}),
                    })
                logger.info(f'Restored interrupted job: {job["id"][:8]}')
