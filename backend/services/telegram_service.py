"""
MegaDL — services/telegram_service.py
Telethon-based Telegram client: auth, dialog fetching, media download.
Uses a single global asyncio event loop — never recreated.
"""

import os
import re
import json
import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger('megadl.telegram')


class TelegramService:
    """Manages Telethon client lifecycle: connect, auth, dialogs, download."""

    def __init__(self, settings, db):
        self.settings = settings
        self.db       = db
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client  = None
        self._lock    = threading.Lock()
        self._started = False
        self._user_phone = None
        self.current_file = ""
        self._download_history: list = []
        self._ensure_session_dir()  # Ensure session directory exists

    # ── Event loop ─────────────────────────────────────────────

    def _ensure_session_dir(self):
        """Ensure telegram session directory exists."""
        session_dir = Path(self.settings.get('temp_dir', './temp')) / 'telegram_sessions'
        session_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self) -> Path:
        """Get or create the telegram session directory."""
        session_dir = Path(self.settings.get('temp_dir', './temp')) / 'telegram_sessions'
        return session_dir

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create the global asyncio event loop."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        """Run a coroutine in the global event loop thread-safely."""
        loop = self._get_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=120)
        else:
            return loop.run_until_complete(coro)

    # ── Client lifecycle ───────────────────────────────────────

    async def _get_client(self):
        """Lazy-init Telethon client without auto-starting (no prompt).
        
        Credentials priority:
        1. Settings (telegram_api_id, telegram_api_hash)
        2. Environment variables (TELEGRAM_API_ID, TELEGRAM_API_HASH)
        """
        if self._client is not None:
            return self._client

        try:
            from telethon import TelegramClient
        except ImportError:
            raise RuntimeError('telethon not installed. Run: pip install telethon cryptg')

        # Load API credentials with priority: settings → environment variables
        api_id = self.settings.get('telegram_api_id', '') or os.environ.get('TELEGRAM_API_ID', '')
        api_hash = self.settings.get('telegram_api_hash', '') or os.environ.get('TELEGRAM_API_HASH', '')

        if not api_id or not api_hash:
            raise RuntimeError('Telegram API_ID and API_HASH not configured. Add to settings or environment variables.')

        session_dir = self._get_session_dir()
        session_file = str(session_dir / 'user_session')

        self._client = TelegramClient(session_file, int(api_id), api_hash)
        logger.info(f'Telegram client initialized (session: {session_file})')
        return self._client

    async def _ensure_connected(self):
        """Connect the client if not already connected."""
        client = await self._get_client()
        if not client.is_connected():
            await client.connect()
            logger.info('Telegram client connected')

    async def _ensure_authorized(self):
        """Ensure client is connected and authorized."""
        client = await self._get_client()
        if not client.is_connected():
            await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError('Not authorized. Use send_code + sign_in first.')

    async def _disconnect_client(self):
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    # ── Auth ───────────────────────────────────────────────────

    def send_code(self, phone: str) -> dict:
        """Request Telegram login code. Returns dict with phone_registered status."""

        async def _do():
            await self._ensure_connected()
            client = await self._get_client()
            if await client.is_user_authorized():
                return {'ok': True, 'authorized': True, 'phone': phone}

            sent = await client.send_code_request(phone)
            self._user_phone = phone
            return {
                'ok': True,
                'authorized': False,
                'phone': phone,
                'phone_code_hash': getattr(sent, 'phone_code_hash', ''),
                'timeout': getattr(sent, 'timeout', 30),
            }

        try:
            return self._run_async(_do())
        except Exception as e:
            err_str = str(e)
            logger.exception(f'Telegram send_code error: {e}')

            # Handle specific Telethon errors with user-friendly messages
            if 'all available options' in err_str.lower():
                return {
                    'ok': False,
                    'error': 'All verification methods exhausted. Please wait 10 minutes before trying again, or use a different phone number.',
                    'code': 'ALL_OPTIONS_USED',
                    'retry_after': 600,
                }
            if 'too much' in err_str.lower() or 'flood' in err_str.lower():
                return {
                    'ok': False,
                    'error': 'Too many attempts. Please wait a few minutes and try again.',
                    'code': 'FLOOD_WAIT',
                    'retry_after': 120,
                }
            if 'phone number' in err_str.lower() and 'invalid' in err_str.lower():
                return {
                    'ok': False,
                    'error': 'Invalid phone number. Use international format (e.g., +1234567890).',
                    'code': 'INVALID_PHONE',
                }
            if 'phone code' in err_str.lower() and 'empty' in err_str.lower():
                return {
                    'ok': False,
                    'error': 'You requested a resend. A new code has been sent.',
                    'code': 'RESEND',
                }
            return {'ok': False, 'error': err_str, 'code': 'UNKNOWN'}

    def sign_in(self, phone: str, code: str, password: str = '') -> dict:
        """Complete Telegram login with code (and optional 2FA password)."""

        async def _do():
            await self._ensure_connected()
            client = await self._get_client()
            try:
                await client.sign_in(phone, code)
            except Exception as e:
                err_str = str(e)
                # 2FA required
                if 'password' in err_str.lower() or '2fa' in err_str.lower():
                    if password:
                        await client.sign_in(password=password)
                    else:
                        return {'ok': False, 'error': '2FA required', 'need_password': True}
                else:
                    return {'ok': False, 'error': err_str}

            self.db.save_settings({'telegram_phone': phone})
            me = await client.get_me()
            return {
                'ok': True,
                'authorized': True,
                'user': {
                    'id': me.id,
                    'phone': phone,
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                }
            }

        try:
            return self._run_async(_do())
        except Exception as e:
            logger.exception(f'Telegram sign_in error: {e}')
            return {'ok': False, 'error': str(e)}

    def sign_in_password(self, password: str) -> dict:
        """Complete 2FA sign-in."""
        return self.sign_in(self._user_phone or '', '', password)

    def logout(self) -> dict:
        """Disconnect and clear session."""

        async def _do():
            await self._disconnect_client()
            session_dir = Path(self.settings.get('temp_dir', './temp')) / 'telegram_sessions'
            if session_dir.exists():
                for f in session_dir.glob('*'):
                    f.unlink()
            return {'ok': True}

        try:
            return self._run_async(_do())
        except Exception:
            return {'ok': True}

    def is_authorized(self) -> bool:
        """Check if user is currently authorized."""

        async def _do():
            try:
                await self._ensure_connected()
                client = await self._get_client()
                return await client.is_user_authorized()
            except Exception:
                return False

        try:
            return self._run_async(_do())
        except Exception:
            return False

    def get_me(self) -> dict:
        """Get current user info."""

        async def _do():
            try:
                await self._ensure_authorized()
            except RuntimeError:
                return {'ok': False, 'authorized': False}
            client = await self._get_client()
            me = await client.get_me()
            return {
                'ok': True,
                'user': {
                    'id': me.id,
                    'phone': getattr(me, 'phone', ''),
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                }
            }

        try:
            return self._run_async(_do())
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ── Dialogs ────────────────────────────────────────────────

    def get_dialogs(self) -> list:
        """Fetch all user dialogs (channels, groups, private chats)."""

        async def _do():
            try:
                await self._ensure_authorized()
            except RuntimeError:
                return []
            client = await self._get_client()

            dialogs = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                dialog_type = 'unknown'
                if hasattr(entity, 'broadcast') and entity.broadcast:
                    dialog_type = 'channel'
                elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                    dialog_type = 'group'
                elif hasattr(entity, 'megagroup') and entity.megagroup:
                    dialog_type = 'group'
                elif dialog.is_user:
                    dialog_type = 'user'
                elif dialog.is_group:
                    dialog_type = 'group'

                dialogs.append({
                    'id': dialog.id,
                    'name': dialog.name or 'Unknown',
                    'type': dialog_type,
                    'unread_count': dialog.unread_count,
                    'message': dialog.message.text[:200] if dialog.message and dialog.message.text else '',
                    'date': str(dialog.date) if dialog.date else '',
                    'entity_id': str(dialog.id),
                })

            return dialogs

        try:
            return self._run_async(_do())
        except Exception as e:
            logger.exception(f'Telegram get_dialogs error: {e}')
            return []

    def get_dialog_messages(self, dialog_id: int, limit: int = 100, offset_id: int = 0) -> list:
        """Fetch messages from a specific dialog."""

        async def _do():
            try:
                await self._ensure_authorized()
            except RuntimeError:
                return []
            client = await self._get_client()

            from telethon import utils
            try:
                entity = await client.get_entity(dialog_id)
            except Exception:
                return []

            messages = []
            async for msg in client.iter_messages(entity, limit=limit, offset_id=offset_id):
                media_type = self._detect_media_type(msg)
                messages.append({
                    'id': msg.id,
                    'date': str(msg.date) if msg.date else '',
                    'text': (msg.text or '')[:500],
                    'media_type': media_type,
                    'has_media': msg.media is not None,
                    'file_name': getattr(msg.file, 'name', '') if msg.file else '',
                    'size': getattr(msg.file, 'size', 0) if msg.file else 0,
                    'mime': getattr(msg.file, 'mime_type', '') if msg.file else '',
                    'duration': getattr(msg.media, 'duration', 0) if msg.media else 0,
                })

            return messages

        try:
            return self._run_async(_do())
        except Exception as e:
            logger.exception(f'Telegram get_messages error: {e}')
            return []

    def _detect_media_type(self, msg) -> str:
        """Detect media type from a message."""
        if not msg.media:
            return 'text'
        try:
            from telethon.tl.types import (
                MessageMediaPhoto, MessageMediaDocument, MessageMediaVideo,
                MessageMediaAudio, MessageMediaWebPage, MessageMediaPoll
            )
            if isinstance(msg.media, MessageMediaPhoto):
                return 'photo'
            if isinstance(msg.media, MessageMediaVideo):
                return 'video'
            if isinstance(msg.media, MessageMediaAudio):
                return 'audio'
            if isinstance(msg.media, MessageMediaDocument):
                if msg.file and msg.file.mime_type:
                    mt = msg.file.mime_type
                    if mt.startswith('video/'):
                        return 'video'
                    if mt.startswith('audio/'):
                        return 'audio'
                    if mt.startswith('image/'):
                        return 'photo'
                return 'document'
            if isinstance(msg.media, MessageMediaWebPage):
                return 'webpage'
            if isinstance(msg.media, MessageMediaPoll):
                return 'poll'
        except ImportError:
            pass
        return 'document'

    # ── Download ───────────────────────────────────────────────

    def download_media(self, dialog_id: int, msg_ids: list, dl_folder: str = '',
                       on_progress: Callable = None, on_complete: Callable = None,
                       on_error: Callable = None,
                       chat_name: str = '') -> list:
        """Download media from specific messages. Returns list of results."""
        results = []

        async def _do():
            nonlocal results
            try:
                await self._ensure_authorized()
            except RuntimeError:
                if on_error:
                    on_error('Not authorized')
                return []
            client = await self._get_client()

            try:
                entity = await client.get_entity(dialog_id)
            except Exception as e:
                if on_error:
                    on_error(f'Cannot get entity: {e}')
                return []

            chat_label = chat_name or str(dialog_id)
            folder = Path(dl_folder or self.settings.get('dl_folder', './downloads')) / 'Telegram' / _safe_dir_name(chat_label)
            folder.mkdir(parents=True, exist_ok=True)

            from services.tg_filename_service import TelegramFilenameService
            fn_service = TelegramFilenameService()

            downloaded = []
            for mid in msg_ids:
                try:
                    msg = await client.get_messages(entity, ids=mid)
                    if not msg or not msg.media:
                        continue

                    fname = fn_service.get_original_filename(msg)
                    self.current_file = fname

                    path = await msg.download_media(
                        file=str(folder),
                        progress_callback=lambda sent, total, msg_id=mid: (
                            on_progress(msg_id, sent, total) if on_progress else None
                        )
                    )
                    self.current_file = ''
                    if path:
                        file_size = os.path.getsize(str(path)) if os.path.exists(str(path)) else 0
                        file_type = _detect_type(msg)
                        downloaded.append({
                            'msg_id': mid,
                            'path': str(path),
                            'size': file_size,
                        })
                        self._add_history(chat_label, fname or str(mid), str(path), file_size, file_type, 'completed')
                        if on_complete:
                            on_complete(mid, str(path))
                except Exception as e:
                    logger.exception(f'Download msg {mid} failed: {e}')
                    self._add_history(chat_label, str(mid), '', 0, 'unknown', f'error: {e}')
                    if on_error:
                        on_error(mid, str(e))

            results = downloaded
            return downloaded

        try:
            self._run_async(_do())
        except Exception as e:
            logger.exception(f'Telegram download_media error: {e}')
            if on_error:
                on_error(str(e))

        return results

    def forward_to_bot(self, bot_token: str, dialog_id: int, msg_ids: list) -> dict:
        """Forward messages to a bot chat (when bot is in the group/channel)."""

        async def _do():
            try:
                from telethon import TelegramClient
            except ImportError:
                return {'ok': False, 'error': 'telethon not installed'}

            api_id = self.settings.get('telegram_api_id', '') or os.environ.get('TELEGRAM_API_ID', '')
            api_hash = self.settings.get('telegram_api_hash', '') or os.environ.get('TELEGRAM_API_HASH', '')

            bot_client = TelegramClient(
                f'bot_{bot_token.split(":")[0]}',
                int(api_id), api_hash
            )
            await bot_client.start(bot_token=bot_token)

            try:
                entity = await bot_client.get_entity(int(dialog_id))
                me = await bot_client.get_me()
                forwarded = []
                for mid in msg_ids:
                    msg = await bot_client.get_messages(entity, ids=mid)
                    if msg:
                        await msg.forward_to(me.id)
                        forwarded.append(mid)
                return {'ok': True, 'forwarded': len(forwarded), 'total': len(msg_ids)}
            finally:
                await bot_client.disconnect()

        try:
            return self._run_async(_do())
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ── Bot download (content forwarded to bot) ────────────────

    def download_from_bot(self, bot_token: str, dl_folder: str = '') -> list:
        """Download all media from a bot's chat (after content was forwarded to it)."""

        async def _do():
            try:
                from telethon import TelegramClient
            except ImportError:
                return []

            api_id = self.settings.get('telegram_api_id', '') or os.environ.get('TELEGRAM_API_ID', '')
            api_hash = self.settings.get('telegram_api_hash', '') or os.environ.get('TELEGRAM_API_HASH', '')

            bot_client = TelegramClient(
                f'bot_{bot_token.split(":")[0]}',
                int(api_id), api_hash
            )
            await bot_client.start(bot_token=bot_token)

            folder = Path(dl_folder or self.settings.get('dl_folder', './downloads')) / 'Telegram' / 'Bot'
            folder.mkdir(parents=True, exist_ok=True)

            downloaded = []
            try:
                me = await bot_client.get_me()
                async for msg in bot_client.iter_messages(me.id, limit=500):
                    if msg.media:
                        path = await msg.download_media(file=str(folder))
                        if path:
                            downloaded.append({
                                'msg_id': msg.id,
                                'path': str(path),
                                'date': str(msg.date),
                            })
                return downloaded
            finally:
                await bot_client.disconnect()

        try:
            return self._run_async(_do())
        except Exception as e:
            logger.exception(f'Bot download error: {e}')
            return []


    # ── Bot Pool ──────────────────────────────────────────────────

    def _get_bot_pool(self) -> list:
        """Get saved bot tokens pool."""
        raw = self.settings.get('telegram_bot_pool') or '[]'
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (json.JSONDecodeError, TypeError):
            return []

    def _save_bot_pool(self, pool: list):
        self.settings.set('telegram_bot_pool', json.dumps(pool))
        self.settings.save()

    def add_bot_token(self, token: str) -> dict:
        """Add a bot token to the pool. Validate format."""
        token = token.strip()
        if not token or ':' not in token:
            return {'ok': False, 'error': 'Invalid bot token format'}
        pool = self._get_bot_pool()
        if any(t == token for t in pool):
            return {'ok': False, 'error': 'Bot token already in pool'}
        pool.append(token)
        self._save_bot_pool(pool)
        return {'ok': True, 'pool': list(pool)}

    def remove_bot_token(self, token: str) -> dict:
        """Remove a bot token from the pool."""
        pool = self._get_bot_pool()
        pool = [t for t in pool if t != token]
        self._save_bot_pool(pool)
        return {'ok': True, 'pool': list(pool)}

    def list_bot_pool(self) -> list:
        """Return all bot tokens (stored locally, no masking needed)."""
        return list(self._get_bot_pool())

    def get_bot_status(self, token: str) -> dict:
        """Check if a bot token is valid by attempting to connect."""
        async def _do():
            try:
                from telethon import TelegramClient
            except ImportError:
                return {'ok': False, 'error': 'telethon not installed'}
            api_id = self.settings.get('telegram_api_id', '') or os.environ.get('TELEGRAM_API_ID', '')
            api_hash = self.settings.get('telegram_api_hash', '') or os.environ.get('TELEGRAM_API_HASH', '')
            bot_client = TelegramClient(f'bot_pool_{token.split(":")[0]}', int(api_id), api_hash)
            await bot_client.start(bot_token=token)
            try:
                me = await bot_client.get_me()
                return {'ok': True, 'username': me.username or 'unknown', 'id': me.id}
            finally:
                await bot_client.disconnect()
        try:
            return self._run_async(_do())
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def get_all_bot_statuses(self) -> list:
        """Get status for all bots in pool."""
        results = []
        for token in self._get_bot_pool():
            status = self.get_bot_status(token)
            status['token_masked'] = self._mask_token(token)
            results.append(status)
        return results

    def download_all_bot_media(self, bot_token: str, dl_folder: str = '') -> dict:
        """Download all media from a bot AND queue as regular download jobs."""
        folder = Path(dl_folder or self.settings.get('dl_folder', './downloads')) / 'Telegram' / 'Bot'
        folder.mkdir(parents=True, exist_ok=True)
        result = self.download_from_bot(bot_token, dl_folder)
        return {'ok': True, 'count': len(result), 'items': result}

    @staticmethod
    def _mask_token(token: str) -> str:
        if ':' in token:
            prefix = token.split(':')[0]
            return f'{prefix}:****{token[-4:]}' if len(token) > 10 else f'{prefix}:****'
        return '****'

    # ── History ──────────────────────────────────────────────────

    def _history_path(self) -> Path:
        dl_folder = self.settings.get('dl_folder', './downloads')
        return Path(dl_folder) / '.telegram_history.json'

    def _load_history(self) -> list:
        if self._download_history:
            return self._download_history
        path = self._history_path()
        try:
            if path.exists():
                self._download_history = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            self._download_history = []
        return self._download_history

    def _save_history(self):
        path = self._history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._download_history, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    def _add_history(self, chat_name: str, filename: str, file_path: str, file_size: int, file_type: str, status: str = 'completed'):
        history = self._load_history()
        history.append({
            'chat': chat_name,
            'filename': filename,
            'path': file_path,
            'size': file_size,
            'type': file_type,
            'status': status,
            'time': datetime.utcnow().timestamp(),
        })
        if len(history) > 2000:
            history[:] = history[-2000:]
        self._download_history = history
        self._save_history()

    def get_history(self, limit: int = 50) -> list:
        history = self._load_history()
        return history[-limit:]

    def save_creds(self, api_id: str, api_hash: str):
        """Save Telegram API credentials to settings.json and .env file.
        
        Credentials are saved in two locations for persistence:
        1. settings.json (MegaDL's config)
        2. .env file (environment variable fallback)
        """
        # Save to settings
        self.settings.set('telegram_api_id', api_id)
        self.settings.set('telegram_api_hash', api_hash)
        self.settings.save()
        logger.info('Telegram credentials saved to settings.json')
        
        # Also save to .env as fallback
        try:
            env_path = Path(__file__).parent.parent.parent / '.env'
            existing = env_path.read_text() if env_path.exists() else ''
            
            # Update or add TELEGRAM_API_ID
            if 'TELEGRAM_API_ID=' in existing:
                existing = re.sub(r'TELEGRAM_API_ID=.*', f'TELEGRAM_API_ID={api_id}', existing)
            else:
                if existing and not existing.endswith('\n'):
                    existing += '\n'
                existing += f'TELEGRAM_API_ID={api_id}\n'
            
            # Update or add TELEGRAM_API_HASH
            if 'TELEGRAM_API_HASH=' in existing:
                existing = re.sub(r'TELEGRAM_API_HASH=.*', f'TELEGRAM_API_HASH={api_hash}', existing)
            else:
                if existing and not existing.endswith('\n'):
                    existing += '\n'
                existing += f'TELEGRAM_API_HASH={api_hash}\n'
            
            env_path.write_text(existing)
            logger.info('Telegram credentials saved to .env file')
        except Exception as e:
            logger.warning(f'Could not save credentials to .env: {e}')

    def get_creds_status(self) -> dict:
        """Check credential status and source."""
        api_id = self.settings.get('telegram_api_id', '')
        api_hash = self.settings.get('telegram_api_hash', '')
        env_api_id = os.environ.get('TELEGRAM_API_ID', '')
        env_api_hash = os.environ.get('TELEGRAM_API_HASH', '')
        
        return {
            'ok': True,
            'has_api_id': bool(api_id),
            'has_api_hash': bool(api_hash),
            'source': 'settings' if api_id and api_hash else ('environment' if env_api_id and env_api_hash else 'none'),
            'api_id_masked': f'{api_id[:8]}...' if api_id else None,
        }


