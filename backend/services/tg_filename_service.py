"""
MegaDL — services/tg_filename_service.py
Telegram filename extraction with 7-layer fallback strategy.
Preserves original Telegram filenames when possible.
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger('megadl.tg_filename')


class TelegramFilenameService:
    """Extract and preserve original Telegram filenames using intelligent fallback."""

    # 7-layer fallback strategy for filename extraction
    FALLBACK_LAYERS = [
        'document_attribute',      # Layer 1: DocumentAttributeFilename
        'audio_metadata',          # Layer 2: DocumentAttributeAudio (performer/title)
        'video_metadata',          # Layer 3: DocumentAttributeVideo metadata
        'caption',                 # Layer 4: Message caption text
        'date_based',              # Layer 5: Date-based naming (YYYYMMDD_HHMMSS)
        'message_id',              # Layer 6: Message ID fallback
        'generic',                 # Layer 7: Generic media_<ID>.<ext>
    ]

    @staticmethod
    def get_original_filename(message) -> str:
        """
        Extract original filename from Telegram message using 7-layer fallback.

        Priority order:
        1. DocumentAttributeFilename (explicit filename attribute)
        2. Audio metadata (performer/title)
        3. Video metadata (title if available)
        4. Message caption text
        5. Date-based naming (YYYYMMDD_HHMMSS)
        6. Message ID-based naming
        7. Generic fallback (media_<ID>.<ext>)

        Args:
            message: Telethon Message object

        Returns:
            Safe filename string with preserved original name when possible
        """
        try:
            # Layer 1: DocumentAttributeFilename
            if message.document:
                from telethon.tl.types import (
                    DocumentAttributeFilename,
                    DocumentAttributeAudio,
                    DocumentAttributeVideo,
                )

                # Explicit filename attribute
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                        return TelegramFilenameService._safe_filename(attr.file_name)

                # Layer 2: Audio metadata (performer/title)
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeAudio):
                        performer = (attr.performer or '').strip()
                        title = (attr.title or '').strip()
                        if performer or title:
                            # Format: "Performer - Title.ext"
                            base = f'{performer} - {title}'.strip(' -')
                            ext = TelegramFilenameService._get_extension(message)
                            if base:
                                return TelegramFilenameService._safe_filename(base) + ext
                        # Fallback to title only
                        if title:
                            ext = TelegramFilenameService._get_extension(message)
                            return TelegramFilenameService._safe_filename(title) + ext

                # Layer 3: Video metadata (title, width x height description)
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        title = getattr(attr, 'title', None)
                        if title:
                            ext = TelegramFilenameService._get_extension(message)
                            return TelegramFilenameService._safe_filename(title) + ext
                        # Fallback: dimensions-based
                        w = getattr(attr, 'w', 0) or 0
                        h = getattr(attr, 'h', 0) or 0
                        if w and h:
                            ext = TelegramFilenameService._get_extension(message)
                            return f'video_{w}x{h}{ext}'

            # Layer 4: Message caption
            if message.text and message.text.strip():
                caption = message.text.strip()[:100]  # Limit caption length
                if len(caption) > 5:  # Only use if meaningful
                    ext = TelegramFilenameService._get_extension(message)
                    return TelegramFilenameService._safe_filename(caption) + ext

            # Layer 5: Date-based naming
            if message.date:
                date_str = message.date.strftime('%Y%m%d_%H%M%S')
                media_type = TelegramFilenameService._detect_media_type(message)
                ext = TelegramFilenameService._get_extension(message)
                return f'{media_type}_{date_str}{ext}'

            # Layer 6: Message ID fallback
            ext = TelegramFilenameService._get_extension(message)
            media_type = TelegramFilenameService._detect_media_type(message)
            return f'{media_type}_{message.id}{ext}'

        except Exception as e:
            logger.warning(f'Error extracting filename, using generic fallback: {e}')

        # Layer 7: Generic fallback
        ext = TelegramFilenameService._get_extension(message)
        return f'media_{message.id}{ext}'

    @staticmethod
    def _detect_media_type(message) -> str:
        """Detect media type from message."""
        if message.photo:
            return 'photo'
        if message.video:
            return 'video'
        if message.audio or message.voice:
            return 'audio'
        if message.document:
            from telethon.tl.types import (
                DocumentAttributeAudio,
                DocumentAttributeVideo,
            )
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    return 'video'
                if isinstance(attr, DocumentAttributeAudio):
                    return 'audio'
            return 'document'
        return 'media'

    @staticmethod
    def _get_extension(message) -> str:
        """Extract file extension from message."""
        ext = ''
        if message.file:
            ext = getattr(message.file, 'ext', '')
        
        # Fallback: infer from media type if no extension
        if not ext:
            media_type = TelegramFilenameService._detect_media_type(message)
            ext_map = {
                'photo': '.jpg',
                'video': '.mp4',
                'audio': '.mp3',
                'document': '.bin',
            }
            ext = ext_map.get(media_type, '')
        
        return ext

    @staticmethod
    def _safe_filename(name: str, max_length: int = 200) -> str:
        """
        Sanitize filename: remove unsafe characters, limit length.

        Args:
            name: Original filename
            max_length: Maximum filename length (default: 200)

        Returns:
            Safe filename
        """
        # Remove/replace unsafe characters
        safe = re.sub(r'[\\/:*?"<>|]', '_', str(name).strip())
        # Remove leading/trailing dots and spaces
        safe = safe.strip('. ')
        # Collapse multiple underscores
        safe = re.sub(r'_{2,}', '_', safe)
        # Limit length
        safe = safe[:max_length]
        # Default if empty
        return safe or 'file'

    @staticmethod
    def extract_filename_info(message) -> dict:
        """
        Extract detailed filename information from message.

        Returns:
            {
                'filename': str (full filename with extension),
                'base_name': str (filename without extension),
                'extension': str (file extension),
                'media_type': str (photo, video, audio, document, text),
                'layer_used': str (which fallback layer was used),
                'source': str (filename source: DocumentAttribute, caption, date, id, generic),
            }
        """
        media_type = TelegramFilenameService._detect_media_type(message)
        ext = TelegramFilenameService._get_extension(message)

        # Determine which layer was used
        layer_used = 'generic'
        source = 'unknown'

        try:
            if message.document:
                from telethon.tl.types import (
                    DocumentAttributeFilename,
                    DocumentAttributeAudio,
                    DocumentAttributeVideo,
                )

                # Check Layer 1: Explicit filename
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                        layer_used = 'document_attribute'
                        source = 'DocumentAttributeFilename'
                        break

                # Check Layer 2: Audio metadata
                if layer_used == 'generic':
                    for attr in message.document.attributes:
                        if isinstance(attr, DocumentAttributeAudio):
                            performer = (attr.performer or '').strip()
                            title = (attr.title or '').strip()
                            if performer or title:
                                layer_used = 'audio_metadata'
                                source = 'DocumentAttributeAudio'
                                break

                # Check Layer 3: Video metadata
                if layer_used == 'generic':
                    for attr in message.document.attributes:
                        if isinstance(attr, DocumentAttributeVideo):
                            title = getattr(attr, 'title', None)
                            if title:
                                layer_used = 'video_metadata'
                                source = 'DocumentAttributeVideo'
                                break

            # Check Layer 4: Caption
            if layer_used == 'generic' and message.text and message.text.strip():
                if len(message.text.strip()) > 5:
                    layer_used = 'caption'
                    source = 'message_caption'

            # Check Layer 5: Date
            if layer_used == 'generic' and message.date:
                layer_used = 'date_based'
                source = 'message_date'

            # Otherwise Layer 6 or 7
            if layer_used == 'generic':
                layer_used = 'message_id'
                source = 'message_id'

        except Exception as e:
            logger.debug(f'Error determining layer: {e}')

        filename = TelegramFilenameService.get_original_filename(message)
        base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename

        return {
            'filename': filename,
            'base_name': base_name,
            'extension': ext,
            'media_type': media_type,
            'layer_used': layer_used,
            'source': source,
        }
