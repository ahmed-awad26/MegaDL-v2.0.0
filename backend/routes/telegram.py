"""MegaDL — routes/telegram.py"""

import os
from flask import Blueprint, request, jsonify
from .ping import ok, err, get_db, get_settings
from services.telegram_service import TelegramService

telegram_bp = Blueprint('telegram', __name__)


def get_tg():
    from flask import current_app
    svc = current_app.config.get('TELEGRAM_SERVICE')
    if svc is None:
        svc = TelegramService(get_settings(), get_db())
        current_app.config['TELEGRAM_SERVICE'] = svc
    return svc


@telegram_bp.route('/api/tg/status')
def tg_status():
    """Check Telegram auth status."""
    try:
        svc = get_tg()
        # Check credentials first (before attempting connection)
        s = get_settings()
        api_id = s.get('telegram_api_id', '') or os.environ.get('TELEGRAM_API_ID', '')
        api_hash = s.get('telegram_api_hash', '') or os.environ.get('TELEGRAM_API_HASH', '')
        if not api_id or not api_hash:
            return ok({
                'authorized': False,
                'error': 'Telegram API ID and Hash not configured. Go to Settings → Integrations.',
            })
        auth = svc.is_authorized()
        me = svc.get_me() if auth else {}
        return ok({
            'authorized': auth,
            'user': me.get('user') if isinstance(me, dict) else None,
        })
    except ImportError as e:
        return ok({'authorized': False, 'error': str(e), 'missing_dep': True})
    except Exception as e:
        return ok({'authorized': False, 'error': str(e)})


@telegram_bp.route('/api/tg/send-code', methods=['POST'])
def tg_send_code():
    """Send Telegram login code to phone."""
    data = request.get_json(force=True) or {}
    phone = data.get('phone', '').strip()
    if not phone:
        return err('Phone number required')
    try:
        svc = get_tg()
        result = svc.send_code(phone)
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/sign-in', methods=['POST'])
def tg_sign_in():
    """Complete Telegram login with code + optional 2FA."""
    data = request.get_json(force=True) or {}
    phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()
    password = data.get('password', '')
    if not phone or not code:
        return err('Phone and code required')
    try:
        svc = get_tg()
        result = svc.sign_in(phone, code, password)
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/sign-in-password', methods=['POST'])
def tg_sign_in_password():
    """Complete 2FA password step."""
    data = request.get_json(force=True) or {}
    password = data.get('password', '')
    if not password:
        return err('Password required')
    try:
        svc = get_tg()
        result = svc.sign_in_password(password)
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/logout', methods=['POST'])
def tg_logout():
    """Disconnect Telegram client and clear session."""
    try:
        svc = get_tg()
        result = svc.logout()
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/dialogs')
def tg_dialogs():
    """Fetch all user dialogs."""
    try:
        svc = get_tg()
        dialogs = svc.get_dialogs()
        return ok({'dialogs': dialogs, 'count': len(dialogs)})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/messages')
def tg_messages():
    """Fetch messages from a dialog."""
    dialog_id = request.args.get('dialog_id', type=int)
    limit = request.args.get('limit', 100, type=int)
    offset_id = request.args.get('offset_id', 0, type=int)
    media_only = request.args.get('media_only', '0') == '1'

    if not dialog_id:
        return err('dialog_id required')

    try:
        svc = get_tg()
        messages = svc.get_dialog_messages(dialog_id, limit, offset_id)
        if media_only:
            messages = [m for m in messages if m['has_media']]
        return ok({'messages': messages, 'count': len(messages)})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/download', methods=['POST'])
def tg_download():
    """Download media from Telegram messages."""
    data = request.get_json(force=True) or {}
    dialog_id = int(data.get('dialog_id') or 0)
    msg_ids = data.get('msg_ids', [])
    dl_folder = data.get('dl_folder', '')
    mode = data.get('mode', 'account')
    bot_token = data.get('bot_token', '')

    if not dialog_id or not msg_ids:
        return err('dialog_id and msg_ids required')

    if mode == 'bot' and not bot_token:
        return err('bot_token required for bot mode')

    try:
        svc = get_tg()
        if mode == 'bot':
            result = svc.forward_to_bot(bot_token, dialog_id, msg_ids)
            return ok(result)
        else:
            from jobs.queue import DownloadQueue
            from flask import current_app
            queue = current_app.config.get('QUEUE')
            results = []
            for mid in msg_ids:
                job_id = f'tg_{dialog_id}_{mid}'
                job = queue.enqueue(
                    url=f'telegram://dl/{dialog_id}/{mid}',
                    opts={
                        'mode': 'telegram',
                        'dialog_id': dialog_id,
                        'msg_id': mid,
                        'dl_folder': dl_folder,
                    },
                    job_id=job_id,
                )
                results.append(job)
            return ok({'jobs': results, 'count': len(results)})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/validate-credentials', methods=['POST'])