def _safe_dir_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', str(name).strip())[:200] or 'chat'

def _get_original_filename(message) -> str:
    if message.document:
        from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeAudio, DocumentAttributeVideo
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                return _safe_dir_name(attr.file_name)
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeAudio):
                performer = attr.performer or ''
                title = attr.title or ''
                if performer or title:
                    base = f'{performer} - {title}'.strip(' -')
                    ext = getattr(message.file, 'ext', '.mp3') or '.mp3'
                    return _safe_dir_name(base) + ext
            if isinstance(attr, DocumentAttributeVideo):
                ext = getattr(message.file, 'ext', '.mp4') or '.mp4'
                date_str = message.date.strftime('%Y%m%d_%H%M%S') if message.date else str(message.id)
                return f'video_{date_str}{ext}'
        ext = getattr(message.file, 'ext', '') or ''
        return f'file_{message.id}{ext}'
    elif message.photo:
        date_str = message.date.strftime('%Y%m%d_%H%M%S') if message.date else str(message.id)
        return f'photo_{date_str}.jpg'
    else:
        ext = getattr(message.file, 'ext', '') or ''
        return f'media_{message.id}{ext}'

def _detect_type(message) -> str:
    if message.photo:
        return 'photo'
    if message.video:
        return 'video'
    if message.audio or message.voice:
        return 'audio'
    if message.document:
        return 'document'
    return 'unknown'

def _now_iso() -> str:
    return datetime.utcnow().isoformat()
