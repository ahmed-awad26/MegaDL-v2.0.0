"""MegaDL — routes/api_keys.py
Universal API Key Manager for AI/ML services."""
import json
import urllib.request
import urllib.error
import logging
from pathlib import Path
from flask import Blueprint, request
from .ping import ok, err, get_settings

logger = logging.getLogger('megadl.api_keys')

api_keys_bp = Blueprint('api_keys', __name__)

VALIDATORS = {
    'openai': lambda key: _validate_url(
        'https://api.openai.com/v1/models',
        key, '"data"'),
    'anthropic': lambda key: _validate_url(
        'https://api.anthropic.com/v1/messages',
        key, 'anthropic', extra_headers={'anthropic-version': '2023-06-01'}),
    'google_gemini': lambda key: _validate_url(
        f'https://generativelanguage.googleapis.com/v1/models?key={key}',
        '', '"models"'),
    'deepseek': lambda key: _validate_url(
        'https://api.deepseek.com/v1/models',
        key, '"data"'),
    'stability': lambda key: _validate_url(
        'https://api.stability.ai/v1/user/account',
        key, '"email"'),
    'huggingface': lambda key: _validate_url(
        'https://huggingface.co/api/models?limit=1',
        key, '"modelId"'),
    'cohere': lambda key: _validate_url(
        'https://api.cohere.ai/v1/models',
        key, '"models"'),
    'elevenlabs': lambda key: _validate_url(
        'https://api.elevenlabs.io/v1/user',
        key, '"subscription"'),
    'assemblyai': lambda key: _validate_url(
        'https://api.assemblyai.com/v2/realtime/token',
        key, '"error"'),  # will error with proper msg if key is invalid
}


def _validate_url(url: str, api_key: str, expect_str: str,
                  extra_headers: dict = None) -> dict:
    """Validate an API key by hitting its verification endpoint."""
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'MegaDL/2.0',
            'Content-Type': 'application/json',
        }
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            if expect_str in body:
                return {'valid': True, 'message': 'API key is valid'}
            return {'valid': True, 'message': 'Connected (unexpected response)'}
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            return {'valid': False, 'error': 'Invalid or unauthorized API key'}
        try:
            err_body = e.read().decode()
            return {'valid': False, 'error': err_body[:200]}
        except Exception:
            return {'valid': False, 'error': f'HTTP {e.code}'}
    except Exception as e:
        return {'valid': False, 'error': str(e)[:200]}


def _get_api_keys() -> dict:
    s = get_settings()
    raw = s.get('api_keys', '')
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_api_keys(keys: dict):
    from flask import current_app
    s = get_settings()
    s.set('api_keys', json.dumps(keys))
    s.save()


@api_keys_bp.route('/api/api-keys', methods=['GET'])
def list_keys():
    keys = _get_api_keys()
    masked = {}
    for provider, key in keys.items():
        masked[provider] = key[:6] + '...' + key[-4:] if len(key) > 12 else '***'
    return ok({'providers': list(keys.keys()), 'keys': masked})


@api_keys_bp.route('/api/api-keys/set', methods=['POST'])
def set_key():
    data = request.get_json(force=True) or {}
    provider = data.get('provider', '').strip()
    api_key = data.get('key', '').strip()
    if not provider or not api_key:
        return err('Provider and API key are required')
    keys = _get_api_keys()
    keys[provider] = api_key
    _save_api_keys(keys)
    return ok({'saved': True, 'provider': provider})


@api_keys_bp.route('/api/api-keys/delete', methods=['POST'])
def delete_key():
    data = request.get_json(force=True) or {}
    provider = data.get('provider', '').strip()
    keys = _get_api_keys()
    keys.pop(provider, None)
    _save_api_keys(keys)
    return ok({'deleted': True, 'provider': provider})


@api_keys_bp.route('/api/api-keys/validate', methods=['POST'])
def validate_key():
    data = request.get_json(force=True) or {}
    provider = data.get('provider', '').strip()
    api_key = data.get('key', '').strip()
    if not provider:
        return err('Provider is required')
    if not api_key:
        keys = _get_api_keys()
        api_key = keys.get(provider, '')
    if not api_key:
        return err('No API key provided for this provider')
    validator = VALIDATORS.get(provider)
    if not validator:
        return ok({'valid': False, 'error': f'No validator for {provider}'})
    result = validator(api_key)
    # Save key if valid
    if result.get('valid'):
        keys = _get_api_keys()
        keys[provider] = api_key
        _save_api_keys(keys)
    return ok(result)
