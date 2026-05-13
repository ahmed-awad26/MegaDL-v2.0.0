"""Tests for Website Downloader service (port of Website-downloader)."""

import os
import sys
import json
import uuid
import time
import shutil
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / 'backend'))

from services.website_downloader import (
    WebsiteDownloaderService,
    _find_binary,
    _extract_domain,
    _sanitize_filename,
    WGET_FLAGS,
)


class TestWebsiteHelpers(unittest.TestCase):
    """Test utility functions used by WebsiteDownloader."""

    def test_extract_domain_simple(self):
        self.assertEqual(_extract_domain('https://example.com/page'), 'example.com')

    def test_extract_domain_with_www(self):
        self.assertEqual(_extract_domain('https://www.google.com/search?q=test'), 'www.google.com')

    def test_extract_domain_no_scheme(self):
        self.assertEqual(_extract_domain('example.org'), 'example.org')

    def test_extract_domain_subdomain(self):
        self.assertEqual(_extract_domain('https://blog.example.co.uk/article'), 'blog.example.co.uk')

    def test_sanitize_filename_simple(self):
        self.assertEqual(_sanitize_filename('example.com'), 'example.com')

    def test_sanitize_filename_with_special_chars(self):
        self.assertEqual(_sanitize_filename('https://example.com'), 'https___example.com')

    def test_sanitize_filename_empty(self):
        self.assertEqual(_sanitize_filename(''), 'website')

    def test_sanitize_filename_only_special(self):
        self.assertEqual(_sanitize_filename('///'), 'website')

    def test_wget_flags_present(self):
        flag_str = ' '.join(WGET_FLAGS)
        self.assertIn('--mirror', flag_str)
        self.assertIn('--convert-links', flag_str)
        self.assertIn('--adjust-extension', flag_str)
        self.assertIn('--page-requisites', flag_str)
        self.assertIn('--no-parent', flag_str)

    def test_wget_flags_match_original(self):
        """Verify flags match the original Website-downloader's wget -mkEpnp."""
        # Original uses: wget -mkEpnp --no-if-modified-since <url>
        # Our long-option equivalents:
        short_flags = set('mkEpnp')
        long_to_short = {
            '--mirror': 'm',
            '--convert-links': 'k',
            '--adjust-extension': 'E',
            '--page-requisites': 'p',
            '--no-parent': 'np',
        }
        mapped = set()
        for flag in WGET_FLAGS:
            mapped.update(long_to_short.get(flag, ''))
        self.assertEqual(mapped, short_flags)

    def test_find_binary_wget(self):
        """wget may or may not be installed, but the function should not crash."""
        result = _find_binary('wget')
        # Should return a string (path) or None — never raise
        self.assertIsNone(result) if result is None else self.assertIsInstance(result, str)


class TestWebsiteDownloaderService(unittest.TestCase):
    """Test WebsiteDownloaderService with mocked subprocess."""

    def setUp(self):
        self.test_dir = Path(BASE_DIR / 'tests' / 'test_website_data')
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_db = str(self.test_dir / 'test_website.db')
        self.test_settings = str(self.test_dir / 'test_settings.json')

        # Minimal settings
        settings_data = {'dl_folder': str(self.test_dir / 'downloads')}
        with open(self.test_settings, 'w') as f:
            json.dump(settings_data, f)

        from database.db import Database
        self.db = Database(self.test_db)
        self.db.initialize()

        class FakeSettings:
            def get(self, key, default=None):
                return settings_data.get(key, default)

        self.settings = FakeSettings()
        self.svc = WebsiteDownloaderService(self.settings, self.db)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(str(self.test_dir), ignore_errors=True)

    def test_init(self):
        self.assertIsNotNone(self.svc)
        self.assertEqual(self.svc._processes, {})

    def test_get_websites_dir(self):
        sites_dir = self.svc.get_websites_dir()
        self.assertTrue(sites_dir.exists())
        self.assertTrue(sites_dir.name == 'websites')

    def test_get_websites_dir_creates_parent(self):
        parent = self.svc.get_websites_dir().parent
        self.assertTrue(parent.exists())

    @patch('services.website_downloader._find_binary', return_value='/usr/bin/wget')
    @patch('services.website_downloader.subprocess.Popen')
    def test_start_download_runs_wget(self, mock_popen, mock_find):
        """Verify start_download creates a thread and calls wget."""
        mock_process = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stderr.readline = MagicMock(side_effect=['', ''])
        mock_process.wait = MagicMock()
        mock_process.returncode = 1  # Simulate failure (no actual URL)
        type(mock_process).stdout = PropertyMock(return_value=MagicMock())
        mock_popen.return_value = mock_process

        job_id = str(uuid.uuid4())
        self.db.create_job({
            'id': job_id,
            'url': 'https://example.com',
            'title': 'Test',
            'state': 'queued',
            'options': {},
        })

        on_complete = MagicMock()
        on_error = MagicMock()

        thread = self.svc.start_download(
            job_id, 'https://example.com', {},
            on_complete=on_complete,
            on_error=on_error,
        )
        thread.join(timeout=5)

        mock_find.assert_called_with('wget')
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn('--mirror', cmd)
        self.assertIn('--convert-links', cmd)
        self.assertIn('--page-requisites', cmd)
        self.assertIn('https://example.com', cmd)

    @patch('services.website_downloader._find_binary', return_value=None)
    def test_download_without_wget(self, mock_find):
        """Should report error when wget is not installed."""
        job_id = str(uuid.uuid4())
        self.db.create_job({
            'id': job_id,
            'url': 'https://example.com',
            'title': 'Test',
            'state': 'queued',
            'options': {},
        })

        on_error = MagicMock()
        thread = self.svc.start_download(
            job_id, 'https://example.com', {},
            on_error=on_error,
        )
        thread.join(timeout=5)

        on_error.assert_called_once()
        error_msg = on_error.call_args[0][1]
        self.assertIn('wget not found', error_msg)

    @patch('services.website_downloader._find_binary', return_value=None)
    def test_cancel_job_no_process(self, mock_find):
        """cancel_job should return False when no process is running."""
        result = self.svc.cancel_job('nonexistent-job')
        self.assertFalse(result)


