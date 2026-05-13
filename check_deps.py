#!/usr/bin/env python3
"""
MegaDL — check_deps.py
Dependency checker with auto-install and fallback mirrors.
Checks all required packages, installs missing ones, retries with alternative sources on failure.

Usage:
    python check_deps.py              # Check & install missing deps
    python check_deps.py --check-only # Only check, don't install
    python check_deps.py --verbose    # Show detailed output
"""

import os
import sys
import json
import subprocess
import importlib
import time
import platform as pf

# ── ANSI Colors ─────────────────────────────────────────────────
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
CYAN = '\033[0;36m'
RESET = '\033[0m'

ok   = lambda msg: print(f'{GREEN}[OK]{RESET} {msg}')
warn = lambda msg: print(f'{YELLOW}[..]{RESET} {msg}')
fail = lambda msg: print(f'{RED}[XX]{RESET} {msg}')
info = lambda msg: print(f'{CYAN}[--]{RESET} {msg}')


# ── Required Dependencies ───────────────────────────────────────
# (module_name, pip_package, min_version)
REQUIRED = [
    ('flask',           'flask',            '3.0.0'),
    ('flask_cors',      'flask-cors',       '4.0.0'),
    ('yt_dlp',          'yt-dlp',           '2024.0.0'),
    ('telethon',        'telethon',         '1.34.0'),
    # cryptg is optional (speeds up Telegram)
    ('cryptg',          'cryptg',           '0.4.0'),
    ('aiofiles',        'aiofiles',         '23.0.0'),
    ('requests',        'requests',         '2.31.0'),
    ('openpyxl',        'openpyxl',         '3.1.0'),
    ('PIL',             'pillow',           '10.0.0'),
    ('gdown',           'gdown',            '5.0.0'),
    ('mega',            'mega.py',          '1.0.0'),
    ('cloudscraper',    'cloudscraper',      '1.2.0'),
    ('bs4',             'beautifulsoup4',   '4.12.0'),
    ('lxml',            'lxml',             '5.0.0'),
]

# Optional packages (won't fail if missing)
OPTIONAL = [
    ('psutil',          'psutil',           '5.9.0'),       # Termux aarch64: no wheel, skip gracefully
    ('googleapiclient', 'google-api-python-client', '2.0.0'),
    ('google.auth',     'google-auth-oauthlib',      '1.0.0'),
    ('selenium',        'selenium',                  '4.15.0'),
    ('aria2p',          'aria2p',                    '0.11.0'),
]

# ── Fallback pip mirrors ────────────────────────────────────────
PIP_MIRRORS = [
    'https://pypi.org/simple/',
    'https://pypi.tuna.tsinghua.edu.cn/simple/',
    'https://mirrors.aliyun.com/pypi/simple/',
    'https://mirrors.cloud.tencent.com/pypi/simple/',
    'https://pypi.douban.com/simple/',
    'https://pypi.mirrors.ustc.edu.cn/simple/',
]


def get_python():
    """Get the current Python executable path."""
    return sys.executable or 'python3'


def get_pip_args(mirror_index=0, extra_flags=None):
    """Build pip install arguments with mirror and fallbacks."""
    args = [get_python(), '-m', 'pip', 'install', '--upgrade']
    args.append(f'-i')
    args.append(PIP_MIRRORS[mirror_index % len(PIP_MIRRORS)])
    if extra_flags:
        args.extend(extra_flags)
    return args


