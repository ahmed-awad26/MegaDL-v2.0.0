"""MegaDL — routes/files_api.py"""

import os
import re
import mimetypes
import subprocess
from pathlib import Path
from flask import Blueprint, request, send_file, abort, Response
from .ping import ok, err, get_db, get_settings

files_bp = Blueprint('files', __name__)

# Cache for durations to avoid repeated ffprobe calls
_duration_cache = {}

# All media extensions yt-dlp can produce
MEDIA_EXTS = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.mp3', '.m4a',
              '.opus', '.ogg', '.wav', '.flac', '.aac', '.wma', '.flv',
              '.3gp', '.m4v', '.mpg', '.mpeg'}


def _dl_folder() -> Path:
    return Path(get_settings().get('dl_folder', './downloads'))


def _get_duration(filepath: Path) -> float:
    key = str(filepath)
    if key in _duration_cache:
        return _duration_cache[key]

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=duration', '-of', 'csv=p=0', str(filepath)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            dur = float(result.stdout.strip())
            _duration_cache[key] = dur
            return dur
    except Exception:
        pass
    return 0


def _is_media(name: str) -> bool:
    return Path(name).suffix.lower() in MEDIA_EXTS


def _scandir_recursive(base: Path, target: Path, recursive: bool) -> list:
    """Scan directory, optionally recursive. Returns sorted entries."""
    files = []
    if recursive:
        for entry in sorted(target.rglob('*'), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.is_dir():
                continue
            try:
                entry.relative_to(base.resolve())
            except ValueError:
                continue
            stat = entry.stat()
            info = {
                'name': entry.name,
                'path': str(entry.relative_to(base)),
                'type': 'file',
                'size': stat.st_size,
                'modified': stat.st_mtime,
            }
            if _is_media(entry.name):
                info['duration'] = _get_duration(entry)
            files.append(info)
    else:
        dirs_only = request.args.get('dirs', '') == '1'
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            stat = entry.stat()
            info = {
                'name': entry.name,
                'path': str(entry.relative_to(base)),
                'type': 'dir' if entry.is_dir() else 'file',
                'size': stat.st_size if entry.is_file() else 0,
                'modified': stat.st_mtime,
            }
            if entry.is_file() and _is_media(entry.name):
                info['duration'] = _get_duration(entry)
            if not (entry.is_dir() and dirs_only):
                files.append(info)
    return files


@files_bp.route('/api/files')
def list_files():
    rel_path = request.args.get('path', '')
    recursive = request.args.get('recursive', '').lower() in ('1', 'true', 'yes')

    base = _dl_folder()
    try:
        target = (base / rel_path).resolve()
        target.relative_to(base.resolve())
    except (ValueError, Exception):
        return err('Invalid path', 400)

    if not target.exists():
        return ok({'files': [], 'path': rel_path})

    try:
        files = _scandir_recursive(base, target, recursive)
    except PermissionError:
        return err('Permission denied', 403)

    return ok({'files': files, 'path': rel_path})


@files_bp.route('/api/files/info/<path:file_path>')
def file_info(file_path):
    """Return metadata for a file without downloading it."""
    base = _dl_folder()
    try:
        target = (base / file_path).resolve()
        target.relative_to(base.resolve())
    except ValueError:
        return err('Access denied', 403)

    if not target.is_file():
        return err('File not found', 404)

    stat = target.stat()
    mime, _ = mimetypes.guess_type(str(target))
    return ok({
        'file': {
            'exists':   True,
            'path':     str(target),
            'name':     target.name,
            'size':     stat.st_size,
            'mime':     mime or 'application/octet-stream',
            'modified': stat.st_mtime,
        }
    })


@files_bp.route('/api/files/download/<path:file_path>')
def download_file(file_path):
    """Download a file from storage (triggers browser save dialog)."""
    base = _dl_folder()
    try:
        target = (base / file_path).resolve()
        target.relative_to(base.resolve())
    except ValueError:
        abort(403)

    if not target.is_file():
        abort(404)

    mime, _ = mimetypes.guess_type(str(target))
    return send_file(str(target), mimetype=mime or 'application/octet-stream',
                     as_attachment=True, download_name=target.name)


@files_bp.route('/api/files/stream/<path:file_path>')
def stream_file(file_path):
    """Stream a media file inline for the browser player (no download)."""
    base = _dl_folder()
    try:
        target = (base / file_path).resolve()
        target.relative_to(base.resolve())
    except ValueError:
        abort(403)

    if not target.is_file():
        abort(404)

    mime, _ = mimetypes.guess_type(str(target))
    return send_file(str(target), mimetype=mime or 'application/octet-stream',
                     as_attachment=False)


@files_bp.route('/api/files/delete', methods=['POST'])
def delete_file():
    data = request.get_json(force=True) or {}
    path = data.get('path', '')
    base = _dl_folder()
    try:
        target = (base / path).resolve()
        target.relative_to(base.resolve())
    except ValueError:
        return err('Invalid path', 400)

    if not target.exists():
        return err('File not found', 404)

    try:
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            import shutil
            shutil.rmtree(str(target))
        return ok({'deleted': path})
    except Exception as e:
        return err(str(e), 500)


@files_bp.route('/api/files/rename', methods=['POST'])
def rename_file():
    data     = request.get_json(force=True) or {}
    old_path = data.get('path', '')
    new_name = data.get('name', '').strip()

    if not new_name or '/' in new_name or '\\' in new_name or '..' in new_name:
        return err('Invalid new name')

    base = _dl_folder()
    try:
        target = (base / old_path).resolve()
        target.relative_to(base.resolve())
    except ValueError:
        return err('Invalid path', 400)

    if not target.exists():
        return err('File not found', 404)

    new_target = target.parent / new_name
    try:
        target.rename(new_target)
        return ok({'renamed': str(new_target.relative_to(base))})
    except Exception as e:
        return err(str(e), 500)
