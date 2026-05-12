"""MegaDL — routes/youtube.py
YouTube channel playlists fetcher using Data API v3."""

import re
import json
import logging
import urllib.request
import urllib.error
from flask import Blueprint, request
from .ping import ok, err, get_settings

logger = logging.getLogger('megadl.youtube')

youtube_bp = Blueprint('youtube', __name__)


def _get_api_key() -> str:
    s = get_settings()
    return s.get('youtube_api_key', '') or ''


def _extract_channel_id(url: str) -> str:
    """Extract channel ID from various YouTube URL formats."""
    # Already a channel ID
    if re.match(r'^UC[\w-]{22}$', url):
        return url

    # youtube.com/channel/UC...
    m = re.search(r'youtube\.com/channel/(UC[\w-]+)', url)
    if m:
        return m.group(1)

    # youtube.com/@handle
    m = re.search(r'youtube\.com/@([\w.-]+)', url)
    if m:
        return m.group(1)  # handle, not channel ID — resolved via API

    # youtube.com/c/...
    m = re.search(r'youtube\.com/c/([\w.-]+)', url)
    if m:
        return m.group(1)

    # youtube.com/user/...
    m = re.search(r'youtube\.com/user/([\w.-]+)', url)
    if m:
        return m.group(1)

    return ''


def _resolve_handle(handle: str, api_key: str) -> str:
    """Resolve a @handle or custom name to a channel ID via the Data API."""
    try:
        req = urllib.request.Request(
            f'https://www.googleapis.com/youtube/v3/channels?part=id&forHandle={handle}&key={api_key}',
            headers={'User-Agent': 'MegaDL/2.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            items = body.get('items', [])
            if items:
                return items[0]['id']
    except Exception:
        pass
    return ''


@youtube_bp.route('/api/youtube/playlists', methods=['POST'])
def get_channel_playlists():
    """Fetch all public playlists from a YouTube channel."""
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()

    if not url:
        return err('URL is required')

    api_key = _get_api_key()
    if not api_key:
        return ok({
            'playlists': [],
            'error': 'YouTube API key not configured. Set it in Settings → Integrations.',
            'needs_api_key': True,
        })

    channel_id = _extract_channel_id(url)
    if not channel_id:
        return err('Could not extract channel ID from URL')

    # If it's a handle (starts with @), resolve it
    if channel_id.startswith('@'):
        resolved = _resolve_handle(channel_id[1:], api_key)
        if not resolved:
            return err(f'Could not resolve channel handle: {channel_id}')
        channel_id = resolved

    try:
        playlists = []
        page_token = ''

        while True:
            params = (
                f'part=snippet,contentDetails'
                f'&channelId={channel_id}'
                f'&maxResults=50'
                f'&key={api_key}'
            )
            if page_token:
                params += f'&pageToken={page_token}'

            req = urllib.request.Request(
                f'https://www.googleapis.com/youtube/v3/playlists?{params}',
                headers={'User-Agent': 'MegaDL/2.0'}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode())

            for item in body.get('items', []):
                snippet = item.get('snippet', {})
                details = item.get('contentDetails', {})
                thumbnails = snippet.get('thumbnails', {})
                thumb = thumbnails.get('medium', thumbnails.get('default', {})).get('url', '')
                playlists.append({
                    'id': item['id'],
                    'title': snippet.get('title', 'Untitled'),
                    'description': (snippet.get('description', '') or '')[:200],
                    'video_count': details.get('itemCount', 0),
                    'published_at': snippet.get('publishedAt', ''),
                    'thumbnail': thumb,
                })

            page_token = body.get('nextPageToken', '')
            if not page_token:
                break

        return ok({
            'playlists': playlists,
            'channel_id': channel_id,
            'count': len(playlists),
        })

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        return ok({'playlists': [], 'error': msg})
    except Exception as e:
        return ok({'playlists': [], 'error': str(e)})
