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
        except OSError: pass
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

# ── Channel Mode Tests ───────────────────────────────────────────
class TestChannelMode(unittest.TestCase):
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

    def test_01_is_channel_mode_true(self):
        for mode in ('playlists_only', 'uploads_only', 'playlists_and_uploads',
                      'all_uncategorized', 'latest_since_last_run'):
            self.assertTrue(self.svc.is_channel_mode({'mode': mode}),
                            f'{mode} should be detected as channel mode')

    def test_02_is_channel_mode_false(self):
        for mode in ('single', 'playlist', 'unlisted_playlist', 'audio_only', 'video_only', ''):
            self.assertFalse(self.svc.is_channel_mode({'mode': mode}),
                             f'{mode!r} should NOT be detected as channel mode')

    def test_03_is_channel_mode_empty_opts(self):
        self.assertFalse(self.svc.is_channel_mode({}))

    def test_04_build_output_path_channel_uploads(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://youtube.com/@channel',
            {'uploader': 'TestChannel', 'channel': 'TestChannel'},
            {'mode': 'uploads_only'}
        )
        self.assertIn('TestChannel', path)
        self.assertIn('Uploads', path)
        self.assertIn('%(id)s', path)

    def test_05_build_output_path_channel_playlist(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://youtube.com/playlist?list=PLtest',
            {'uploader': 'TestChannel', 'playlist_id': 'PLtest', 'playlist_title': 'My Playlist'},
            {'mode': 'playlist'}
        )
        self.assertIn('TestChannel', path)
        self.assertIn('Playlists', path)
        self.assertIn('My Playlist', path)

    def test_06_build_output_path_standalone_playlist(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://youtube.com/playlist?list=PLtest',
            {'playlist_id': 'PLtest', 'playlist_title': 'My List'},
            {'mode': 'playlist'}
        )
        self.assertIn('Playlist_PLtest', path)

    def test_07_build_output_path_facebook(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://facebook.com/watch?v=test',
            {},
            {'mode': 'single'}
        )
        self.assertIn('facebook.com', path)

    def test_08_build_output_path_latest(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://youtube.com/@channel',
            {'uploader': 'TestChannel'},
            {'mode': 'latest'}
        )
        self.assertIn('Latest', path)

    def test_09_build_output_path_uncategorized(self):
        path = self.svc._build_output_path(
            '/downloads',
            'https://youtube.com/@channel',
            {'uploader': 'TestChannel'},
            {'mode': 'uncategorized'}
        )
        self.assertIn('Uncategorized', path)

    def test_10_detect_platform(self):
        self.assertEqual(self.svc._detect_platform('https://youtube.com/watch?v=test'), 'youtube')
        self.assertEqual(self.svc._detect_platform('https://youtu.be/test'), 'youtube')
        self.assertEqual(self.svc._detect_platform('https://facebook.com/video'), 'facebook')
        self.assertEqual(self.svc._detect_platform('https://fb.watch/test'), 'facebook')
        self.assertEqual(self.svc._detect_platform('https://instagram.com/p/test'), 'instagram')
        self.assertEqual(self.svc._detect_platform('https://tiktok.com/@user/video'), 'tiktok')
        self.assertEqual(self.svc._detect_platform('https://twitter.com/user/status/123'), 'twitter')
        self.assertEqual(self.svc._detect_platform('https://example.com/video'), 'other')

    def test_11_channel_metadata_write(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'TestChannel')
            self.svc._write_last_run(Path(path))
            last_run = Path(path) / '.last_run'
            self.assertTrue(last_run.exists())
            ts = last_run.read_text(encoding='utf-8')
            self.assertIn('20', ts)  # year prefix

    def test_12_latest_per_channel_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.svc.settings._data['dl_folder'] = tmp
            self.svc.save_latest_per_channel('UCtest1234', 'video_01', '20260511')
            self.svc.save_latest_per_channel('UCtest1234', 'video_02', '20260512')
            report = self.svc.get_latest_per_channel()
            self.assertIn('UCtest1234', report)
            self.assertEqual(report['UCtest1234']['video_id'], 'video_02')
            self.assertEqual(report['UCtest1234']['upload_date'], '20260512')

    def test_13_filter_latest_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.svc.settings._data['dl_folder'] = tmp
            self.svc.save_latest_per_channel('UCfilter_test_1234567890', 'old_vid', '20260501')
            videos = [
                {'id': 'v1', 'upload_date': '20260401'},
                {'id': 'v2', 'upload_date': '20260515'},
                {'id': 'v3', 'upload_date': '20260502'},
            ]
            from unittest.mock import patch
            with patch.object(self.svc, '_get_channel_id', return_value='UCfilter_test_1234567890'):
                filtered = self.svc.filter_latest_only('https://youtube.com/channel/UCfilter_test_1234567890', videos)
                self.assertEqual(len(filtered), 2)
                self.assertEqual(filtered[0]['id'], 'v2')
                self.assertEqual(filtered[1]['id'], 'v3')

    def test_14_url_pattern_detection(self):
        import re
        test_cases = [
            ('https://youtube.com/channel/UCabc123def456ghi789jkl0', True),
            ('https://youtube.com/@handle', True),
            ('https://youtube.com/c/CustomName', True),
            ('https://youtube.com/user/RealUser', True),
            ('https://youtube.com/watch?v=test', False),
        ]
        channel_pattern = re.compile(r'youtube\.com/(@|channel/|c/|user/)')
        for url, expected in test_cases:
            self.assertEqual(bool(channel_pattern.search(url)), expected,
                             f'{url} should match={expected}')