def tg_validate_credentials():
    """Validate Telegram API ID and Hash by attempting connection."""
    data = request.get_json(force=True) or {}
    api_id = data.get('api_id', '').strip()
    api_hash = data.get('api_hash', '').strip()

    if not api_id or not api_hash:
        return err('API ID and Hash are required')

    try:
        from telethon import TelegramClient
        import asyncio

        async def _test():
            client = TelegramClient('__validate_test', int(api_id), api_hash)
            await client.connect()
            ok = await client.is_user_authorized()  # just tests connectivity
            await client.disconnect()
            return True

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_test())
        loop.close()
        return ok({'valid': True, 'message': 'Credentials are valid — Telegram servers reachable'})
    except ImportError:
        return ok({'valid': False, 'error': 'telethon not installed'})
    except ValueError:
        return ok({'valid': False, 'error': 'API ID must be a number'})
    except Exception as e:
        return ok({'valid': False, 'error': str(e)})


@telegram_bp.route('/api/tg/bot-download', methods=['POST'])
def tg_bot_download():
    """Download all media from bot's saved messages."""
    data = request.get_json(force=True) or {}
    bot_token = data.get('bot_token', '')
    dl_folder = data.get('dl_folder', '')

    if not bot_token:
        return err('bot_token required')

    try:
        svc = get_tg()
        result = svc.download_from_bot(bot_token, dl_folder)
        return ok({'downloaded': result, 'count': len(result)})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/history')
def tg_history():
    """Get Telegram download history."""
    try:
        svc = get_tg()
        limit = request.args.get('limit', 50, type=int)
        history = svc.get_history(limit)
        return ok({'history': history, 'count': len(history)})
    except Exception as e:
        return ok({'history': [], 'error': str(e)})


@telegram_bp.route('/api/tg/save-creds', methods=['POST'])
def tg_save_creds():
    """Save Telegram API credentials."""
    data = request.get_json(force=True) or {}
    api_id = data.get('api_id', '').strip()
    api_hash = data.get('api_hash', '').strip()
    if not api_id or not api_hash:
        return err('API ID and Hash are required')
    try:
        svc = get_tg()
        svc.save_creds(api_id, api_hash)
        return ok({'saved': True})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/creds-status')
def tg_creds_status():
    """Check Telegram credentials status (location and source)."""
    try:
        svc = get_tg()
        status = svc.get_creds_status()
        return ok(status)
    except Exception as e:
        return ok({'ok': False, 'error': str(e)})


@telegram_bp.route('/api/tg/current-file')
def tg_current_file():
    """Get the current file being downloaded."""
    try:
        svc = get_tg()
        return ok({'current_file': svc.current_file})
    except Exception as e:
        return ok({'current_file': '', 'error': str(e)})


# ── Bot Pool ─────────────────────────────────────────────────────

@telegram_bp.route('/api/tg/scan-chat', methods=['POST'])
def tg_scan_chat():
    """Scan a chat for media by type with size estimation."""
    data = request.get_json(force=True) or {}
    dialog_id = int(data.get('dialog_id') or 0)
    media_types = data.get('media_types') or ['photo', 'video', 'document', 'audio']
    limit_per_type = data.get('limit_per_type') or {}

    if not dialog_id:
        return err('dialog_id required')

    try:
        from services.tg_scan_service import TelegramScanService
        svc = get_tg()
        scan_svc = TelegramScanService(svc)
        result = scan_svc.scan_chat_media(dialog_id, media_types, limit_per_type)
        return ok(result)
    except Exception as e:
        return err(str(e))


# ── Bot Pool ─────────────────────────────────────────────────────

@telegram_bp.route('/api/tg/bot-pool', methods=['GET'])
def tg_bot_pool_list():
    """List all bot tokens in pool (masked)."""
    try:
        svc = get_tg()
        return ok({'pool': svc.list_bot_pool(), 'count': len(svc.list_bot_pool())})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-pool/add', methods=['POST'])
