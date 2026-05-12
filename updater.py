"""MegaDL Updater — update repo and Python packages."""
import sys, os, subprocess, json
from pathlib import Path

BASE = Path(__file__).parent
PYTHON = sys.executable

REQUIREMENTS_FILES = [
    BASE / 'requirements.txt',
    BASE / 'backend' / 'requirements.txt',
]

ADDITIONAL_PACKAGES = ['yt-dlp']

def print_banner():
    print('=' * 50)
    print('  MegaDL — Updater')
    print('=' * 50)

def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd or str(BASE), capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return r.stdout.strip()
        return f'ERROR: {r.stderr.strip()[:200]}'
    except Exception as e:
        return f'ERROR: {e}'

def update_packages():
    print('\n>> Updating Python packages...')
    for req_file in REQUIREMENTS_FILES:
        if req_file.exists():
            print(f'   Installing from: {req_file.name}')
            out = run([PYTHON, '-m', 'pip', 'install', '--upgrade', '-r', str(req_file)])
            print(f'   {out[:300]}')
    for pkg in ADDITIONAL_PACKAGES:
        print(f'   Upgrading: {pkg}')
        out = run([PYTHON, '-m', 'pip', 'install', '--upgrade', pkg])
        print(f'   {out[:300]}')
    print('   Packages done.')

def update_repo():
    print('\n>> Updating repository...')
    git_dir = BASE / '.git'
    if git_dir.exists():
        out = run(['git', 'pull'])
        print(f'   {out}')
    else:
        print('   Not a git repository. Initializing...')
        run(['git', 'init'])
        print('   Git repo initialized. Set your remote manually:\n     git remote add origin <url>')
    print('   Repo done.')

def menu():
    while True:
        print()
        print('  1) Everything (update all)')
        print('  2) Repo only')
        print('  3) Packages only')
        print('  4) Exit')
        choice = input('\n  Choose: ').strip()
        if choice == '1':
            update_packages()
            update_repo()
            print('\n  All updates complete.')
        elif choice == '2':
            update_repo()
        elif choice == '3':
            update_packages()
        elif choice == '4':
            print('  Bye.')
            sys.exit(0)
        else:
            print('  Invalid choice.')
        input('\n  Press Enter to continue...')

if __name__ == '__main__':
    print_banner()
    menu()