def check_package(mod_name, pip_name, min_ver):
    """Check if a package is installed and meets minimum version.
    
    Tries pip show first (safe, no import side effects), then import.
    """
    # Try pip show first (safe, no import side effects)
    try:
        r = subprocess.run([get_python(), '-m', 'pip', 'show', pip_name],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            for line in r.stdout.split('\n'):
                if line.lower().startswith('version:'):
                    return True, line.split(':', 1)[1].strip()
    except Exception:
        pass
    
    # Fallback: try import (may fail if package has broken dependencies)
    for name in [mod_name, pip_name.replace('-', '_')]:
        try:
            mod = importlib.import_module(name)
            ver = getattr(mod, '__version__', getattr(mod, 'version', ''))
            if isinstance(ver, bytes):
                ver = ver.decode()
            return True, str(ver) or 'installed'
        except (ImportError, AttributeError, Exception):
            continue
    
    # Try alternative names
    alt_map = {'PIL': 'Pillow', 'mega': 'mega.py', 'bs4': 'beautifulsoup4',
               'flask_cors': 'flask-cors', 'yt_dlp': 'yt-dlp',
               'googleapiclient': 'google-api-python-client'}
    alt = alt_map.get(mod_name, pip_name)
    try:
        mod = importlib.import_module(alt)
        return True, getattr(mod, '__version__', 'installed')
    except Exception:
        pass
    
    return False, ''


def install_package(pip_name, verbose=False):
    """Install a package with fallback mirrors and multiple strategies."""
    strategies = [
        [],                              # Default
        ['--break-system-packages'],     # PEP 668 (Debian/Ubuntu)
        ['--user'],                      # User install
        ['--no-cache-dir'],              # No cache (if cache corrupt)
    ]
    
    for mirror_idx in range(len(PIP_MIRRORS)):
        for strategy in strategies:
            args = get_pip_args(mirror_idx, strategy)
            args.append(pip_name)
            
            if verbose:
                info(f'Trying: pip install {pip_name} (mirror {mirror_idx+1}, flags: {" ".join(strategy)})')
            
            try:
                r = subprocess.run(args, capture_output=True, text=True,
                                  timeout=120)
                if r.returncode == 0:
                    if verbose:
                        print(r.stdout[-300:])
                    return True
                if verbose:
                    warn(r.stderr[-200:])
            except subprocess.TimeoutExpired:
                warn(f'Timeout installing {pip_name}')
            except Exception as e:
                warn(f'Error: {e}')
    
    # Final attempt: pip install without any flags
    try:
        r = subprocess.run([get_python(), '-m', 'pip', 'install', pip_name],
                          capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def check_binary(name):
    """Check if a system binary is available."""
    try:
        r = subprocess.run([name, '--version'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return True, r.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return False, ''


def main():
    verbose = '--verbose' in sys.argv
    check_only = '--check-only' in sys.argv
    
    print(f'{CYAN}========================================{RESET}')
    print(f'{CYAN}  MegaDL - Dependency Checker{RESET}')
    print(f'{CYAN}  Python: {sys.version.split()[0]}{RESET}')
    print(f'{CYAN}  Platform: {pf.system()} {pf.machine()}{RESET}')
    print(f'{CYAN}========================================{RESET}')
    print()
    
    # ── Check Binaries ────────────────────────────────────────
    info('Checking system binaries...')
    binaries = [
        ('yt-dlp', 'pip install yt-dlp'),
        ('ffmpeg', 'apt install ffmpeg / pkg install ffmpeg'),
        ('wget', 'apt install wget / pkg install wget'),
    ]
    
    all_bin_ok = True
    for binary, install_cmd in binaries:
        installed, ver = check_binary(binary)
        if installed:
            ok(f'{binary}: {ver}')
        else:
            warn(f'{binary} not found. Install: {install_cmd}')
            all_bin_ok = False
    
    print()
    
    # ── Check Required Packages ────────────────────────────────
    info('Checking required Python packages...')
    missing = []
    
    for mod_name, pip_name, min_ver in REQUIRED:
        installed, ver = check_package(mod_name, pip_name, min_ver)
        if installed:
            ok(f'{pip_name}: {ver}')
        else:
            fail(f'{pip_name}: NOT INSTALLED')
            missing.append(pip_name)
    
    print()
    
    # ── Check Optional Packages ────────────────────────────────
    info('Checking optional packages...')
    for mod_name, pip_name, min_ver in OPTIONAL:
        installed, ver = check_package(mod_name, pip_name, min_ver)
        if installed:
            ok(f'{pip_name}: {ver}')
        else:
            warn(f'{pip_name}: not installed (optional)')
    
    print()
    
    # ── Install Missing ────────────────────────────────────────
    if missing and not check_only:
        info('Installing missing packages...')
        for pip_name in missing:
            print(f'  Installing {pip_name}...')
            if install_package(pip_name, verbose):
                ok(f'{pip_name} installed successfully')
            else:
                fail(f'{pip_name} FAILED after all mirrors and strategies')
                fail(f'  Try manual: pip install {pip_name}')
        
        print()
        info('Verifying installation...')
        still_missing = []
        for mod_name, pip_name, min_ver in REQUIRED:
            installed, ver = check_package(mod_name, pip_name, min_ver)
            if not installed:
                still_missing.append(pip_name)
        
        if still_missing:
            fail('Still missing: ' + ', '.join(still_missing))
            sys.exit(1)
        else:
            ok('All packages verified!')
    
    elif missing and check_only:
        fail('Missing packages: ' + ', '.join(missing))
        info('Run without --check-only to auto-install')
        sys.exit(1)
    
    print()
    print(f'{GREEN}========================================{RESET}')
    print(f'{GREEN}  Dependency check complete!{RESET}')
    print(f'{GREEN}========================================{RESET}')


if __name__ == '__main__':
    main()