def tg_bot_pool_add():
    """Add a bot token to the pool."""
    data = request.get_json(force=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return err('Bot token required')
    try:
        svc = get_tg()
        result = svc.add_bot_token(token)
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-pool/remove', methods=['POST'])
def tg_bot_pool_remove():
    """Remove a bot token from the pool."""
    data = request.get_json(force=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return err('Bot token required')
    try:
        svc = get_tg()
        result = svc.remove_bot_token(token)
        return ok(result)
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-pool/status', methods=['GET'])
def tg_bot_pool_status():
    """Get status of all bots in pool."""
    try:
        svc = get_tg()
        return ok({'bots': svc.get_all_bot_statuses()})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-pool/download-all', methods=['POST'])
def tg_bot_pool_download_all():
    """Download all media from a specific bot and queue as jobs."""
    data = request.get_json(force=True) or {}
    bot_token = data.get('bot_token', '').strip()
    dl_folder = data.get('dl_folder', '')
    if not bot_token:
        return err('bot_token required')
    try:
        svc = get_tg()
        result = svc.download_all_bot_media(bot_token, dl_folder)
        return ok(result)
    except Exception as e:
        return err(str(e))


# ── Resume Downloads ──────────────────────────────────────────────

@telegram_bp.route('/api/tg/resume/init', methods=['POST'])
def tg_resume_init():
    """Initialize a resumable download job."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    dialog_id = int(data.get('dialog_id') or 0)
    msg_id = int(data.get('msg_id') or 0)
    dest_path = data.get('dest_path', '')
    total_size = int(data.get('total_size') or 0)
    if not all([job_id, dialog_id, msg_id, dest_path]):
        return err('job_id, dialog_id, msg_id, dest_path required')
    try:
        from services.tg_resume_service import TelegramResumeService
        svc = get_tg()
        resume = TelegramResumeService(get_settings())
        job = resume.init_job(job_id, dialog_id, msg_id, dest_path, total_size)
        return ok({'job': job})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/progress', methods=['POST'])
def tg_resume_progress():
    """Update download progress."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    downloaded = int(data.get('downloaded_bytes') or 0)
    if not job_id:
        return err('job_id required')
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        resume.update_progress(job_id, downloaded)
        return ok({'ok': True})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/pause', methods=['POST'])
def tg_resume_pause():
    """Pause a download (applies 2MB rollback)."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    if not job_id:
        return err('job_id required')
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        resume.mark_paused(job_id)
        offset = resume.get_resume_offset(job_id)
        return ok({'ok': True, 'resume_offset': offset})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/resume', methods=['POST'])
def tg_resume_resume():
    """Resume a paused download."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    if not job_id:
        return err('job_id required')
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        offset = resume.get_resume_offset(job_id)
        return ok({'ok': True, 'resume_offset': offset})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/complete', methods=['POST'])
def tg_resume_complete():
    """Mark download as completed."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    if not job_id:
        return err('job_id required')
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        resume.mark_completed(job_id)
        return ok({'ok': True})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/fail', methods=['POST'])
def tg_resume_fail():
    """Mark download as failed."""
    data = request.get_json(force=True) or {}
    job_id = data.get('job_id', '')
    error = data.get('error', '')
    if not job_id:
        return err('job_id required')
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        resume.mark_failed(job_id, error)
        return ok({'ok': True})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/resume/status')
def tg_resume_status():
    """Get current resume status and active jobs."""
    try:
        from services.tg_resume_service import TelegramResumeService
        resume = TelegramResumeService(get_settings())
        active = resume.get_active_jobs()
        stats = resume.get_job_stats()
        return ok({'active_jobs': active, 'stats': stats, 'count': len(active)})
    except Exception as e:
        return err(str(e))


# ── Bot Scoring ───────────────────────────────────────────────────

@telegram_bp.route('/api/tg/bot-scores')
def tg_bot_scores():
    """Get weighted AI scores for all bots in pool."""
    try:
        from services.tg_bot_scorer import TelegramBotScorer
        scorer = TelegramBotScorer(get_settings())
        scores = scorer.get_all_scores()
        return ok({'scores': scores})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-scores/select', methods=['POST'])
def tg_bot_select():
    """Select best bot from available tokens using weighted scoring."""
    data = request.get_json(force=True) or {}
    tokens = data.get('tokens', [])
    if not tokens:
        return err('tokens list required')
    try:
        from services.tg_bot_scorer import TelegramBotScorer
        scorer = TelegramBotScorer(get_settings())
        best = scorer.select_best_bot(tokens)
        return ok({'selected': best})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-scores/record-success', methods=['POST'])
def tg_bot_success():
    """Record a successful download for a bot."""
    data = request.get_json(force=True) or {}
    token = data.get('token', '')
    speed = float(data.get('speed_bps') or 0)
    if not token:
        return err('token required')
    try:
        from services.tg_bot_scorer import TelegramBotScorer
        scorer = TelegramBotScorer(get_settings())
        scorer.record_success(token, speed)
        return ok({'ok': True})
    except Exception as e:
        return err(str(e))


@telegram_bp.route('/api/tg/bot-scores/record-failure', methods=['POST'])
def tg_bot_failure():
    """Record a failed download for a bot."""
    data = request.get_json(force=True) or {}
    token = data.get('token', '')
    if not token:
        return err('token required')
    try:
        from services.tg_bot_scorer import TelegramBotScorer
        scorer = TelegramBotScorer(get_settings())
        scorer.record_failure(token)
        return ok({'ok': True})
    except Exception as e:
        return err(str(e))
