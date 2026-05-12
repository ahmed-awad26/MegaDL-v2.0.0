#!/usr/bin/env python3
"""
MegaDL — Flask Backend (app.py)
Main entry point: wires all services, registers blueprints, starts server.
"""

import os
import sys
import platform
import logging
from pathlib import Path
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# ── Path setup ────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
ROOT_DIR     = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'

# Runtime data goes OUTSIDE the project — never inside the repo
def _get_data_dir() -> Path:
    system = platform.system().lower()
    if os.path.exists('/sdcard'):               # Android / Termux
        return Path('/sdcard/Download/MegaDL')
    if 'win' in system:                          # Windows
        return Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming')) / 'MegaDL'
    if system == 'darwin':                       # macOS
        return Path.home() / 'Library' / 'Application Support' / 'MegaDL'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'megadl'

DATA_DIR = _get_data_dir()
LOGS_DIR = DATA_DIR / 'logs'

# Ensure runtime directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / 'database').mkdir(parents=True, exist_ok=True)
(DATA_DIR / 'config').mkdir(parents=True, exist_ok=True)

# Add backend to path
sys.path.insert(0, str(BASE_DIR))

# ── Create Flask app ──────────────────────────────────────────
app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path='',
)

# ── CORS ──────────────────────────────────────────────────────
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOGS_DIR / 'app.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger('megadl')

# ── Config ────────────────────────────────────────────────────
from config.settings import Settings
settings = Settings(DATA_DIR / 'config' / 'settings.json')

# ── Database ──────────────────────────────────────────────────
from database.db import Database
db = Database(DATA_DIR / 'database' / 'megadl.db')
db.initialize()

# ── Services ──────────────────────────────────────────────────
from services.ytdlp_service import YtdlpService
from services.filehost_service import FileHostService
from jobs.queue import DownloadQueue

ytdlp_svc = YtdlpService(settings, db)
filehost_svc = FileHostService(settings, db)
queue = DownloadQueue(ytdlp_svc, db, settings, filehost_service=filehost_svc)

# Store references for blueprints
app.config['DB']       = db
app.config['SETTINGS'] = settings
app.config['BASE_DIR'] = BASE_DIR
app.config['LOGGER']   = logger
app.config['YTDLP']    = ytdlp_svc
app.config['QUEUE']    = queue
app.config['FILEHOST_SERVICE'] = filehost_svc

# Lazy-init for telegram service
app.config['TELEGRAM_SERVICE'] = None

# ── Register blueprints ───────────────────────────────────────
from routes.ping        import ping_bp
from routes.info        import info_bp
from routes.download    import download_bp
from routes.jobs        import jobs_bp
from routes.history     import history_bp
from routes.archive     import archive_bp
from routes.favorites   import favorites_bp
from routes.failed_links import failed_bp
from routes.files_api   import files_bp
from routes.settings_api import settings_bp
from routes.logs_api    import logs_bp
from routes.diagnostics_api import diag_bp
from routes.stats       import stats_bp
from routes.telegram    import telegram_bp
from routes.dependencies_api import deps_bp
from routes.progress import progress_bp
from routes.youtube import youtube_bp
from routes.ytdlp_update import ytdlp_update_bp
from routes.api_keys import api_keys_bp
from routes.ytdlp_features import ytdlp_features_bp
from routes.filehost import filehost_bp

app.register_blueprint(ping_bp)
app.register_blueprint(info_bp)
app.register_blueprint(download_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(history_bp)
app.register_blueprint(archive_bp)
app.register_blueprint(failed_bp)
app.register_blueprint(favorites_bp)
app.register_blueprint(files_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(diag_bp)
app.register_blueprint(progress_bp)
app.register_blueprint(deps_bp)
app.register_blueprint(telegram_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(youtube_bp)
app.register_blueprint(ytdlp_update_bp)
app.register_blueprint(api_keys_bp)
app.register_blueprint(ytdlp_features_bp)
app.register_blueprint(filehost_bp)

# ── Queue compatibility endpoint ─────────────────────────────
@app.route('/api/queue', methods=['GET'])
def api_queue():
    """Compatibility endpoint: mirrors /api/jobs for frontend queue views."""
    try:
        data = db.get_jobs(state_filter='all')
        return jsonify({
            "ok": True,
            "queue": data,
            "jobs": data
        })
    except Exception as e:
        logger.exception('Queue endpoint error')
        return jsonify({
            "ok": False,
            "queue": [],
            "jobs": [],
            "error": str(e)
        }), 500

# ── Serve frontend ────────────────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and (FRONTEND_DIR / path).exists():
        return send_from_directory(str(FRONTEND_DIR), path)
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

# ── Error handlers ────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    from flask import request
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found', 'ok': False}), 404
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

@app.errorhandler(500)
def server_error(e):
    logger.exception('Internal server error')
    return jsonify({'error': 'Internal server error', 'ok': False}), 500

# ── Worker auto-start ─────────────────────────────────────────
def _start_worker():
    """Start the download queue scheduler in a background thread."""
    try:
        queue.start()
        logger.info('[WORKER] Download queue scheduler started')
    except Exception as e:
        logger.exception(f'[WORKER] Failed to start queue: {e}')

# ── Main ──────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('MEGADL_PORT', 5000))
    host = os.environ.get('MEGADL_HOST', '0.0.0.0')
    debug = os.environ.get('MEGADL_DEBUG', '0') == '1'

    logger.info(f'MegaDL starting on {host}:{port}')
    logger.info(f'Frontend: {FRONTEND_DIR}')
    logger.info(f'Database: {DATA_DIR / "database" / "megadl.db"}')
    logger.info(f'Download queue: {queue.max_parallel} parallel slots')

    # ── Start-up diagnostics ──────────────────────────────────
    dl_folder = settings.get('dl_folder', '')
    logger.info(f'[DIAG] Download folder: {dl_folder}')
    logger.info(f'[DIAG] DL folder exists: {os.path.exists(dl_folder) if dl_folder else "N/A"}')
    dl_writable = os.access(dl_folder, os.W_OK) if (dl_folder and os.path.exists(dl_folder)) else False
    logger.info(f'[DIAG] DL folder writable: {dl_writable}')
    if dl_folder:
        contents = os.listdir(dl_folder) if os.path.exists(dl_folder) else []
        logger.info(f'[DIAG] DL folder contents ({len(contents)} items)')
    temp_dir = settings.get('temp_dir', '')
    logger.info(f'[DIAG] Temp folder: {temp_dir}')
    platform_info = platform.uname() if hasattr(platform, 'uname') else str(platform.platform())
    logger.info(f'[DIAG] Platform: {platform_info}')
    is_termux = os.path.exists('/data/data/com.termux')
    is_android = os.path.exists('/sdcard')
    logger.info(f'[DIAG] Termux: {is_termux}, Android: {is_android}')
    logger.info(f'[DIAG] yt-dlp: {YtdlpService.find_binary("yt-dlp")}')
    logger.info(f'[DIAG] ffmpeg:  {YtdlpService.find_binary("ffmpeg")}')

    # Start background worker
    _start_worker()

    # Disable dotenv loading (broken python-dotenv package on Python 3.14)
    os.environ['FLASK_SKIP_DOTENV'] = '1'
    app.run(host=host, port=port, debug=debug, threaded=True)