class TestWebsiteAPI(unittest.TestCase):
    """Test the website downloader API endpoints."""

    def setUp(self):
        self.test_dir = Path(BASE_DIR / 'tests' / 'test_website_api')
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(self.test_dir / 'test.db')
        self.settings_path = str(self.test_dir / 'settings.json')

        settings_data = {'dl_folder': str(self.test_dir / 'downloads')}
        with open(self.settings_path, 'w') as f:
            json.dump(settings_data, f)

        from database.db import Database
        self.db = Database(self.db_path)
        self.db.initialize()

        from config.settings import Settings
        self.settings = Settings(Path(self.settings_path))

        from routes.website import website_bp
        from flask import Flask
        self.app = Flask(__name__)
        self.app.config['DB'] = self.db
        self.app.config['SETTINGS'] = self.settings
        self.app.config['QUEUE'] = MagicMock()
        self.app.register_blueprint(website_bp)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        if self.test_dir.exists():
            shutil.rmtree(str(self.test_dir), ignore_errors=True)

    def test_check_endpoint(self):
        resp = self.client.get('/api/website/check')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))

    def test_download_no_url(self):
        resp = self.client.post('/api/website/download', json={})
        data = resp.get_json()
        self.assertFalse(data.get('ok'))
        self.assertIn('URL is required', data.get('error', ''))

    def test_download_empty_url(self):
        resp = self.client.post('/api/website/download', json={'url': ''})
        data = resp.get_json()
        self.assertFalse(data.get('ok'))

    @patch('services.website_downloader._find_binary', return_value=None)
    def test_download_no_wget(self, mock_find):
        resp = self.client.post('/api/website/download', json={'url': 'https://example.com'})
        data = resp.get_json()
        self.assertFalse(data.get('ok'))
        self.assertIn('wget not found', data.get('error', ''))

    def test_status_not_found(self):
        resp = self.client.get('/api/website/download/nonexistent')
        data = resp.get_json()
        self.assertFalse(data.get('ok'))

    def test_check_endpoint_returns_sites_dir(self):
        resp = self.client.get('/api/website/check')
        data = resp.get_json()
        self.assertIn('sites_dir', data)

    def test_log_endpoint(self):
        """Log endpoint should return a list (possibly empty)."""
        resp = self.client.get('/api/website/log/test-job-id')
        data = resp.get_json()
        self.assertTrue(data.get('ok'))


class TestFrontendJS(unittest.TestCase):
    """Verify the website.js frontend file is syntactically valid."""

    def test_website_js_syntax(self):
        js_path = BASE_DIR / 'frontend' / 'assets' / 'js' / 'website.js'
        self.assertTrue(js_path.exists(), 'website.js not found')
        result = subprocess.run(
            ['node', '--check', str(js_path)],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, f'JS syntax error: {result.stderr}')

    def test_api_wrappers_exported(self):
        api_path = BASE_DIR / 'frontend' / 'assets' / 'js' / 'api.js'
        content = api_path.read_text(encoding='utf-8')
        expected_functions = [
            'websiteCheck', 'websiteDownload',
            'websiteStatus', 'websiteLog', 'websiteCancel',
        ]
        for func in expected_functions:
            self.assertIn(func, content, f'{func} not exported in api.js')

    def test_website_module_structure(self):
        js_path = BASE_DIR / 'frontend' / 'assets' / 'js' / 'website.js'
        content = js_path.read_text(encoding='utf-8')
        self.assertIn('MegaDL.WebsiteDownloader', content)
        self.assertIn('startDownload', content)
        self.assertIn('checkHealth', content)
        self.assertIn('pollStatus', content)

    def test_index_html_has_page(self):
        html_path = BASE_DIR / 'frontend' / 'index.html'
        content = html_path.read_text(encoding='utf-8')
        self.assertIn('id="page-website"', content)
        self.assertIn('data-page="website"', content)
        self.assertIn('website.js', content)


if __name__ == '__main__':
    unittest.main()
