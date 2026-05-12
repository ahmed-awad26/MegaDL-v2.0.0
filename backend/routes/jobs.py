"""MegaDL — routes/jobs.py"""

from pathlib import Path
import os
import mimetypes
from flask import Blueprint, request, send_file, jsonify
from .ping import ok, err, get_db, get_queue, get_settings

jobs_bp = Blueprint('jobs', __name__)


@jobs_bp.route('/api/jobs')
def list_jobs():
    db = get_db()
    sort   = request.args.get('sort',   'date_desc')
    filter_ = request.args.get('filter', 'all')
    q      = request.args.get('q',      '')
    jobs   = db.get_jobs(state_filter=filter_, sort=sort, q=q)
    return ok({'jobs': jobs})


@jobs_bp.route('/api/jobs/<job_id>')
def get_job(job_id):
    db  = get_db()
    job = db.get_job(job_id)
    if not job:
        return err('Job not found', 404)
    return ok({'job': job})


@jobs_bp.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    db    = get_db()
    queue = get_queue()
    if queue:
        queue.cancel_job(job_id)
    db.delete_job(job_id)
    return ok({'deleted': job_id})


@jobs_bp.route('/api/jobs/<job_id>/download')
def download_job_file(job_id):
    """Return the output file for a completed job.

    If the file exists locally on disk, return its metadata
    (path, size, exists=true) so the frontend can open the local
    file directly instead of triggering a redundant HTTP download.
    On Android this prevents the spurious 'Download File' notification.

    Falls back to Flask send_file only if the file doesn't exist
    on the local filesystem (cross-device remote access).
    """
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return err('Job not found', 404)

    output_path = job.get('output_path', '')
    if not output_path:
        return err('No output file for this job', 404)

    settings = get_settings()
    base = Path(settings.get('dl_folder', './downloads'))
    target = Path(output_path)
    if not target.is_absolute():
        target = (base / output_path).resolve()
    else:
        target = target.resolve()

    try:
        target.relative_to(base.resolve())
    except ValueError:
        return err('Access denied', 403)

    # ── File exists locally → return metadata only ────────────
    if target.is_file():
        stat = target.stat()
        mime, _ = mimetypes.guess_type(str(target))
        return ok({
            'file': {
                'exists':    True,
                'path':      str(target),
                'name':      target.name,
                'size':      stat.st_size,
                'mime':      mime or 'application/octet-stream',
                'modified':  stat.st_mtime,
            },
            '_note': 'File exists locally — open directly, do NOT download via HTTP',
        })

    # ── File not on disk → return 404 with diagnostics ────────
    dl_folder = str(base.resolve())
    return err(
        f'File not found on disk: {output_path}. '
        f'Checked: {target}. '
        f'DL folder exists: {base.exists()}, '
        f'DL folder contents: {os.listdir(dl_folder) if base.exists() else "N/A"}',
        404
    )


@jobs_bp.route('/api/jobs/<job_id>/pause', methods=['POST'])
def pause_job(job_id):
    queue = get_queue()
    if not queue:
        return err('Queue not available', 503)
    ok_ = queue.pause_job(job_id)
    return ok({'paused': ok_})


@jobs_bp.route('/api/jobs/<job_id>/resume', methods=['POST'])
def resume_job(job_id):
    queue = get_queue()
    if not queue:
        return err('Queue not available', 503)
    ok_ = queue.resume_job(job_id)
    return ok({'resumed': ok_})


@jobs_bp.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    queue = get_queue()
    if not queue:
        return err('Queue not available', 503)
    ok_ = queue.cancel_job(job_id)
    return ok({'cancelled': ok_})


@jobs_bp.route('/api/jobs/<job_id>/retry', methods=['POST'])
def retry_job(job_id):
    queue = get_queue()
    if not queue:
        return err('Queue not available', 503)
    ok_ = queue.retry_job(job_id)
    return ok({'retried': ok_})


@jobs_bp.route('/api/jobs/<job_id>/logs')
def job_logs(job_id):
    db   = get_db()
    logs = db.get_logs(job_id=job_id)
    text = '\n'.join(f'[{l["time"]}] {l["message"]}' for l in logs)
    return ok({'logs': text, 'entries': logs})


@jobs_bp.route('/api/jobs/pause-all', methods=['POST'])
def pause_all():
    queue = get_queue()
    if queue:
        queue.pause_all()
    return ok()


@jobs_bp.route('/api/jobs/resume-all', methods=['POST'])
def resume_all():
    queue = get_queue()
    if queue:
        queue.resume_all()
    return ok()


@jobs_bp.route('/api/jobs/cancel-all', methods=['POST'])
def cancel_all():
    queue = get_queue()
    if queue:
        queue.cancel_all()
    return ok()
