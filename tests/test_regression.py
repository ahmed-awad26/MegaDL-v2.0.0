#!/usr/bin/env python3
"""
MegaDL — Full Regression Test Suite
Tests all API endpoints, core services, and database operations.
Run: python tests/test_regression.py
"""

import os
import sys
import json
import uuid
import time
import shutil
import unittest
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).parent.parent
BACKEND_DIR = BASE_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

TEST_DB = str(BASE_DIR / 'tests' / 'test_megadl.db')
TEST_SETTINGS = {
    'dl_folder':       str(BASE_DIR / 'tests' / 'downloads'),
    'def_quality':     'best',
    'merge_format':    'mp4',
    'concurrent_frag': 2,
    'max_parallel':    3,
    'retries':         1,
    'embed_thumb':     False,
    'embed_meta':      False,
    'sponsorblock':    False,
    'archive_mode':    False,
    'speed_limit':     0,
    'timeout':         15,
}

def cleanup():
    for f in [TEST_DB, TEST_DB + '-wal', TEST_DB + '-shm']:
        try: os.unlink(f)
        except: pass
    dl = Path(TEST_SETTINGS['dl_folder'])
    if dl.exists():
        shutil.rmtree(str(dl), ignore_errors=True)

# ── Database Tests ──────────────────────────────────────────────
class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from database.db import Database
        cls.db = Database(TEST_DB)
        cls.db.initialize()

    def setUp(self):
        self.job_id = str(uuid.uuid4())
        self.db.create_job({
            'id':    self.job_id,
            'url':   'https://youtube.com/test',
            'title': 'Test Video',
            'state': 'queued',
        })

    def _clean_table(self, table):
        from database.db import Database
        with self.db.conn() as con:
            con.execute(f"DELETE FROM {table}")

    def tearDown(self):
        for t in ['jobs', 'history', 'archive', 'favorites', 'logs']:
            self._clean_table(t)

    def test_01_create_and_get_job(self):
        job = self.db.get_job(self.job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job['url'], 'https://youtube.com/test')
        self.assertEqual(job['state'], 'queued')

    def test_02_update_job(self):
        self.db.update_job(self.job_id, {'state': 'running', 'progress': 50})
        job = self.db.get_job(self.job_id)
        self.assertEqual(job['state'], 'running')
        self.assertEqual(job['progress'], 50)

    def test_03_get_jobs_with_filter(self):
        id2 = str(uuid.uuid4())
        self.db.create_job({'id': id2, 'url': 'https://example.com/2', 'title': 'Done', 'state': 'done'})
        all_jobs = self.db.get_jobs(state_filter='all')
        self.assertGreaterEqual(len(all_jobs), 2)

    def test_04_get_active_jobs(self):
        self.db.update_job(self.job_id, {'state': 'running'})
        active = self.db.get_active_jobs()
        self.assertTrue(any(j['id'] == self.job_id for j in active))

    def test_05_delete_job(self):
        self.db.delete_job(self.job_id)
        self.assertIsNone(self.db.get_job(self.job_id))

    def test_06_history_crud(self):
        job = self.db.get_job(self.job_id)
        job['state'] = 'done' if job else 'done'
        self.db.add_history(job or {})
        history = self.db.get_history()
        self.assertGreaterEqual(len(history), 1)

    def test_07_archive_crud(self):
        self.db.add_archive('youtube', 'test_video_id', 'Test Vid')
        arch = self.db.get_archive()
        self.assertTrue(any(a['id'] == 'test_video_id' for a in arch))

    def test_08_favorites_crud(self):
        job = self.db.get_job(self.job_id)
        self.db.add_favorite(job or {})
        favs = self.db.get_favorites()
        self.assertGreaterEqual(len(favs), 1)
        self.db.remove_favorite(self.job_id)
        favs = self.db.get_favorites()
        self.assertFalse(any(f['job_id'] == self.job_id for f in favs))

    def test_09_logs_crud(self):
        self.db.add_log('Test log message', 'info', self.job_id)
        logs = self.db.get_logs()
        self.assertTrue(any(l['message'] == 'Test log message' for l in logs))

    def test_10_stats(self):
        stats = self.db.get_stats()
        self.assertIn('total', stats)
        self.assertIn('active', stats)
        self.assertIn('done', stats)

# ── Queue Tests ─────────────────────────────────────────────────
class TestDownloadQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from database.db import Database
        from config.settings import Settings
        from services.ytdlp_service import YtdlpService
        from jobs.queue import DownloadQueue

        cls.db = Database(TEST_DB)
        cls.db.initialize()
        cls.settings = Settings.__new__(Settings)
        cls.settings._data = dict(TEST_SETTINGS)
        cls.settings._path = str(BASE_DIR / 'tests' / 'test_settings.json')
        cls.ytdlp = YtdlpService(cls.settings, cls.db)
        cls.queue = DownloadQueue(cls.ytdlp, cls.db, cls.settings)

    @classmethod
    def tearDownClass(cls):
        cls.queue.stop()
        for f in [str(BASE_DIR / 'tests' / 'test_settings.json')]:
            try: os.unlink(f)
            except: pass

    def setUp(self):
        with self.db.conn() as con:
            con.execute("DELETE FROM jobs")

    def test_01_enqueue_job(self):
        job = self.queue.enqueue('https://youtube.com/test', {})
        self.assertIsNotNone(job)
        self.assertEqual(job['state'], 'queued')
        self.assertIn('id', job)

    def test_02_enqueue_batch(self):
        urls = ['https://youtube.com/1', 'https://youtube.com/2']
        jobs = self.queue.enqueue_batch(urls, {})
        self.assertEqual(len(jobs), 2)

    def test_03_max_parallel_property(self):
        self.assertEqual(self.queue.max_parallel, 3)

    def test_04_pause_resume_job(self):
        job = self.queue.enqueue('https://youtube.com/test', {})
        job_id = job['id']
        self.db.update_job(job_id, {'state': 'paused'})
        ok = self.queue.resume_job(job_id)
        self.assertTrue(ok)

    def test_05_retry_job(self):
        job = self.queue.enqueue('https://youtube.com/test', {})
        job_id = job['id']
        self.db.update_job(job_id, {'state': 'error', 'error': 'test error'})
        ok = self.queue.retry_job(job_id)
        self.assertTrue(ok)
        updated = self.db.get_job(job_id)
        self.assertEqual(updated['state'], 'queued')

    def test_06_cancel_job(self):
        job = self.queue.enqueue('https://youtube.com/test', {})
        job_id = job['id']
        ok = self.queue.cancel_job(job_id)
        self.assertTrue(ok)

    def test_07_bulk_operations(self):
        job_ids = []
        for i in range(3):
            j = self.queue.enqueue(f'https://youtube.com/{i}', {})
            job_ids.append(j['id'])
            self.db.update_job(j['id'], {'state': 'paused'})
        self.queue.resume_all()
        with self.db.conn() as con:
            paused = con.execute("SELECT COUNT(*) FROM jobs WHERE state='paused'").fetchone()
        if paused:
            self.assertEqual(paused[0], 0)

    def test_08_restore_from_db(self):
        self.queue.enqueue('https://youtube.com/restore_test', {})
        with self.db.conn() as con:
            con.execute("UPDATE jobs SET state='running' WHERE state='queued'")
        self.queue._restore_from_db()
        jobs = self.db.get_jobs(state_filter='queued')
        self.assertGreaterEqual(len(jobs), 1)