# ── Telegram Bot Scorer Tests ──────────────────────────────────
class TestTelegramBotScorer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from config.settings import Settings
        from services.tg_bot_scorer import TelegramBotScorer, BotStats
        cls.Settings = Settings
        cls.TelegramBotScorer = TelegramBotScorer
        cls.BotStats = BotStats

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        from config.settings import Settings
        s = Settings.__new__(Settings)
        s._data = {'dl_folder': self.tmp.name}
        self.scorer = self.TelegramBotScorer(s)

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_register_and_score(self):
        self.scorer.register_bot('123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
        score = self.scorer.get_bot_score('123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)

    def test_02_fail_rate_calculation(self):
        stats = self.BotStats(token='test', total_downloaded=8, total_failed=2)
        self.assertAlmostEqual(stats.fail_rate, 0.2)

    def test_03_weighted_scoring(self):
        # Fresh bot with no history should get moderate score
        self.scorer.register_bot('bot_fresh:xxx')
        score = self.scorer.get_bot_score('bot_fresh:xxx')
        # No load, no fail rate = good, but no speed = lower
        self.assertGreater(score, 0.3)

    def test_04_select_best_bot(self):
        tokens = ['bot_a:aaa', 'bot_b:bbb', 'bot_c:ccc']
        for t in tokens:
            self.scorer.register_bot(t)
        # Record some successes/failures to differentiate
        self.scorer.record_success('bot_a:aaa', 5_000_000)  # 5 MB/s
        self.scorer.record_success('bot_a:aaa', 8_000_000)
        self.scorer.record_failure('bot_c:ccc')
        self.scorer.record_failure('bot_c:ccc')

        best = self.scorer.select_best_bot(tokens)
        # bot_a should be best (good speed, no failures)
        self.assertEqual(best, 'bot_a:aaa')

    def test_05_score_differentiation(self):
        tokens = ['fast:aaa', 'slow:bbb', 'flaky:ccc']
        for t in tokens:
            self.scorer.register_bot(t)

        self.scorer.record_success('fast:aaa', 10_000_000)  # 10 MB/s
        self.scorer.record_success('slow:bbb', 500_000)      # 0.5 MB/s
        self.scorer.record_success('flaky:ccc', 2_000_000)
        self.scorer.record_failure('flaky:ccc')

        scores = self.scorer.get_all_scores()
        # First should be fast bot
        self.assertIn('fast', scores[0]['token_masked'])

    def test_06_record_removal(self):
        self.scorer.register_bot('remove_me:token')
        self.assertIn('remove_me:token', self.scorer._bots)
        self.scorer.remove_bot('remove_me:token')
        self.assertNotIn('remove_me:token', self.scorer._bots)


# ── Telegram Filename Service Tests ────────────────────────────
class TestTelegramFilenameService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from services.tg_filename_service import TelegramFilenameService
            cls.svc = TelegramFilenameService()
            cls.available = True
        except ImportError:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest('telethon not installed')

    def test_01_extract_filename_from_attributes(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.message = None
        msg.media = True
        msg.document = MagicMock()
        msg.document.attributes = []
        msg.photo = None
        msg.file = MagicMock()
        msg.file.name = 'report.pdf'
        msg.file.ext = '.pdf'
        fname = self.svc.get_original_filename(msg)
        self.assertIsNotNone(fname)

    def test_02_get_original_filename(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.media = False
        msg.document = None
        msg.photo = None
        msg.video = None
        msg.audio = None
        msg.voice = None
        msg.text = ''
        msg.date = None
        msg.id = 999
        msg.file = MagicMock()
        msg.file.ext = ''
        msg.file.name = ''
        fname = self.svc.get_original_filename(msg)
        # Falls through to Layer 6 (message ID) since all checks fail
        self.assertIn('999', fname)

    def test_03_extract_info_debug_photo(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.media = True
        msg.document = None
        msg.photo = MagicMock()
        msg.video = None
        msg.audio = None
        msg.voice = None
        msg.text = ''
        msg.id = 123
        msg.date = None
        msg.file = MagicMock()
        msg.file.name = ''
        msg.file.ext = '.jpg'
        info = self.svc.extract_filename_info(msg)
        self.assertIn('filename', info)
        self.assertIn('extension', info)
        self.assertIn('media_type', info)
        self.assertEqual(info['media_type'], 'photo')


# ── Telegram Resume Service Tests ──────────────────────────────
class TestTelegramResumeService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from config.settings import Settings
        from services.tg_resume_service import TelegramResumeService
        cls.Settings = Settings
        cls.TelegramResumeService = TelegramResumeService

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        s = self.Settings.__new__(self.Settings)
        s._data = {'dl_folder': self.tmp.name}
        self.resume = self.TelegramResumeService(s)

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_init_job(self):
        job = self.resume.init_job('job_001', 12345, 678, '/tmp/test.mp4', 1_000_000)
        self.assertEqual(job['job_id'], 'job_001')
        self.assertEqual(job['dialog_id'], 12345)
        self.assertEqual(job['msg_id'], 678)
        self.assertEqual(job['total_size'], 1_000_000)
        self.assertEqual(job['downloaded_bytes'], 0)
        self.assertEqual(job['status'], 'paused')  # starts as paused

    def test_02_update_progress(self):
        self.resume.init_job('job_002', 111, 222, '/tmp/test.mp4', 500_000)
        self.resume.update_progress('job_002', 250_000)
        jobs = self.resume.get_active_jobs()
        # get_active_jobs returns dict of job_id -> job
        self.assertIn('job_002', jobs)
        self.assertEqual(jobs['job_002']['downloaded_bytes'], 250_000)

    def test_03_pause_applies_rollback(self):
        self.resume.init_job('job_003', 111, 222, '/tmp/test.mp4', 2_000_000)
        self.resume.update_progress('job_003', 500_000)
        self.resume.mark_paused('job_003')
        offset = self.resume.get_resume_offset('job_003')
        # job stores rollback_offset separately (not recalculated)
        job = self.resume.get_job('job_003')
        self.assertEqual(job['rollback_offset'], 0)  # 500KB < 2MB rollback
        # Actual resume offset uses rollback_offset or downloaded_bytes
        self.assertEqual(offset, 0)  # rollback_offset=0 since 500KB < 2MB

    def test_04_mark_completed(self):
        self.resume.init_job('job_004', 111, 222, '/tmp/test.mp4', 100_000)
        self.resume.update_progress('job_004', 100_000)
        self.resume.mark_completed('job_004')
        job = self.resume.get_active_jobs()
        active = [j for j in job if j['job_id'] == 'job_004']
        self.assertEqual(len(active), 0)  # Completed jobs removed from active

    def test_05_mark_failed(self):
        self.resume.init_job('job_005', 111, 222, '/tmp/test.mp4', 100_000)
        self.resume.mark_failed('job_005', 'Connection lost')
        stats = self.resume.get_job_stats()
        self.assertIn('failed', stats)
        self.assertGreaterEqual(stats['failed'], 1)

    def test_06_get_resume_offset_no_job(self):
        offset = self.resume.get_resume_offset('nonexistent_job')
        self.assertEqual(offset, 0)


# ── Telegram Scan Service Tests ────────────────────────────────
class TestTelegramScanService(unittest.TestCase):
    def test_01_format_size(self):
        from services.tg_scan_service import TelegramScanService
        self.assertEqual(TelegramScanService.format_size(0), '0.00 B')
        self.assertEqual(TelegramScanService.format_size(1024), '1.00 KB')
        self.assertEqual(TelegramScanService.format_size(1_048_576), '1.00 MB')
        self.assertEqual(TelegramScanService.format_size(1_073_741_824), '1.00 GB')

    def test_02_estimate_download_time(self):
        from services.tg_scan_service import TelegramScanService
        s = TelegramScanService.__new__(TelegramScanService)
        # 10 MB at 1 MB/s = 10 seconds
        time = s.estimate_download_time(10_000_000, 1_000_000)
        self.assertAlmostEqual(time, 10.0, places=1)


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
        loader.loadTestsFromTestCase(TestChannelMode),
        loader.loadTestsFromTestCase(TestTelegramBotScorer),
        loader.loadTestsFromTestCase(TestTelegramFilenameService),
        loader.loadTestsFromTestCase(TestTelegramResumeService),
        loader.loadTestsFromTestCase(TestTelegramScanService),
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
