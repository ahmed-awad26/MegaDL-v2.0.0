"""MegaDL Launcher — starts backend server and opens browser."""
import subprocess, sys, os, time, threading, webbrowser
from pathlib import Path

BASE = Path(__file__).parent

PYTHON = sys.executable

def run_server():
    backend_dir = BASE / 'backend'
    cmd = [PYTHON, 'app.py']
    subprocess.Popen(cmd, cwd=str(backend_dir),
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0)

def open_browser():
    time.sleep(5)
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    print('=' * 50)
    print('  MegaDL — Launcher')
    print('=' * 50)
    print()
    print('>> Starting backend server on http://127.0.0.1:5000')
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=open_browser, daemon=True).start()
    print('>> Opening browser in 5 seconds...')
    print()
    print('  Press Ctrl+C to stop')
    print('=' * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down...')
        sys.exit(0)
