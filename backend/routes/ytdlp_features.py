"""MegaDL — routes/ytdlp_features.py
YouTube Uncategorized + Latest-Only endpoints."""

from flask import Blueprint, request, jsonify
from .ping import ok, err, get_ytdlp

ytdlp_features_bp = Blueprint('ytdlp_features', __name__)


@ytdlp_features_bp.route('/api/ytdlp/uncategorized', methods=['GET'])
def ytdlp_uncategorized():
    """Get YouTube videos not in any playlist."""
    channel_url = request.args.get('channel_url', '').strip()
    if not channel_url:
        return err('channel_url parameter required')
    try:
        svc = get_ytdlp()
        result = svc.get_uncategorized(channel_url)
        return ok(result)
    except Exception as e:
        return err(str(e))


@ytdlp_features_bp.route('/api/ytdlp/latest-report', methods=['GET'])
def ytdlp_latest_report():
    """Get the latest-download tracking report for all channels."""
    try:
        svc = get_ytdlp()
        report = svc.get_latest_per_channel()
        return ok({'report': report, 'count': len(report)})
    except Exception as e:
        return err(str(e))


@ytdlp_features_bp.route('/api/ytdlp/latest-report/save', methods=['POST'])
def ytdlp_latest_report_save():
    """Save a latest-download entry for a channel."""
    data = request.get_json(force=True) or {}
    channel_id = data.get('channel_id', '').strip()
    video_id = data.get('video_id', '').strip()
    upload_date = data.get('upload_date', '').strip()
    if not channel_id or not video_id:
        return err('channel_id and video_id required')
    try:
        svc = get_ytdlp()
        svc.save_latest_per_channel(channel_id, video_id, upload_date)
        return ok({'saved': True})
    except Exception as e:
        return err(str(e))


@ytdlp_features_bp.route('/api/ytdlp/channel-uploads', methods=['GET'])
def ytdlp_channel_uploads():
    """Fetch all uploads from a YouTube channel."""
    channel_id = request.args.get('channel_id', '').strip()
    limit = request.args.get('limit', 200, type=int)
    if not channel_id:
        return err('channel_id parameter required')
    try:
        svc = get_ytdlp()
        videos = svc.get_channel_uploads(channel_id, limit)
        return ok({'videos': videos, 'count': len(videos)})
    except Exception as e:
        return err(str(e))