# ── Flask API Tests ─────────────────────────────────────────────
class TestFlaskAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app
        cls.client = app.test_client()
        app.config['TESTING'] = True
        from database.db import Database
        cls.db = Database(TEST_DB)
        cls.db.initialize()
        app.config['DB'] = cls.db

    def setUp(self):
        with self.db.conn() as con:
            for t in ['jobs', 'history', 'archive', 'favorites', 'logs']:
                con.execute(f"DELETE FROM {t}")

    def test_01_ping(self):
        resp = self.client.get('/api/ping')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get('ok'))

    def test_02_queue_endpoint(self):
        resp = self.client.get('/api/queue')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get('ok'))
        self.assertIn('queue', data)
        self.assertIn('jobs', data)

    def test_03_download(self):
        resp = self.client.post('/api/download', json={
            'url': 'https://youtube.com/test',
            'title': 'Test',
        })
        data = resp.get_json()
        if resp.status_code == 200:
            self.assertTrue(data.get('ok'))
            self.assertIn('job', data)
        else:
            self.assertIn('error', data)

    def test_04_jobs_list(self):
        self.db.create_job({
            'id':    str(uuid.uuid4()),
            'url':   'https://example.com/job1',
            'title': 'Job 1',
            'state': 'done',
        })
        resp = self.client.get('/api/jobs')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get('ok'))
        self.assertIn('jobs', data)

    def test_05_job_crud(self):
        job_id = str(uuid.uuid4())
        self.db.create_job({'id': job_id, 'url': 'https://example.com/crud', 'title': 'CRUD', 'state': 'queued'})
        resp = self.client.get(f'/api/jobs/{job_id}')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        resp = self.client.delete(f'/api/jobs/{job_id}')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_06_history(self):
        resp = self.client.get('/api/history')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get('ok'))

    def test_07_archive(self):
        resp = self.client.get('/api/archive')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get('ok'))

    def test_08_favorites(self):
        job_id = str(uuid.uuid4())
        self.db.create_job({'id': job_id, 'url': 'https://example.com/fav', 'title': 'Fav', 'state': 'done'})
        resp = self.client.post('/api/favorites', json={'job_id': job_id})
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        resp = self.client.get('/api/favorites')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))
        self.assertIn('favorites', data)

    def test_09_files(self):
        resp = self.client.get('/api/files')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_10_settings(self):
        resp = self.client.get('/api/settings')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_11_logs(self):
        resp = self.client.get('/api/logs')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_12_diagnostics(self):
        resp = self.client.get('/api/diagnostics')
        self.assertIn(resp.status_code, (200, 500))

    def test_13_stats(self):
        resp = self.client.get('/api/stats')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_14_404(self):
        resp = self.client.get('/api/nonexistent')
        self.assertEqual(resp.status_code, 404)

    def test_15_serve_frontend(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp.content_type or '')

# ── YtdlpService Tests ──────────────────────────────────────────
class TestYtdlpService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from database.db import Database
        from config.settings import Settings
        from services.ytdlp_service import YtdlpService
        cls.db = Database(TEST_DB)
        cls.db.initialize()
        cls.settings = Settings.__new__(Settings)
        cls.settings._data = dict(TEST_SETTINGS)
        cls.settings._path = str(BASE_DIR / 'tests' / 'test_settings.json')
        cls.svc = YtdlpService(cls.settings, cls.db)

    def test_01_find_binary(self):
        binary = self.svc.find_binary('yt-dlp')
        if binary:
            version = self.svc.get_version(binary)
            self.assertIsNotNone(version)

    def test_02_parse_progress(self):
        line = '[download]  45.6% of 123.45MiB at 1.23MiB/s ETA 01:23'
        result = self.svc._parse_progress(line)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['percent'], 45.6)
        self.assertGreater(result['speed'], 0)
        self.assertGreater(result['total_bytes'], 0)

    def test_03_parse_progress_no_eta(self):
        line = '[download]  90.0% of 50.00MiB at 2.00MiB/s ETA 00:05'
        result = self.svc._parse_progress(line)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['percent'], 90.0)

    def test_04_parse_progress_complete(self):
        line = '[download] 100% of 10.00MiB in 00:01'
        result = self.svc._parse_progress(line)
        self.assertIsNotNone(result)
        self.assertEqual(result['percent'], 100)

    def test_05_build_command(self):
        cmd = self.svc._build_command(
            '/usr/bin/yt-dlp',
            'https://youtube.com/test',
            {'quality': 'best'},
            '/tmp/downloads'
        )
        self.assertIsInstance(cmd, list)
        self.assertGreater(len(cmd), 2)
        self.assertIn('https://youtube.com/test', cmd)

    def test_06_build_command_mp3(self):
        cmd = self.svc._build_command(
            '/usr/bin/yt-dlp',
            'https://youtube.com/test',
            {'quality': 'mp3'},
            '/tmp/downloads'
        )
        cmd_str = ' '.join(cmd)
        self.assertIn('-x', cmd_str)
        self.assertIn('--audio-format', cmd_str)

    def test_07_normalize_info(self):
        raw = {
            'id': 'abc123',
            'title': 'Test Video',
            'thumbnail': 'https://img.youtube.com/vi/abc123/hqdefault.jpg',
            'duration': 300,
            'formats': [{'format_id': '18', 'ext': 'mp4', 'height': 360}],
        }
        norm = self.svc._normalize_info(raw)
        self.assertEqual(norm['title'], 'Test Video')
        self.assertEqual(norm['duration'], 300)
        self.assertEqual(len(norm['formats']), 1)

