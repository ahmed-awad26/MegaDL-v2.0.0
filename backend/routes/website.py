"""MegaDL — routes/website.py
Website downloader: mirror websites via wget and serve as zip."""

import os
import uuid
import logging
from pathlib import Path
from flask import Blueprint, request, send_file
from .ping import ok, err, get_db, get_settings
from services.website_downloader import WebsiteDownloaderService, _find_binary

logger = logging.getLogger('megadl.website')
website_bp = Blueprint('website', __name__)

def get_svc():
    from flask import current_app
    svc = current_app.config.get('WEBSITE_SVC')
    if svc is None:
        svc = WebsiteDownloaderService(get_settings(), get_db())
        current_app.config['WEBSITE_SVC'] = svc
    return svc


@website_bp.route('/api/website/check', methods=['GET'])
def website_check():
    """Check if wget is available and websites dir is writable."""
    wget_path = _find_binary('wget')
    svc = get_svc()
    sites_dir = svc.get_websites_dir()
    writable = os.access(str(sites_dir), os.W_OK) if sites_dir.exists() else False
    return ok({
        'wget_available': wget_path is not None,
        'wget_path': wget_path,
        'sites_dir': str(sites_dir),
        'sites_dir_writable': writable,
    })


@website_bp.route('/api/website/download', methods=['POST'])
def website_download():
    """Start a website download job."""
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return err('URL is required')

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    wget_path = _find_binary('wget')
    if not wget_path:
        return err('wget not found. Install: apt install wget / pkg install wget')

    job_id = str(uuid.uuid4())
    svc = get_svc()
    opts = {'mode': 'website', 'url': url}

    # Create job in DB
    db = get_db()
    db.create_job({
        'id': job_id,
        'url': url,
        'title': f'Website: {url}',
        'state': 'queued',
        'options': opts,
    })
    db.add_log(f'Website download queued: {url}', 'info', job_id)

    # Start download thread (service handles DB updates internally)
    svc.start_download(job_id, url, opts)

    return ok({'job_id': job_id, 'url': url})


@website_bp.route('/api/website/status/<job_id>')
def website_status(job_id):
    """Get status of a website download job."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return err('Job not found')
    return ok({
        'job': job,
        'download_url': f'/api/website/download/{job_id}' if job.get('state') == 'done' else None,
    })


@website_bp.route('/api/website/download/<job_id>')
def website_download_file(job_id):
    """Download the completed website zip."""
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return err('Job not found', 404)
    if job.get('state') != 'done':
        return err('Download not yet completed', 400)

    output_path = job.get('output_path', '')
    if not output_path or not Path(output_path).exists():
        return err('File not found', 404)

    return send_file(
        output_path,
        as_attachment=True,
        download_name=Path(output_path).name,
    )


@website_bp.route('/api/website/cancel/<job_id>', methods=['POST'])
def website_cancel(job_id):
    """Cancel a website download."""
    svc = get_svc()
    svc.cancel_job(job_id)
    return ok({'cancelled': True})


@website_bp.route('/api/website/log/<job_id>')
def website_log(job_id):
    """Get log for a website download job."""
    db = get_db()
    logs = db.get_logs(job_id=job_id)
    return ok({'logs': logs})
