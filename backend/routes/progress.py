"""
MegaDL — routes/progress.py
Server-Sent Events endpoint for live download progress.
Streams job progress updates to connected clients.
"""

import time
import json
import logging
from flask import Blueprint, Response, stream_with_context
from .ping import get_db

logger = logging.getLogger('megadl.progress')

progress_bp = Blueprint('progress', __name__)


@progress_bp.route('/api/progress')
def stream_progress():
    """SSE endpoint: streams job progress as JSON events."""

    def generate():
        db = get_db()
        last_state = {}

        while True:
            try:
                active = db.get_active_jobs()
                data = []
                for job in active:
                    # Parse video tracking info from options JSON
                    opts_raw = job.get('options', '{}')
                    opts = {}
                    if isinstance(opts_raw, str):
                        try: opts = json.loads(opts_raw)
                        except (json.JSONDecodeError, TypeError): pass
                    elif isinstance(opts_raw, dict):
                        opts = opts_raw
                    data.append({
                        'id':         job.get('id', ''),
                        'state':      job.get('state', ''),
                        'progress':   job.get('progress', 0),
                        'speed':      job.get('speed', 0),
                        'eta':        job.get('eta', 0),
                        'title':      job.get('title', ''),
                        'url':        job.get('url', ''),
                        'total_bytes': job.get('total_bytes', 0),
                        'downloaded': job.get('downloaded', 0),
                        'fragment':   job.get('fragment', ''),
                        'error':      job.get('error', ''),
                        'current_video_title': opts.get('_video_title', ''),
                        'current_video_index': opts.get('_video_index', 0),
                        'total_videos': opts.get('_video_total', 0),
                    })

                state_key = json.dumps(data, sort_keys=True)
                if state_key != last_state.get('key'):
                    yield f"data: {json.dumps({'jobs': data})}\n\n"
                    last_state['key'] = state_key

                time.sleep(0.5)

            except GeneratorExit:
                break
            except Exception:
                yield f"data: {json.dumps({'error': 'internal error'})}\n\n"
                time.sleep(2)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@progress_bp.route('/api/progress/<job_id>')
def stream_job_progress(job_id):
    """SSE endpoint for a single job's progress."""

    def generate():
        db = get_db()
        last_state = {}

        while True:
            try:
                job = db.get_job(job_id)
                if not job:
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break

                state_key = json.dumps(job, sort_keys=True, default=str)
                if state_key != last_state.get('key'):
                    yield f"data: {json.dumps({'job': job}, default=str)}\n\n"
                    last_state['key'] = state_key

                if job.get('state') in ('done', 'error', 'cancelled'):
                    break

                time.sleep(0.3)

            except GeneratorExit:
                break
            except Exception:
                time.sleep(2)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )
