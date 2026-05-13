#!/usr/bin/env python3
"""Quick smoke test against running Flask server."""
__test__ = False  # prevent pytest collection (it's a standalone script)
import urllib.request, json, sys

BASE = 'http://127.0.0.1:5001'

def test(path, expect_json=True):
    try:
        r = urllib.request.urlopen(f'{BASE}{path}', timeout=5)
        if expect_json:
            data = json.loads(r.read())
            ok = data.get('ok', False)
            print(f'GET {path:25s} {r.status} ok={ok}')
        else:
            body = r.read()
            print(f'GET {path:25s} {r.status} {len(body)} bytes')
        return True
    except Exception as e:
        print(f'GET {path:25s} FAILED - {e}')
        return False

test('/api/ping')
test('/api/queue')
test('/api/jobs')
test('/api/history')
test('/api/archive')
test('/api/favorites')
test('/api/files')
test('/api/settings')
test('/api/logs')
test('/api/stats')
test('/api/diagnostics')
test('/', expect_json=False)
test('/index.html', expect_json=False)
test('/manifest.json', expect_json=False)
test('/service-worker.js', expect_json=False)
test('/assets/css/main.css', expect_json=False)
test('/assets/js/app.js', expect_json=False)
print('Smoke test complete')
