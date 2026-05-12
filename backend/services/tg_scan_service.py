"""
MegaDL — services/tg_scan_service.py
Telegram media scanning service: count and size estimation by media type.
"""

import logging
from typing import Optional, Callable, Dict

logger = logging.getLogger('megadl.tg_scan')


class TelegramScanService:
    """Scan Telegram chats for media with filtering by type and size calculation."""

    def __init__(self, telegram_service):
        """
        Args:
            telegram_service: TelegramService instance for async client access.
        """
        self.tg_service = telegram_service

    def scan_chat_media(self, dialog_id: int, media_types: Optional[list] = None,
                        limit_per_type: Optional[Dict[str, int]] = None,
                        on_progress: Optional[Callable] = None) -> dict:
        """
        Scan a chat for media by type and estimate total size.

        Args:
            dialog_id: Telegram dialog/chat ID
            media_types: List of media types to scan (e.g., ['photo', 'video', 'document', 'audio'])
                        If None, scans all types.
            limit_per_type: Dict mapping media type to max count (e.g., {'photo': 50, 'video': 10})
            on_progress: Optional callback(current_count, total_estimate) for progress updates

        Returns:
            {
                'ok': True,
                'dialog_id': int,
                'media': {
                    'photo': {'count': int, 'total_size': int, 'messages': [...]},
                    'video': {...},
                    'document': {...},
                    'audio': {...}
                },
                'total_count': int,
                'total_size': int,
            }
        """
        import asyncio

        async def _do():
            try:
                await self.tg_service._ensure_authorized()
            except RuntimeError as e:
                return {
                    'ok': False,
                    'error': str(e),
                    'dialog_id': dialog_id,
                }

            client = await self.tg_service._get_client()

            try:
                entity = await client.get_entity(dialog_id)
            except Exception as e:
                return {
                    'ok': False,
                    'error': f'Cannot get entity: {e}',
                    'dialog_id': dialog_id,
                }

            # Default: scan all media types
            if not media_types:
                media_types = ['photo', 'video', 'document', 'audio']

            from telethon.tl.types import (
                InputMessagesFilterPhotos,
                InputMessagesFilterVideo,
                InputMessagesFilterDocument,
                InputMessagesFilterMusic,
                InputMessagesFilterVoice,
            )

            media_filters = {
                'photo': InputMessagesFilterPhotos(),
                'video': InputMessagesFilterVideo(),
                'document': InputMessagesFilterDocument(),
                'audio': InputMessagesFilterMusic(),
            }

            result = {
                'ok': True,
                'dialog_id': dialog_id,
                'media': {},
                'total_count': 0,
                'total_size': 0,
            }

            total_scanned = 0

            for media_type in media_types:
                if media_type not in media_filters:
                    logger.warning(f'Unknown media type: {media_type}')
                    continue

                limit = limit_per_type.get(media_type, 1000) if limit_per_type else 1000
                count = 0
                total_size = 0
                messages = []

                try:
                    msg_filter = media_filters[media_type]
                    async for msg in client.iter_messages(entity, filter=msg_filter, limit=limit):
                        if msg.media:
                            file_size = getattr(msg.file, 'size', 0) if msg.file else 0
                            total_size += file_size
                            count += 1
                            total_scanned += 1

                            # Collect message details
                            messages.append({
                                'id': msg.id,
                                'date': str(msg.date) if msg.date else '',
                                'size': file_size,
                                'filename': getattr(msg.file, 'name', '') if msg.file else '',
                                'mime_type': getattr(msg.file, 'mime_type', '') if msg.file else '',
                                'duration': getattr(msg.media, 'duration', 0) if msg.media else 0,
                            })

                            if on_progress:
                                on_progress(total_scanned, total_size)

                except Exception as e:
                    logger.warning(f'Error scanning {media_type}: {e}')
                    continue

                result['media'][media_type] = {
                    'count': count,
                    'total_size': total_size,
                    'messages': messages,
                }
                result['total_count'] += count
                result['total_size'] += total_size

            return result

        try:
            return self.tg_service._run_async(_do())
        except Exception as e:
            logger.exception(f'Telegram scan_chat_media error: {e}')
            return {
                'ok': False,
                'error': str(e),
                'dialog_id': dialog_id,
            }

    def estimate_download_time(self, total_size: int, avg_speed_bps: float = 1_000_000) -> float:
        """
        Estimate download time in seconds.

        Args:
            total_size: Total size in bytes
            avg_speed_bps: Average speed in bytes per second (default: 1 MB/s)

        Returns:
            Estimated time in seconds
        """
        if avg_speed_bps <= 0:
            return 0
        return total_size / avg_speed_bps

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f'{size_bytes:.2f} {unit}'
            size_bytes /= 1024
        return f'{size_bytes:.2f} PB'
