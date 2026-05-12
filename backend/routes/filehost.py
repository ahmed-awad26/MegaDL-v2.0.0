"""MegaDL — routes/filehost.py
File hosting download + URL cleaning endpoints."""

import os
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify
from .ping import ok, err, get_db, get_settings
from services.url_cleaner import UrlCleaner
from services.filehost_service import FileHostService

logger = logging.getLogger('megadl.filehost')
filehost_bp = Blueprint('filehost', __name__)


def get_fh():
    from flask import current_app
    svc = current_app.config.get('FILEHOST_SERVICE')
    if svc is None:
        svc = FileHostService(get_settings(), get_db())
        current_app.config['FILEHOST_SERVICE'] = svc
    return svc


@filehost_bp.route('/api/url/clean', methods=['POST'])
def url_clean():
    """Clean URLs: strip tracking params, resolve short URLs."""
    data = request.get_json(force=True) or {}
    urls = data.get('urls', [])
    resolve = data.get('resolve_short', True)
    if isinstance(urls, str):
        urls = [urls]
    cleaned = UrlCleaner.batch_prepare(urls, resolve_short=resolve)
    return ok({'cleaned': cleaned, 'count': len(cleaned)})


@filehost_bp.route('/api/url/info', methods=['POST'])
def url_info():
    """Get info about URLs (domain, host type, file ext)."""
    data = request.get_json(force=True) or {}
    urls = data.get('urls', [])
    if isinstance(urls, str):
        urls = [urls]
    info = [UrlCleaner.get_url_info(u) for u in urls]
    return ok({'info': info})


@filehost_bp.route('/api/url/preview', methods=['POST'])
def url_preview():
    """Preview a downloadable file (name, size, type). Only for direct URLs."""
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return err('URL required')

    try:
        import requests
        resp = requests.head(url, allow_redirects=True, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0'})
        content_type = resp.headers.get('Content-Type', '')
        content_length = resp.headers.get('Content-Length', '0')
        content_disposition = resp.headers.get('Content-Disposition', '')
        filename = url.split('/')[-1].split('?')[0]

        if content_disposition and 'filename=' in content_disposition:
            import re
            fm = re.search(r'filename[^;=\n]*=((["\']).*?\2|[^;\n]*)', content_disposition)
            if fm:
                filename = fm.group(1).strip('"\' ')

        is_text = content_type.startswith('text/')
        is_pdf = content_type == 'application/pdf'
        is_archive = any(ct in content_type for ct in
                        ['application/zip', 'application/x-rar', 'application/gzip',
                         'application/x-7z-compressed', 'application/x-tar'])

        return ok({
            'filename': filename,
            'size': int(content_length) if content_length.isdigit() else 0,
            'content_type': content_type,
            'is_text': is_text,
            'is_pdf': is_pdf,
            'is_archive': is_archive,
            'previewable': is_text or is_pdf,
        })
    except Exception as e:
        return ok({'filename': url.split('/')[-1], 'size': 0, 'previewable': False, 'error': str(e)})


@filehost_bp.route('/api/url/preview-content', methods=['POST'])
def url_preview_content():
    """Fetch text/plain content for preview."""
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return err('URL required')
    try:
        import requests
        resp = requests.get(url, timeout=15,
                            headers={'User-Agent': 'Mozilla/5.0'})
        content_type = resp.headers.get('Content-Type', '')
        is_text = content_type.startswith('text/')
        is_pdf = content_type == 'application/pdf'

        if is_text:
            text = resp.text[:5000]
            return ok({'content': text, 'content_type': content_type, 'truncated': len(resp.text) > 5000})
        elif is_pdf:
            return ok({'content': None, 'content_type': 'application/pdf',
                       'pdf_base64': None, 'note': 'PDF preview not available in browser'})
        else:
            return ok({'content': None, 'content_type': content_type, 'note': 'Binary file, cannot preview'})
    except Exception as e:
        return err(str(e))


@filehost_bp.route('/api/filehost/download', methods=['POST'])
def filehost_download():
    """Start a filehost download as a regular job."""
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return err('URL required')

    from jobs.queue import DownloadQueue
    from flask import current_app

    # Detect platform for proper job options
    platform = FileHostService.detect_platform(url)

    queue = current_app.config.get('QUEUE')
    job = queue.enqueue(
        url=url,
        opts={
            'mode': 'filehost',
            'filehost_platform': platform,
        },
    )
    return ok({'job': job, 'platform': platform})