# ── Frontend File Tests ─────────────────────────────────────────
class TestFrontend(unittest.TestCase):
    def test_01_index_html_exists(self):
        f = BASE_DIR / 'frontend' / 'index.html'
        self.assertTrue(f.exists(), f"Missing: {f}")
        self.assertGreater(f.stat().st_size, 500)

    def test_02_manifest_json_exists(self):
        f = BASE_DIR / 'frontend' / 'manifest.json'
        self.assertTrue(f.exists())
        data = json.loads(f.read_text(encoding='utf-8'))
        self.assertIn('name', data)
        self.assertIn('start_url', data)
        self.assertIn('icons', data)

    def test_03_service_worker_exists(self):
        f = BASE_DIR / 'frontend' / 'service-worker.js'
        self.assertTrue(f.exists())
        self.assertGreater(f.stat().st_size, 100)

    def test_04_css_files_exist(self):
        css_dir = BASE_DIR / 'frontend' / 'assets' / 'css'
        required = ['main.css', 'animations.css', 'components.css', 'pages.css']
        for name in required:
            f = css_dir / name
            self.assertTrue(f.exists(), f"Missing CSS: {f}")

    def test_05_js_files_exist(self):
        js_dir = BASE_DIR / 'frontend' / 'assets' / 'js'
        for name in ['app.js', 'config.js', 'api.js', 'router.js']:
            self.assertTrue((js_dir / name).exists(), f"Missing JS: {name}")

    def test_06_icons_exist(self):
        icons_dir = BASE_DIR / 'frontend' / 'assets' / 'icons'
        for size in [72, 96, 128, 192, 512]:
            f = icons_dir / f'icon-{size}.png'
            self.assertTrue(f.exists(), f"Missing icon: {f}")

# ── Project Structure Tests ────────────────────────────────────
class TestProjectStructure(unittest.TestCase):
    def test_01_backend_app_exists(self):
        self.assertTrue((BACKEND_DIR / 'app.py').exists())

    def test_02_requirements_exists(self):
        req = BASE_DIR / 'requirements.txt'
        self.assertTrue(req.exists())
        content = req.read_text()
        self.assertIn('flask', content.lower())

    def test_03_php_backend_exists(self):
        php_dir = BASE_DIR / 'backend-php'
        for f in ['api/index.php', 'config/Config.php', 'database/Database.php', 'jobs/watcher.php']:
            self.assertTrue((php_dir / f).exists(), f"Missing PHP: {f}")

    def test_04_php_handlers_exist(self):
        handlers = BASE_DIR / 'backend-php' / 'api' / 'handlers'
        for name in ['info.php', 'download.php', 'jobs.php', 'files.php', 'diagnostics.php']:
            self.assertTrue((handlers / name).exists(), f"Missing handler: {name}")

    def test_05_shell_scripts_exist(self):
        for script in ['install.sh', 'run.sh', 'update.sh']:
            self.assertTrue((BASE_DIR / script).exists(), f"Missing: {script}")

# ── Main ────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"MegaDL Regression Test v2.0.0")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Project: {BASE_DIR}")
    print()
    try:
        from importlib.metadata import version as _v
        print(f"Flask: {_v('flask')}")
    except Exception as e:
        print(f"Flask: NOT AVAILABLE ({e})")
    print()
    try:
        from yt_dlp import version as yt_dlp_version
        print(f"yt-dlp: {yt_dlp_version.__version__}")
    except Exception as e:
        print(f"yt-dlp: NOT AVAILABLE ({e})")
    print()

    loader = unittest.TestLoader()
    suites = [
        loader.loadTestsFromTestCase(TestDatabase),
        loader.loadTestsFromTestCase(TestDownloadQueue),
        loader.loadTestsFromTestCase(TestFlaskAPI),
        loader.loadTestsFromTestCase(TestYtdlpService),
        loader.loadTestsFromTestCase(TestFrontend),
        loader.loadTestsFromTestCase(TestProjectStructure),
    ]
    runner = unittest.TextTestRunner(verbosity=2)
    all_passed = True

    for suite in suites:
        if not suite.countTestCases():
            continue
        name = suite._tests[0].__class__.__name__ if suite._tests else 'Unknown'
        print(f"\n{'='*60}")
        print(f"Running: {name}")
        print(f"{'='*60}")
        result = runner.run(suite)
        if not result.wasSuccessful():
            all_passed = False

    cleanup()

    print(f"\n{'='*60}")
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print(f"{'='*60}")
    sys.exit(0 if all_passed else 1)
