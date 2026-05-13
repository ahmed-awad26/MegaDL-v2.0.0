"""
MegaDL — services/ytdlp_service.py
Core yt-dlp integration: info extraction, download execution,
progress parsing, process management, output file handling.

All completed downloads are saved directly to the configured
dl_folder (e.g. /sdcard/Download/MegaDL on Android Termux).
"""

import os
import re
import json
import uuid
import shutil
import time
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

logger = logging.getLogger('megadl.ytdlp')

DOWNLOAD_DIR = "/storage/emulated/0/Download/AW/AW-DL"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# Media file extensions yt-dlp can produce
MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.webm', '.avi', '.mov', '.mp3', '.m4a',
    '.opus', '.ogg', '.wav', '.flac', '.aac', '.wma', '.flv',
    '.3gp', '.m4v', '.mpg', '.mpeg',
}


class YtdlpService:
    """Manages yt-dlp processes: info extraction and downloads."""

    def __init__(self, settings, db):
        self.settings = settings
        self.db       = db
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    # ── Binary detection ─────────────────────────────────────

    @staticmethod
    def find_binary(name: str) -> Optional[str]:
        path = shutil.which(name)
        if path:
            return path

        extras = []
        if name == 'yt-dlp':
            extras = [
                '/usr/local/bin/yt-dlp',
                '/usr/bin/yt-dlp',
                os.path.expanduser('~/.local/bin/yt-dlp'),
                os.path.expanduser('~/bin/yt-dlp'),
                '/data/data/com.termux/files/usr/bin/yt-dlp',
                'yt-dlp.exe',
            ]
        elif name == 'ffmpeg':
            extras = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/data/data/com.termux/files/usr/bin/ffmpeg',
                'C:/ffmpeg/bin/ffmpeg.exe',
                'C:/xampp/ffmpeg/bin/ffmpeg.exe',
            ]

        for p in extras:
            if p and Path(p).exists():
                return str(p)
        return None

    @staticmethod
    def get_version(binary: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [binary, '--version'],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip().split('\n')[0]
        except Exception:
            return None

    # ── Info extraction ──────────────────────────────────────

    def extract_info(self, url: str, opts: dict = None) -> dict:
        ytdlp = self.find_binary('yt-dlp')
        if not ytdlp:
            raise RuntimeError('yt-dlp not found. Install it: pip install yt-dlp')

        no_playlist = opts.get('no_playlist', True) if opts else True
        cmd = [
            ytdlp,
            '--dump-json',
            '--no-download',
            '--socket-timeout', str(opts.get('timeout', self.settings.get('timeout', 30))),
        ]
        if no_playlist:
            cmd.append('--no-playlist')
        else:
            cmd.append('--yes-playlist')

        proxy = opts.get('proxy') or self.settings.get('proxy', '')
        if proxy:
            cmd += ['--proxy', proxy]

        if opts.get('cookies'):
            cookies_file = Path(self.settings.get('dl_folder', './downloads')) / 'cookies.txt'
            if cookies_file.exists():
                cmd += ['--cookies', str(cookies_file)]

        cmd.append(url)

        logger.info(f'Extracting info: {url}')
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=60, encoding='utf-8', errors='replace'
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError('Info extraction timed out (60s)')

        if result.returncode != 0:
            error_msg = result.stderr.strip().split('\n')[-1] if result.stderr else 'Unknown error'
            raise RuntimeError(f'yt-dlp error: {error_msg}')

        try:
            lines = [l for l in result.stdout.strip().split('\n') if l.startswith('{')]
            data  = json.loads(lines[0]) if lines else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f'Could not parse yt-dlp output: {e}')

        return self._normalize_info(data)

    def _normalize_info(self, data: dict) -> dict:
        formats = []
        for f in data.get('formats', []):
            formats.append({
                'format_id':        f.get('format_id', ''),
                'ext':              f.get('ext', ''),
                'height':           f.get('height'),
                'width':            f.get('width'),
                'fps':              f.get('fps'),
                'filesize':         f.get('filesize') or f.get('filesize_approx'),
                'filesize_approx':  f.get('filesize_approx'),
                'vcodec':           f.get('vcodec', ''),
                'acodec':           f.get('acodec', ''),
                'tbr':              f.get('tbr'),
                'abr':              f.get('abr'),
                'vbr':              f.get('vbr'),
                'format_note':      f.get('format_note', ''),
                'protocol':         f.get('protocol', ''),
                'has_drm':          f.get('has_drm', False),
                'language':         f.get('language'),
                'audio_channels':   f.get('audio_channels'),
                'dynamic_range':    f.get('dynamic_range'),
                'aspect_ratio':     f.get('aspect_ratio'),
                'format':           f.get('format', ''),
                'quality':          f.get('quality'),
                'preference':       f.get('preference'),
                'source_preference': f.get('source_preference'),
                'pixel_format':     f.get('pixel_format'),
                'color_range':      f.get('color_range'),
                'color_space':      f.get('color_space'),
                'color_transfer':   f.get('color_transfer'),
                'color_primaries':  f.get('color_primaries'),
                'resolution':       f.get('resolution', ''),
            })

        thumbnails = data.get('thumbnails') or []
        thumb_list = [{
            'id': t.get('id',''),
            'url': t.get('url',''),
            'width': t.get('width'),
            'height': t.get('height'),
            'resolution': t.get('resolution',''),
        } for t in thumbnails] if thumbnails else []

        subs = {}
        for lang, sub_data in (data.get('subtitles') or {}).items():
            subs[lang] = [{'ext': s.get('ext',''), 'url': s.get('url','')} for s in (sub_data or [])]
        auto_subs = {}
        for lang, sub_data in (data.get('automatic_captions') or {}).items():
            auto_subs[lang] = [{'ext': s.get('ext',''), 'url': s.get('url','')} for s in (sub_data or [])]

        chapters_list = []
        for ch in data.get('chapters') or []:
            chapters_list.append({
                'title': ch.get('title',''),
                'start': ch.get('start_time',0),
                'end':   ch.get('end_time',0),
            })

        heatmap = data.get('heatmap') or []
        heatmap_list = [{'start': h.get('start_time',0), 'end': h.get('end_time',0), 'value': h.get('value',0)} for h in heatmap]

        return {
            'id':                data.get('id', ''),
            'fulltitle':         data.get('fulltitle', ''),
            'title':             data.get('title', 'Unknown'),
            'thumbnail':         data.get('thumbnail', ''),
            'thumbnails':        thumb_list,
            'uploader':          data.get('uploader') or data.get('channel', ''),
            'uploader_id':       data.get('uploader_id', ''),
            'uploader_url':      data.get('uploader_url', ''),
            'channel':           data.get('channel', ''),
            'channel_id':        data.get('channel_id', ''),
            'channel_url':       data.get('channel_url', ''),
            'creator':           data.get('creator', ''),
            'duration':          data.get('duration', 0),
            'duration_string':   data.get('duration_string', ''),
            'resolution':        data.get('resolution', ''),
            'height':            data.get('height'),
            'width':             data.get('width'),
            'filesize':          data.get('filesize') or data.get('filesize_approx'),
            'view_count':        data.get('view_count'),
            'like_count':        data.get('like_count'),
            'comment_count':     data.get('comment_count'),
            'repost_count':      data.get('repost_count'),
            'upload_date':       data.get('upload_date', ''),
            'release_date':      data.get('release_date'),
            'release_year':      data.get('release_year'),
            'timestamp':         data.get('timestamp'),
            'description':       (data.get('description', '') or '')[:500],
            'webpage_url':       data.get('webpage_url', ''),
            'webpage_domain':    data.get('webpage_url_domain', ''),
            'original_url':      data.get('original_url', ''),
            'extractor':         data.get('extractor', ''),
            'extractor_key':     data.get('extractor_key', ''),
            'is_live':           data.get('is_live', False),
            'was_live':          data.get('was_live', False),
            'live_status':       data.get('live_status'),
            'availability':      data.get('availability'),
            'age_limit':         data.get('age_limit'),
            'language':          data.get('language'),
            'license':           data.get('license'),
            'categories':        data.get('categories', []),
            'tags':              data.get('tags', []),
            'playlist_id':       data.get('playlist_id'),
            'playlist_title':    data.get('playlist_title'),
            'playlist_index':    data.get('playlist_index'),
            'subtitles':         subs,
            'automatic_captions': auto_subs,
            'chapters':          chapters_list,
            'heatmap':           heatmap_list,
            'series':            data.get('series'),
            'season_number':     data.get('season_number'),
            'episode_number':    data.get('episode_number'),
            'episode':           data.get('episode'),
            'album':             data.get('album'),
            'album_artist':      data.get('album_artist'),
            'track':             data.get('track'),
            'artist':            data.get('artist'),
            'genre':             data.get('genre'),
            'formats':           formats,
        }

    # ── Archive Dedup ────────────────────────────────────────────

    def is_archived(self, url: str) -> bool:
        ytdlp = self.find_binary('yt-dlp')
        if not ytdlp:
            return False

        try:
            info = self.extract_info(url, {'timeout': 15})
            vid  = info.get('id', '')
            extractor = info.get('extractor', '')
        except Exception:
            return False

        if not vid:
            return False

        dl_folder = self.settings.get('dl_folder', DOWNLOAD_DIR)

        archive_file = Path(self.settings.get('archive_file') or str(Path(dl_folder) / '.megadl_archive.txt'))
        if archive_file.exists():
            try:
                content = archive_file.read_text(encoding='utf-8')
                if f'{extractor} {vid}' in content:
                    return True
            except Exception:
                pass

        dl_path = Path(dl_folder)
        if dl_path.exists():
            pattern = f'[{re.escape(vid)}]'
            for f in dl_path.rglob('*'):
                if f.is_file() and re.search(pattern, f.name):
                    return True

        try:
            archived = self.db.get_archive()
            for entry in archived:
                if entry.get('id') == vid:
                    return True
        except Exception:
            pass

        return False

    def mark_archived(self, extractor: str, video_id: str, title: str = ''):
        dl_folder = self.settings.get('dl_folder', DOWNLOAD_DIR)

        archive_file = Path(self.settings.get('archive_file') or str(Path(dl_folder) / '.megadl_archive.txt'))
        try:
            archive_file.parent.mkdir(parents=True, exist_ok=True)
            with open(archive_file, 'a', encoding='utf-8') as f:
                f.write(f'{extractor} {video_id}\n')
        except Exception:
            pass

        try:
            self.db.add_archive(extractor, video_id, title)
        except Exception:
            pass

    # ── Pre-download validation ──────────────────────────────

    def _validate_dl_folder(self, dl_folder: str) -> Optional[str]:
        """Check the download folder is writable. Return error msg or None."""
        path = Path(dl_folder)
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / '.megadl_write_test'
            test_file.write_text('test')
            test_file.unlink()
            return None
        except PermissionError:
            return f'Permission denied: cannot write to {dl_folder}'
        except OSError as e:
            return f'Cannot access {dl_folder}: {e}'

    # ── Download ─────────────────────────────────────────────

    def start_download(self, job_id: str, url: str, opts: dict,
                       on_progress: Callable = None,
                       on_complete: Callable = None,
                       on_error: Callable = None) -> threading.Thread:
        thread = threading.Thread(
            target=self._download_worker,
            args=(job_id, url, opts, on_progress, on_complete, on_error),
            daemon=True,
            name=f'dl-{job_id[:8]}'
        )
        thread.start()
        return thread

    def _find_output_file(self, dl_folder: str, known_paths: list[str]) -> Optional[str]:
        """
        Reliably find the output file after yt-dlp finishes.
        Strategy:
        1. Check known paths parsed from yt-dlp output (destination/merge lines)
        2. Scan dl_folder for the newest media file created in the last 30s
        3. If older files exist, pick the most recently modified media file
        """
        # Strategy 1: known paths from yt-dlp output
        for p in known_paths:
            if p and Path(p).is_file():
                return p

        # Strategy 2: scan for newest media file
        dl_path = Path(dl_folder)
        if not dl_path.exists():
            return None

        cutoff = time.time() - 30
        candidates = []
        for f in dl_path.iterdir():
            if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
                candidates.append(f)
        if candidates:
            candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            newest = candidates[0]
            if newest.stat().st_mtime >= cutoff:
                return str(newest.resolve())
            return str(newest.resolve())

        return None

    def _resolve_output_path(self, dl_folder: str, url: str, opts: dict) -> Optional[str]:
        """
        Use yt-dlp --print filename_after_merge to get the exact final path
        WITHOUT actually downloading. Uses smart output path when info is available.
        """
        ytdlp = self.find_binary('yt-dlp')
        if not ytdlp:
            return None

        # Build the output path template with smart folder structure
        info = {}
        try:
            info_cmd = [
                ytdlp, '--dump-json', '--no-playlist',
                '--no-warnings', '--skip-download', url,
                '--socket-timeout', '15',
            ]
            ir = subprocess.run(info_cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30)
            if ir.returncode == 0 and ir.stdout.strip():
                info = json.loads(ir.stdout.strip().split('\n')[0])
        except Exception:
            pass

        template = self._build_output_path(dl_folder, url, info, opts)
        cmd = [
            ytdlp,
            '--print', 'filename_after_merge',
            '--no-download',
            '--no-playlist',
            '-o', template,
        ]

        proxy = opts.get('proxy') or self.settings.get('proxy', '')
        if proxy:
            cmd += ['--proxy', proxy]

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if path:
                    logger.info(f'[OUTPUT] yt-dlp --print path: {path}')
                    return path
        except Exception as e:
            logger.warning(f'[OUTPUT] --print failed: {e}')

        return None

    @staticmethod
    def _detect_platform(url: str) -> str:
        url_lower = url.lower()
        if "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
            return "facebook"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        if "instagram.com" in url_lower:
            return "instagram"
        if "tiktok.com" in url_lower:
            return "tiktok"
        if "twitter.com" in url_lower or "x.com" in url_lower:
            return "twitter"
        return "other"

    def _build_output_path(self, dl_folder: str, url: str, info: dict, opts: dict) -> str:
        """
        Build smart output path with organized folder structure:
          {dl_folder}/ChannelName/Playlists/PlaylistName/Title [id].ext
          {dl_folder}/ChannelName/Uploads/Title [id].ext
          {dl_folder}/ChannelName/Uncategorized/Title [id].ext
          {dl_folder}/ChannelName/Latest/Title [id].ext
          {dl_folder}/Playlist_PLxxxx/Title [id].ext
          {dl_folder}/domain.com/Title [id].ext
        """
        out_dir = Path(dl_folder)
        platform = self._detect_platform(url)

        # Common fields
        uploader = (info.get("uploader") or info.get("channel") or "").strip()
        uploader_safe = re.sub(r'[\\/:*?"<>|]', '_', uploader)[:100] if uploader else ""
        playlist_id = info.get("playlist_id") or ""
        playlist_title = info.get("playlist_title") or ""
        playlist_title_safe = re.sub(r'[\\/:*?"<>|]', '_', playlist_title)[:100] if playlist_title else ""
        is_playlist = bool(playlist_id) or opts.get('mode') in ('playlist', 'unlisted_playlist')
        mode = opts.get('mode', 'single')

        quality = opts.get('quality', self.settings.get('def_quality', 'best'))
        if quality in ('mp3', 'm4a'):
            ext = quality
        else:
            ext = '%(ext)s'

        # Always use %(id)s placeholder so yt-dlp substitutes per video
        filename_tpl = f"%(title)s [%(id)s].{ext}"

        if platform == "facebook":
            return str(out_dir / "facebook.com" / filename_tpl)

        if platform == "youtube":
            channel_safe = uploader_safe or "Unknown_Channel"

            # Standalone playlist (no channel context) → Playlist_PLxxxx/
            if is_playlist and not uploader_safe:
                pl_dir = f"Playlist_{playlist_id}" if playlist_id else "Playlist_unknown"
                return str(out_dir / pl_dir / filename_tpl)

            # Playlist within a channel → ChannelName/Playlists/PlaylistName/
            if is_playlist and playlist_title_safe:
                return str(out_dir / channel_safe / "Playlists" / playlist_title_safe / filename_tpl)

            # Latest-only mode → ChannelName/Latest/
            if mode == 'latest' or opts.get('latestOnly'):
                return str(out_dir / channel_safe / "Latest" / filename_tpl)

            # Uncategorized → ChannelName/Uncategorized/
            if mode == 'uncategorized':
                return str(out_dir / channel_safe / "Uncategorized" / filename_tpl)

            # Default: regular uploads → ChannelName/Uploads/
            return str(out_dir / channel_safe / "Uploads" / filename_tpl)

        # Standalone playlist (non-YouTube)
        if is_playlist and playlist_id:
            pl_dir = f"Playlist_{playlist_id}"
            return str(out_dir / pl_dir / filename_tpl)

        # Other platforms → domain.com/
        return str(out_dir / platform / filename_tpl)

    # ── Metadata files (.last_run, latest_report.txt, download logs) ──

    def _get_channel_dir(self, dl_folder: str, info: dict) -> Optional[Path]:
        """Get the per-channel directory path from download metadata."""
        uploader = (info.get("uploader") or info.get("channel") or "").strip()
        if not uploader:
            return None
        safe = re.sub(r'[\\/:*?"<>|]', '_', uploader)[:100]
        return Path(dl_folder) / safe

    def _write_last_run(self, channel_dir: Path):
        """Write .last_run timestamp file for a channel."""
        try:
            channel_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            (channel_dir / '.last_run').write_text(ts, encoding='utf-8')
        except Exception:
            pass

    def _write_download_log(self, channel_dir: Path, url: str, info: dict, output_path: str):
        """Append to download_YYYYMMDD.log for the channel."""
        try:
            channel_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime('%Y%m%d')
            log_path = channel_dir / f'download_{today}.log'
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            title = info.get('title', url)
            video_id = info.get('id', '')
            line = f'[{ts}] {title} [{video_id}] -> {output_path}\n'
            with open(str(log_path), 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception:
            pass

    def write_channel_metadata(self, dl_folder: str, url: str, info: dict, output_path: str):
        """Write all metadata files for a channel's parent directory."""
        channel_dir = self._get_channel_dir(dl_folder, info)
        if channel_dir:
            self._write_last_run(channel_dir)
            self._write_download_log(channel_dir, url, info, output_path)

    def _build_output_template(self, dl_folder: str, opts: dict) -> str:
        """Build an absolute output template for yt-dlp (fallback)."""
        s = self.settings
        quality = opts.get('quality', s.get('def_quality', 'best'))

        if quality in ('mp3', 'm4a'):
            ext = quality
        else:
            ext = '%(ext)s'

        return os.path.join(dl_folder, '%(title)s [%(id)s].%(ext)s')

    # ── Channel Mode Dispatcher ────────────────────────────────────

    CHANNEL_MODES = ('playlists_only', 'uploads_only', 'playlists_and_uploads',
                     'all_uncategorized', 'latest_since_last_run')

    def is_channel_mode(self, opts: dict) -> bool:
        """Check if the options specify a YouTube channel download mode."""
        return opts.get('mode') in self.CHANNEL_MODES

    def _handle_channel_mode(self, job_id: str, url: str, opts: dict,
                             on_progress, on_complete, on_error):
        """Dispatch multiple sub-downloads for a YouTube channel mode.
        
        For each playlist, dispatches a single job; for uploads/uncategorized,
        dispatches the channel URL with appropriate flags.
        Uses --download-archive for dedup across all sub-downloads.
        """
        ytdlp = self.find_binary('yt-dlp')
        if not ytdlp:
            self.db.update_job(job_id, {'state': 'error', 'error': 'yt-dlp not found'})
            if on_error: on_error(job_id, 'yt-dlp not found')
            return

        mode = opts.get('mode', 'uploads_only')
        dl_folder = self.settings.get('dl_folder', DOWNLOAD_DIR)
        dl_folder_abs = str(Path(dl_folder).resolve())

        # ── Step 1: Extract channel info ───────────────────────
        info = {}
        playlists = []
        channel_id = ''
        channel_name = ''
        try:
            info_cmd = [ytdlp, '--dump-json', '--no-playlist',
                        '--no-warnings', '--skip-download', url,
                        '--socket-timeout', '15']
            ir = subprocess.run(info_cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30)
            if ir.returncode == 0 and ir.stdout.strip():
                info = json.loads(ir.stdout.strip().split('\n')[0])
                channel_id = info.get('channel_id') or info.get('channel_url', '').split('/')[-1] or ''
                channel_name = info.get('uploader') or info.get('channel') or 'Unknown'
        except Exception as e:
            logger.warning(f'[{job_id[:8]}] Channel info extract failed: {e}')

        if not channel_name:
            self.db.update_job(job_id, {'state': 'error', 'error': 'Could not determine channel name'})
            if on_error: on_error(job_id, 'Could not determine channel name')
            return

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', channel_name)[:100]

        # ── Step 2: Fetch playlists (for playlists modes) ──────
        fetch_playlists = mode in ('playlists_only', 'playlists_and_uploads', 'all_uncategorized')
        if fetch_playlists:
            try:
                pl_cmd = [ytdlp, '--flat-playlist', '--dump-json',
                          '--no-warnings', '--skip-download',
                          f'https://www.youtube.com/channel/{channel_id}/playlists'
                          if channel_id else url.replace('/videos', '/playlists').replace('/streams', '/playlists'),
                          '--socket-timeout', '15']
                pr = subprocess.run(pl_cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=30)
                if pr.returncode == 0 and pr.stdout.strip():
                    for line in pr.stdout.strip().split('\n'):
                        try:
                            pl = json.loads(line)
                            if pl.get('playlist_id') or pl.get('id'):
                                playlists.append({
                                    'id': pl.get('playlist_id') or pl.get('id'),
                                    'title': pl.get('title') or pl.get('playlist_title') or f'Playlist_{len(playlists)}',
                                    'url': f'https://www.youtube.com/playlist?list={pl.get("playlist_id") or pl.get("id")}',
                                })
                        except (json.JSONDecodeError, Exception):
                            continue
            except Exception as e:
                logger.warning(f'[{job_id[:8]}] Playlist fetch failed: {e}')

        logger.info(f'[{job_id[:8]}] Channel: {channel_name}, playlists: {len(playlists)}')

        # ── Step 3: Build sub-job URLs ─────────────────────────
        sub_urls = []
        total_estimated = 0

        if mode == 'playlists_only':
            # Only playlist URLs
            sub_urls = [p['url'] for p in playlists if p.get('url')]
            total_estimated = len(sub_urls)

        elif mode == 'uploads_only':
            # Channel uploads URL (with --no-playlist)
            channel_url = f'https://www.youtube.com/channel/{channel_id}/videos' if channel_id else url
            sub_urls = [channel_url]
            total_estimated = 1

        elif mode in ('playlists_and_uploads', 'all_uncategorized'):
            # Playlists + channel uploads
            for p in playlists:
                if p.get('url'):
                    sub_urls.append(p['url'])
            channel_url = f'https://www.youtube.com/channel/{channel_id}/videos' if channel_id else url
            sub_urls.append(channel_url)
            total_estimated = len(sub_urls)

        elif mode == 'latest_since_last_run':
            # Use --dateafter with last run date
            last_date = self.get_latest_per_channel().get(channel_id, {}).get('upload_date', '')
            if last_date:
                opts['dateafter'] = last_date
            channel_url = f'https://www.youtube.com/channel/{channel_id}/videos' if channel_id else url
            sub_urls = [channel_url]
            total_estimated = 1

        if not sub_urls:
            self.db.update_job(job_id, {'state': 'error', 'error': f'No URLs to download for mode: {mode}'})
            if on_error: on_error(job_id, f'No URLs to download for mode: {mode}')
            return

        # ── Step 4: Dispatch sub-downloads ─────────────────────
        self.db.update_job(job_id, {
            'state': 'running',
            'title': f'{channel_name} ({mode})',
            'progress': 0,
        })
        self.db.add_log(f'Channel mode "{mode}": {len(sub_urls)} sub-job(s) for {channel_name}', 'info', job_id)

        # Use same archive file for dedup across all sub-jobs
        archive_file = self.settings.get('archive_file') or str(Path(dl_folder) / '.megadl_archive.txt')
        common_flags = [
            '--download-archive', archive_file,
            '--no-overwrites', '--continue',
            '--newline', '--progress',
        ]

        completed = 0
        failed = 0
        total = len(sub_urls)
        output_paths = []

        for i, sub_url in enumerate(sub_urls, 1):
            sub_job_id = f'{job_id}_{i}'
            logger.info(f'[{job_id[:8]}] Sub-job {i}/{total}: {sub_url}')

            # Build output path with correct folder structure
            sub_info = dict(info)
            sub_opts = dict(opts)
            sub_opts['mode'] = 'playlist'  # yt-dlp playlist mode
            sub_opts['_is_sub_job'] = True

            # For uploads_only or the uploads sub-job, use --no-playlist
            is_uploads = (mode == 'uploads_only' or
                         (mode in ('playlists_and_uploads', 'all_uncategorized') and i == total))

            # Build command
            cmd = [ytdlp]
            quality = sub_opts.get('quality', self.settings.get('def_quality', 'best'))
            if quality in ('mp3',):
                cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
            elif quality in ('m4a',):
                cmd += ['-x', '--audio-format', 'm4a']
            elif quality == 'best':
                cmd += ['-f', 'bestvideo+bestaudio/best']
            else:
                cmd += ['-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best']

            if quality not in ('mp3', 'm4a'):
                merge = sub_opts.get('merge_format') or self.settings.get('merge_format', 'mp4')
                cmd += ['--merge-output-format', merge]

            cmd += ['--retries', '3', '--fragment-retries', '5',
                    '--socket-timeout', '30']
            cmd += common_flags

            # Playlist handling
            if is_uploads:
                cmd += ['--no-playlist']
            else:
                cmd += ['--yes-playlist']

            # Latest-only
            if sub_opts.get('dateafter'):
                cmd += ['--dateafter', sub_opts['dateafter']]

            # Build output template
            output_tpl = self._build_output_path(dl_folder_abs, sub_url, sub_info, sub_opts)
            Path(output_tpl).parent.mkdir(parents=True, exist_ok=True)
            cmd += ['-o', output_tpl]
            cmd.append(sub_url)

            logger.info(f'[{job_id[:8]}] Sub-cmd: {" ".join(cmd[:8])}...')

            # Progress tracking
            sub_progress = {'percent': 0}
            def _make_progress_cb(jid, idx, total):
                def cb(progress):
                    overall = ((idx - 1) * 100 + progress.get('percent', 0)) / max(total, 1)
                    self.db.update_job(jid, {'progress': overall})
                    if on_progress:
                        on_progress(jid, {'percent': overall, 'sub': idx, 'total': total})
                return cb

            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace',
                )
                for line in iter(proc.stdout.readline, ''):
                    line = line.rstrip()
                    if not line: continue
                    self.db.add_log(line, 'debug', job_id)
                    prog = self._parse_progress(line)
                    if prog:
                        sub_progress = prog
                        overall = ((i - 1) * 100 + prog.get('percent', 0)) / max(total, 1)
                        self.db.update_job(job_id, {'progress': overall})
                        if on_progress:
                            on_progress(job_id, {
                                'percent': overall,
                                'sub': i,
                                'total': total,
                                'speed': prog.get('speed', 0),
                                'eta': prog.get('eta', 0),
                            })

                    # Track output path
                    dest_match = re.search(r'\[download\] Destination:\s*(.+)', line)
                    if dest_match:
                        rel_path = dest_match.group(1).strip()
                        abs_path = str((Path(dl_folder_abs) / rel_path).resolve())
                        if abs_path not in output_paths:
                            output_paths.append(abs_path)

                proc.wait()
                if proc.returncode == 0:
                    completed += 1
                    logger.info(f'[{job_id[:8]}] Sub-job {i} done')
                else:
                    failed += 1
                    logger.warning(f'[{job_id[:8]}] Sub-job {i} failed (code {proc.returncode})')
            except Exception as e:
                failed += 1
                logger.warning(f'[{job_id[:8]}] Sub-job {i} error: {e}')

        # ── Step 5: Finalize ───────────────────────────────────
        # Write metadata
        channel_dir = Path(dl_folder_abs) / safe_name
        self._write_last_run(channel_dir)

        # Update latest-per-channel
        if channel_id and info.get('id'):
            self.save_latest_per_channel(channel_id, info.get('id', ''), info.get('upload_date', ''))

        final_output = output_paths[0] if output_paths else str(channel_dir)
        self.db.update_job(job_id, {
            'state': 'done',
            'progress': 100,
            'output_path': final_output,
        })
        self.db.add_log(f'Channel mode "{mode}" complete: {completed}/{total} sub-jobs', 'info', job_id)
        if on_complete:
            on_complete(job_id, final_output)

    def _download_worker(self, job_id: str, url: str, opts: dict,
                         on_progress, on_complete, on_error):
        ytdlp  = self.find_binary('yt-dlp')
        if not ytdlp:
            if on_error: on_error(job_id, 'yt-dlp not found')
            return

        dl_folder = self.settings.get('dl_folder', DOWNLOAD_DIR)
        dl_folder_abs = str(Path(dl_folder).resolve())

        err_msg = self._validate_dl_folder(dl_folder_abs)
        if err_msg:
            logger.error(f'[{job_id[:8]}] {err_msg}')
            self.db.update_job(job_id, {'state': 'error', 'error': err_msg})
            self.db.add_log(f'Download failed: {err_msg}', 'error', job_id)
            if on_error: on_error(job_id, err_msg)
            return

        logger.info(f'[{job_id[:8]}] Download folder: {dl_folder_abs}')

        # Route channel mode to dedicated handler
        if self.is_channel_mode(opts):
            try:
                self._handle_channel_mode(job_id, url, opts, on_progress, on_complete, on_error)
            except Exception as e:
                self.db.update_job(job_id, {'state': 'error', 'error': f'Channel mode error: {e}'})
                self.db.add_log(f'Channel mode exception: {e}', 'error', job_id)
                if on_error: on_error(job_id, str(e))
            return

        # Quick info extract for smart folder structure
        info_data = {}
        try:
            info_cmd = [
                ytdlp, '--dump-json', '--no-playlist',
                '--no-warnings', '--skip-download', url,
                '--socket-timeout', '15',
            ]
            ir = subprocess.run(info_cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30)
            if ir.returncode == 0 and ir.stdout.strip():
                info_data = json.loads(ir.stdout.strip().split('\n')[0])
        except Exception:
            pass

        title = info_data.get('title', url)
        uploader = info_data.get('uploader') or info_data.get('channel', '')

        # Build smart output path
        smart_path = self._build_output_path(dl_folder_abs, url, info_data, opts)
        Path(smart_path).parent.mkdir(parents=True, exist_ok=True)
        opts = dict(opts)
        opts['_output_template'] = smart_path

        cmd = self._build_command(ytdlp, url, opts, dl_folder_abs)

        logger.info(f'[{job_id[:8]}] Starting: {" ".join(cmd[:6])}...')
        self.db.update_job(job_id, {'state': 'running'})
        self.db.add_log(f'Starting download: {url}', 'info', job_id)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
            )

            with self._lock:
                self._processes[job_id] = proc

            known_paths: list[str] = []
            output_path: Optional[str] = None
            current_video_title = ''
            current_video_index = 0
            total_videos = 0
            extractor = ''
            video_id = ''
            dest_seen: set[str] = set()
            merge_seen: set[str] = set()

            for line in iter(proc.stdout.readline, ''):
                line = line.rstrip()
                if not line:
                    continue

                self.db.add_log(line, 'debug', job_id)

                pl_match = re.search(r'\[download\] Downloading video (\d+) of (\d+)', line)
                if pl_match:
                    current_video_index = int(pl_match.group(1))
                    total_videos = int(pl_match.group(2))

                id_match = re.search(r'\[(\w+)\]\s+([\w-]+):\s+(?:Downloading|Extracting)', line)
                if id_match:
                    extractor = id_match.group(1).lower()
                    video_id = id_match.group(2)

                dest_line_match = re.search(r'\[download\] Destination:\s*(.+)', line)
                if dest_line_match:
                    rel_path = dest_line_match.group(1).strip()
                    abs_path = str((Path(dl_folder_abs) / rel_path).resolve())
                    if abs_path not in dest_seen:
                        dest_seen.add(abs_path)
                        known_paths.append(abs_path)
                        logger.info(f'[{job_id[:8]}] [DEST] {abs_path}')
                    title_from_path = Path(abs_path).stem
                    if title_from_path:
                        current_video_title = title_from_path
                        self.db.update_job(job_id, {'title': current_video_title})

                merge_match = re.search(r'\[Merger\] Merging formats into "(.+)"', line)
                if merge_match:
                    rel_path = merge_match.group(1).strip()
                    abs_path = str((Path(dl_folder_abs) / rel_path).resolve())
                    if abs_path not in merge_seen:
                        merge_seen.add(abs_path)
                        known_paths.append(abs_path)
                        logger.info(f'[{job_id[:8]}] [MERGE] {abs_path}')

                progress = self._parse_progress(line)
                if progress:
                    update_data = {
                        'progress':    progress.get('percent', 0),
                        'speed':       progress.get('speed', 0),
                        'eta':         progress.get('eta', 0),
                        'total_bytes': progress.get('total_bytes', 0),
                        'fragment':    progress.get('fragment', ''),
                    }
                    self.db.update_job(job_id, update_data)

                    if current_video_title or current_video_index > 0:
                        job = self.db.get_job(job_id)
                        if job:
                            opts_saved = job.get('options') or {}
                            if isinstance(opts_saved, str):
                                try:
                                    opts_saved = json.loads(opts_saved)
                                except (json.JSONDecodeError, TypeError):
                                    opts_saved = {}
                            if current_video_title:
                                opts_saved['_video_title'] = current_video_title
                            if current_video_index > 0:
                                opts_saved['_video_index'] = current_video_index
                            if total_videos > 0:
                                opts_saved['_video_total'] = total_videos
                            self.db.update_job(job_id, {'options': json.dumps(opts_saved)})

                    if on_progress:
                        on_progress(job_id, progress)

            proc.wait()

            with self._lock:
                self._processes.pop(job_id, None)

            job = self.db.get_job(job_id)
            if job and job.get('state') == 'cancelled':
                logger.info(f'[{job_id[:8]}] Cancelled')
                return

            if proc.returncode == 0:
                output_path = self._resolve_final_path(
                    dl_folder_abs, url, opts, known_paths,
                    job_id, current_video_title, extractor, video_id
                )

                if output_path:
                    self.db.update_job(job_id, {
                        'state':       'done',
                        'progress':    100,
                        'output_path': output_path,
                    })
                    self.db.add_log(f'Download completed -> {output_path}', 'info', job_id)
                    logger.info(f'[{job_id[:8]}] [DONE] Saved to: {output_path}')

                    # Write channel metadata files (.last_run, download log)
                    self.write_channel_metadata(dl_folder_abs, url, info_data, output_path)
                else:
                    self.db.update_job(job_id, {
                        'state': 'done',
                        'progress': 100,
                    })
                    self.db.add_log('Download completed (output path unknown)', 'info', job_id)
                    logger.warning(f'[{job_id[:8]}] [DONE] Could not determine output path')

                if extractor or video_id:
                    self.mark_archived(extractor or 'unknown', video_id or '', current_video_title)

                # Save latest-per-channel for YouTube (latest-only mode)
                if extractor == 'youtube' and video_id:
                    channel_id = info_data.get('channel_id', '')
                    if channel_id:
                        upload_date = info_data.get('upload_date', '')
                        self.save_latest_per_channel(channel_id, video_id, upload_date)

                job = self.db.get_job(job_id)
                if job:
                    self.db.add_history(job)
                if on_complete:
                    on_complete(job_id, output_path)
            else:
                err = f'Process exited with code {proc.returncode}'
                self.db.update_job(job_id, {'state': 'error', 'error': err})
                self.db.add_log(f'Download failed: {err}', 'error', job_id)
                if on_error:
                    on_error(job_id, err)

        except Exception as e:
            logger.exception(f'[{job_id[:8]}] Download exception: {e}')
            self.db.update_job(job_id, {'state': 'error', 'error': str(e)})
            if on_error:
                on_error(job_id, str(e))

    def _resolve_final_path(self, dl_folder_abs: str, url: str, opts: dict,
                            known_paths: list[str], job_id: str,
                            title: str, extractor: str, video_id: str) -> Optional[str]:
        """
        Resolve the final output file path after download completes.
        Uses multiple strategies in order of reliability.
        Logs all attempts for diagnostics.
        """
        logger.info(f'[{job_id[:8]}] [RESOLVE] Resolving final output path...')
        logger.info(f'[{job_id[:8]}] [RESOLVE] Known paths: {known_paths}')

        # Strategy 1: yt-dlp's --print filename_after_merge (reliable)
        printed = self._resolve_output_path(dl_folder_abs, url, opts)
        if printed:
            p = Path(printed)
            if p.is_file():
                logger.info(f'[{job_id[:8]}] [RESOLVE] Strategy 1 (--print): {printed}')
                return str(p.resolve())
            else:
                logger.info(f'[{job_id[:8]}] [RESOLVE] Strategy 1 path not on disk: {printed}')

        # Strategy 2: known paths from stdout (destination/merge lines)
        for p in known_paths:
            if Path(p).is_file():
                logger.info(f'[{job_id[:8]}] [RESOLVE] Strategy 2 (known path): {p}')
                return p
            logger.info(f'[{job_id[:8]}] [RESOLVE] Strategy 2 missing: {p}')

        # Strategy 3: scan dl_folder for newest media file
        scan = self._find_output_file(dl_folder_abs, known_paths)
        if scan:
            logger.info(f'[{job_id[:8]}] [RESOLVE] Strategy 3 (scan): {scan}')
            return scan

        logger.warning(f'[{job_id[:8]}] [RESOLVE] All strategies failed to find output file')
        return None

    # ── Command builder ──────────────────────────────────────

    def _build_command(self, ytdlp: str, url: str, opts: dict, dl_folder: str) -> list:
        """Build yt-dlp command using ABSOLUTE output template pointing to dl_folder."""
        s    = self.settings
        cmd  = [ytdlp]

        quality  = opts.get('quality', s.get('def_quality', 'best'))
        mode     = opts.get('mode', 'single')

        if quality in ('mp3',):
            cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
        elif quality in ('m4a',):
            cmd += ['-x', '--audio-format', 'm4a']
        elif quality == 'best':
            cmd += ['-f', 'bestvideo+bestaudio/best']
        else:
            cmd += ['-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best']

        if quality not in ('mp3', 'm4a'):
            merge = opts.get('merge_format') or s.get('merge_format', 'mp4')
            cmd += ['--merge-output-format', merge]

        if 'facebook' in url.lower() or 'fb.watch' in url.lower() or 'fb.com' in url.lower():
            cmd += ['-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4', '--embed-thumbnail', '--no-playlist']

        if opts.get('format_id'):
            cmd += ['-f', opts['format_id']]

        frag = int(opts.get('concurrent_frag') or s.get('concurrent_frag', 4))
        if frag > 1:
            cmd += ['--concurrent-fragments', str(frag)]

        cmd += ['--retries', str(int(opts.get('retries') or s.get('retries', 3)))]
        cmd += ['--fragment-retries', str(int(opts.get('frag_retries') or s.get('frag_retries', 5)))]
        cmd += ['--socket-timeout', str(int(opts.get('timeout') or s.get('timeout', 30)))]

        speed = int(opts.get('speed_limit') or s.get('speed_limit', 0))
        if speed > 0:
            cmd += ['--limit-rate', f'{speed}K']

        proxy = opts.get('proxy') or s.get('proxy', '')
        if proxy:
            cmd += ['--proxy', proxy]

        if opts.get('embed_subs') or s.get('embed_subs', False):
            lang = opts.get('sub_lang') or s.get('sub_lang', 'en')
            cmd += ['--embed-subs', '--sub-langs', lang, '--convert-subs', 'srt']

        if opts.get('embed_thumb', s.get('embed_thumb', True)):
            cmd += ['--embed-thumbnail']

        if opts.get('embed_meta', s.get('embed_meta', True)):
            cmd += ['--add-metadata']

        if opts.get('sponsorblock', s.get('sponsorblock', False)):
            cmd += ['--sponsorblock-mark', 'all']

        if opts.get('cookies'):
            cookies_file = Path(dl_folder) / 'cookies.txt'
            if cookies_file.exists():
                cmd += ['--cookies', str(cookies_file)]

        if opts.get('archive_mode', s.get('archive_mode', True)):
            archive_file = s.get('archive_file') or str(Path(dl_folder) / '.megadl_archive.txt')
            cmd += ['--download-archive', archive_file]

        # Latest-only mode: use --dateafter to skip older videos
        if opts.get('latestOnly') or s.get('latest_only', False):
            channel_id = self._get_channel_id(url) if ('youtube.com/channel/' in url or 'youtube.com/@' in url) else None
            if channel_id:
                report = self.get_latest_per_channel()
                last = report.get(channel_id, {}).get('upload_date', '')
                if last:
                    year = last[:4]
                    month = last[4:6]
                    day = last[6:8]
                    cmd += ['--dateafter', f'{year}{month}{day}']

        if mode == 'single':
            cmd += ['--no-playlist']
        elif mode == 'playlist':
            cmd += ['--yes-playlist']
        elif mode == 'unlisted_playlist':
            cmd += ['--yes-playlist', '--extractor-args', 'youtube:skip_unavailable_videos=False']

        cmd += ['--newline', '--progress', '--continue']

        if opts.get('verbose', s.get('verbose', False)):
            cmd += ['--verbose']

        custom = (opts.get('custom_args') or s.get('custom_args', '')).strip()
        if custom:
            cmd += custom.split()

        # ── Output template: ABSOLUTE path to dl_folder ──────────
        output_template = opts.get('_output_template') or self._build_output_template(dl_folder, opts)
        cmd += ['-o', output_template]

        cmd.append(url)
        return cmd

    # ── Progress parser ──────────────────────────────────────

    def _parse_progress(self, line: str) -> Optional[dict]:
        m = re.search(
            r'\[download\]\s+([\d.]+)%\s+of\s+([\d.]+)(\w+)\s+at\s+([\d.]+)(\w+/s)'
            r'(?:\s+ETA\s+([\d:]+))?(?:\s+\(frag\s+(\d+)/(\d+)\))?',
            line
        )
        if m:
            percent  = float(m.group(1))
            size_val = float(m.group(2))
            size_unit = m.group(3)
            speed_val = float(m.group(4))
            speed_unit = m.group(5)
            eta_str   = m.group(6) or ''
            frag_cur  = m.group(7)
            frag_tot  = m.group(8)

            total_bytes = _parse_size(size_val, size_unit)
            speed       = _parse_speed(speed_val, speed_unit)
            eta         = _parse_eta(eta_str)

            return {
                'percent':    percent,
                'total_bytes': total_bytes,
                'speed':      speed,
                'eta':        eta,
                'fragment':   f'{frag_cur}/{frag_tot}' if frag_cur else '',
            }

        if '[download] 100%' in line:
            return {'percent': 100, 'speed': 0, 'eta': 0}

        return None

    # ── Job control ──────────────────────────────────────────

    def pause_job(self, job_id: str) -> bool:
        proc = self._processes.get(job_id)
        if not proc:
            return False
        try:
            import signal
            os.kill(proc.pid, signal.SIGSTOP)
            self.db.update_job(job_id, {'state': 'paused'})
            return True
        except (AttributeError, ProcessLookupError):
            self.db.update_job(job_id, {'state': 'paused'})
            return True

    def resume_job(self, job_id: str) -> bool:
        proc = self._processes.get(job_id)
        if proc:
            try:
                import signal
                os.kill(proc.pid, signal.SIGCONT)
                self.db.update_job(job_id, {'state': 'running'})
                return True
            except (AttributeError, ProcessLookupError):
                pass

        job = self.db.get_job(job_id)
        if job:
            self.db.update_job(job_id, {'state': 'queued'})
        return False

    def cancel_job(self, job_id: str) -> bool:
        proc = self._processes.get(job_id)
        self.db.update_job(job_id, {'state': 'cancelled'})
        if proc:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            self._processes.pop(job_id, None)
        return True

    def cancel_all(self):
        for job_id in list(self._processes.keys()):
            self.cancel_job(job_id)

    def pause_all(self):
        for job_id in list(self._processes.keys()):
            self.pause_job(job_id)

    def resume_all(self):
        active = self.db.get_jobs(state_filter='paused')
        for job in active:
            self.resume_job(job['id'])

    # ── YouTube Uncategorized ─────────────────────────────────────

    def _get_channel_id(self, url_or_id: str) -> Optional[str]:
        """Resolve a channel URL or ID to a channel_id."""
        if url_or_id.startswith('UC') and len(url_or_id) == 24:
            return url_or_id
        try:
            info = self.extract_info(url_or_id, {'timeout': 30})
            cid = info.get('channel_id') or info.get('uploader_id', '')
            if cid and cid.startswith('UC'):
                return cid
        except Exception:
            pass
        return None

    def get_channel_uploads(self, channel_id: str, limit: int = 200) -> list:
        """Fetch all uploads from a YouTube channel."""
        url = f'https://www.youtube.com/channel/{channel_id}/videos'
        try:
            info = self.extract_info(url, {'timeout': 60, 'no_playlist': False})
            entries = info.get('entries') or []
            videos = []
            for entry in entries[:limit]:
                if entry and entry.get('id'):
                    videos.append({
                        'id': entry['id'],
                        'title': entry.get('title', ''),
                        'upload_date': entry.get('upload_date', ''),
                        'duration': entry.get('duration', 0),
                        'url': f'https://youtu.be/{entry["id"]}',
                    })
            return videos
        except Exception as e:
            logger.error(f'get_channel_uploads error: {e}')
            return []

    def get_uncategorized(self, channel_url: str) -> dict:
        """
        Find videos uploaded by a channel that are NOT in any of
        the channel's public playlists.
        """
        channel_id = self._get_channel_id(channel_url)
        if not channel_id:
            return {'error': 'Could not resolve channel ID', 'channel_id': None}

        all_uploads = self.get_channel_uploads(channel_id)
        upload_ids = {v['id'] for v in all_uploads}

        # Get all playlist IDs for this channel
        playlist_ids = set()
        try:
            pl_url = f'https://www.youtube.com/channel/{channel_id}/playlists'
            pl_info = self.extract_info(pl_url, {'timeout': 60, 'no_playlist': False})
            pl_entries = pl_info.get('entries') or []
            for entry in pl_entries:
                if entry and entry.get('id'):
                    playlist_ids.add(entry['id'])
        except Exception:
            pass

        # Get all video IDs that appear in any playlist
        playlist_video_ids = set()
        for pl_id in playlist_ids:
            try:
                pl_url = f'https://www.youtube.com/playlist?list={pl_id}'
                pl_info = self.extract_info(pl_url, {'timeout': 60, 'no_playlist': False})
                pl_entries = pl_info.get('entries') or []
                for entry in pl_entries:
                    if entry and entry.get('id'):
                        playlist_video_ids.add(entry['id'])
            except Exception:
                continue

        uncategorized_ids = upload_ids - playlist_video_ids
        uncategorized = [v for v in all_uploads if v['id'] in uncategorized_ids]

        return {
            'channel_id': channel_id,
            'total_uploads': len(all_uploads),
            'in_playlists': len(playlist_video_ids),
            'uncategorized': len(uncategorized),
            'videos': uncategorized,
        }

    # ── Latest-only (per-channel date tracking) ──────────────────

    def _latest_report_path(self) -> Path:
        dl_folder = self.settings.get('dl_folder', DOWNLOAD_DIR)
        return Path(dl_folder) / '.megadl_latest.json'

    def get_latest_per_channel(self) -> dict:
        """Read the latest-download tracking file."""
        path = self._latest_report_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, Exception):
                pass
        return {}

    def save_latest_per_channel(self, channel_id: str, video_id: str, upload_date: str):
        """Record that a video was downloaded, so we skip older ones next time."""
        data = self.get_latest_per_channel()
        existing = data.get(channel_id, {})
        if upload_date and (not existing.get('upload_date') or upload_date > existing.get('upload_date', '')):
            data[channel_id] = {'video_id': video_id, 'upload_date': upload_date}
        elif video_id and not existing.get('video_id'):
            data[channel_id] = {'video_id': video_id, 'upload_date': upload_date or ''}
        try:
            self._latest_report_path().write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception:
            pass

    def filter_latest_only(self, channel_url: str, videos: list) -> list:
        """Filter videos to only those newer than last download."""
        channel_id = self._get_channel_id(channel_url)
        if not channel_id:
            return videos
        report = self.get_latest_per_channel()
        last = report.get(channel_id, {})
        last_date = last.get('upload_date', '')
        if not last_date:
            return videos
        filtered = [v for v in videos if v.get('upload_date', '') > last_date]
        return filtered

    # ── yt-dlp update ─────────────────────────────────────────────

    def check_ytdlp_update(self) -> dict:
        """Check if a yt-dlp update is available."""
        ytdlp = self.find_binary('yt-dlp')
        current = self.get_version(ytdlp) if ytdlp else 'not installed'
        try:
            r = subprocess.run(
                [ytdlp, '--update', '--version'] if ytdlp else [],
                capture_output=True, text=True, timeout=30
            )
            return {
                'current': current,
                'update_available': r.returncode == 0 and '--update' not in r.stdout,
                'output': r.stdout.strip()[:300] or r.stderr.strip()[:300],
            }
        except Exception as e:
            return {'current': current, 'update_available': False, 'error': str(e)}

    def update_ytdlp(self) -> dict:
        """Update yt-dlp to latest version."""
        ytdlp = self.find_binary('yt-dlp')
        if not ytdlp:
            return {'success': False, 'error': 'yt-dlp not found'}
        try:
            r = subprocess.run(
                [ytdlp, '--update'],
                capture_output=True, text=True, timeout=120
            )
            return {
                'success': r.returncode == 0 or 'already up to date' in r.stdout.lower(),
                'output': r.stdout.strip()[:500] or r.stderr.strip()[:500],
                'version': self.get_version(ytdlp),
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


_SIZE_MULTIPLIERS = {
    'B': 1, 'KB': 1024, 'KIB': 1024,
    'MB': 1024**2, 'MIB': 1024**2,
    'GB': 1024**3, 'GIB': 1024**3,
    'TB': 1024**4, 'TIB': 1024**4,
}

def _parse_size(val: float, unit: str) -> int:
    unit = unit.upper().replace('I', 'I')
    mult = _SIZE_MULTIPLIERS.get(unit, 1)
    return int(val * mult)

def _parse_speed(val: float, unit: str) -> float:
    unit = unit.upper().split('/')[0]
    mult = _SIZE_MULTIPLIERS.get(unit, 1)
    return val * mult

def _parse_eta(eta_str: str) -> int:
    if not eta_str:
        return 0
    parts = eta_str.strip().split(':')
    try:
        parts = [int(p) for p in parts]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except ValueError:
        pass
    return 0
