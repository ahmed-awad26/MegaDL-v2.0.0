"""MegaDL — routes/download.py"""

from flask import Blueprint, request
from .ping import ok, err, validate_url, get_queue, get_ytdlp
from services.url_cleaner import UrlCleaner
from services.filehost_service import FileHostService

download_bp = Blueprint('download', __name__)


@download_bp.route('/api/download', methods=['POST'])
def start_download():
    data = request.get_json(force=True) or {}
    url  = data.pop('url', '').strip()

    # Clean URL (strip tracking, resolve shorteners)
    clean = UrlCleaner.prepare_url(url)
    valid, error = validate_url(clean)
    if error:
        return err(error)

    queue = get_queue()
    if not queue:
        return err('Download queue not available', 503)

    opts = {k: v for k, v in data.items()}

    # Auto-detect filehost URLs that yt-dlp may not handle well
    platform = FileHostService.detect_platform(clean)
    is_filehost = platform not in ('unknown', 'direct')
    if is_filehost:
        opts['mode'] = 'filehost'
        opts['filehost_platform'] = platform

    try:
        job = queue.enqueue(clean, opts)
        return ok({'job': job, 'job_id': job['id'], 'platform': platform if is_filehost else 'ytdlp'})
    except Exception as e:
        return err(str(e), 500)


@download_bp.route('/api/batch', methods=['POST'])
def start_batch():
    data = request.get_json(force=True) or {}
    urls = data.get('urls', [])
    if not urls:
        return err('No URLs provided')

    queue = get_queue()
    if not queue:
        return err('Download queue not available', 503)

    opts = {k: v for k, v in data.items() if k != 'urls'}

    clean_urls = []
    for url in urls:
        raw = str(url).strip()
        cleaned = UrlCleaner.prepare_url(raw)
        valid, error = validate_url(cleaned)
        if valid:
            clean_urls.append(cleaned)

    if not clean_urls:
        return err('No valid URLs after validation')

    try:
        jobs = queue.enqueue_batch(clean_urls, opts)
        return ok({'jobs': jobs, 'count': len(jobs)})
    except Exception as e:
        return err(str(e), 500)
