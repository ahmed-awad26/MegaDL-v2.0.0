#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# MegaDL — install.sh
# Termux + Linux auto-installer with fallback mirrors
# Checks all dependencies, installs missing ones, retries
# with alternative sources on failure.
# ============================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

log()  { echo -e "${CYAN}[MegaDL]${RESET} $1"; }
ok()   { echo -e "${GREEN}[OK]${RESET} $1"; }
warn() { echo -e "${YELLOW}[..]${RESET} $1"; }
fail() { echo -e "${RED}[XX]${RESET} $1"; }

echo -e "${CYAN}"
cat << 'EOF'
  __  __                  ____  _
 |  \/  | ___  __ _  __ _|  _ \| |
 | |\/| |/ _ \/ _` |/ _` | | | | |
 | |  | |  __/ (_| | (_| | |_| | |___
 |_|  |_|\___|\__, |\__,_|____/|_____|
               |___/  v2.0.0 Installer
EOF
echo -e "${RESET}"

# ── Detect environment ────────────────────────────────────────
IS_TERMUX=false
IS_ANDROID=false
IS_LINUX=false

if [ -d "/data/data/com.termux" ]; then
    IS_TERMUX=true
    IS_ANDROID=true
    log "Detected: Termux on Android"
elif [ -f "/proc/sys/kernel/ostype" ]; then
    IS_LINUX=true
    log "Detected: Linux"
else
    log "Detected: Unknown (trying Linux mode)"
    IS_LINUX=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Storage permission (Android) ──────────────────────────────
if $IS_ANDROID; then
    log "Requesting storage access..."
    echo ""
    echo -e "  ${YELLOW}MegaDL needs storage access to save downloads.${RESET}"
    echo -e "  ${YELLOW}A permission dialog will appear — tap ALLOW.${RESET}"
    echo ""
    sleep 1

    if command -v termux-setup-storage &>/dev/null; then
        termux-setup-storage
        sleep 2
    else
        fail "termux-setup-storage not found. Install: pkg install termux-api"
        exit 1
    fi

    # Verify storage access
    if [ -d "/sdcard" ] && touch "/sdcard/.megadl_perms_test" 2>/dev/null; then
        rm -f "/sdcard/.megadl_perms_test"
        ok "Storage access granted"
    else
        echo ""
        fail "Storage permission DENIED."
        echo ""
        echo -e "  ${YELLOW}Please run manually: termux-setup-storage${RESET}"
        echo -e "  ${YELLOW}Then re-run this installer.${RESET}"
        echo ""
        exit 1
    fi
else
    log "Storage permission not required on this platform"
fi

# ── Update package manager ────────────────────────────────────
log "Updating package manager..."
if $IS_TERMUX; then
    pkg update -y 2>/dev/null && pkg upgrade -y 2>/dev/null || \
    warn "Package update skipped (non-critical)"
else
    sudo apt-get update -qq 2>/dev/null || true
fi

# ── Install Python ────────────────────────────────────────────
PYTHON_BIN=""
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
fi

if [ -z "$PYTHON_BIN" ]; then
    log "Installing Python..."
    if $IS_TERMUX; then
        pkg install -y python 2>/dev/null || { fail "Python install failed"; exit 1; }
    else
        sudo apt-get install -y python3 python3-pip 2>/dev/null || \
        sudo yum install -y python3 python3-pip 2>/dev/null || \
        { fail "Python install failed. Install manually: python3"; exit 1; }
    fi
    PYTHON_BIN="python3"
    ok "Python installed"
else
    ok "Python: $($PYTHON_BIN --version 2>&1)"
fi

# ── Install pip if missing ────────────────────────────────────
if ! $PYTHON_BIN -m pip --version &>/dev/null; then
    log "Installing pip..."
    $PYTHON_BIN -m ensurepip --upgrade 2>/dev/null || \
    curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON_BIN 2>/dev/null || \
    { fail "pip install failed"; exit 1; }
    ok "pip installed"
else
    ok "pip: $($PYTHON_BIN -m pip --version | head -1)"
fi

# ── Install FFmpeg ────────────────────────────────────────────
log "Installing FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    if $IS_TERMUX; then
        pkg install -y ffmpeg 2>/dev/null || warn "FFmpeg install failed. Install: pkg install ffmpeg"
    else
        sudo apt-get install -y ffmpeg 2>/dev/null || \
        sudo yum install -y ffmpeg 2>/dev/null || \
        warn "FFmpeg install failed. Install manually."
    fi
else
    ok "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
fi

# ── Run Python dependency checker ─────────────────────────────
log "Checking Python dependencies..."
echo ""
cd "$SCRIPT_DIR" || exit 1

if [ -f "check_deps.py" ]; then
    $PYTHON_BIN check_deps.py --verbose || true
else
    # ── Fallback: direct install ──────────────────────────────
    log "check_deps.py not found, installing directly..."

    DEPS="flask flask-cors yt-dlp telethon cryptg aiofiles requests requests[socks] openpyxl pillow gdown mega.py cloudscraper beautifulsoup4 lxml"

    # Mirror list for pip fallback
    MIRRORS=(
        "https://pypi.org/simple/"
        "https://pypi.tuna.tsinghua.edu.cn/simple/"
        "https://mirrors.aliyun.com/pypi/simple/"
        "https://pypi.douban.com/simple/"
    )

    install_with_fallback() {
        local pkg="$1"
        for mirror in "${MIRRORS[@]}"; do
            for flag in "" "--break-system-packages" "--user" "--no-cache-dir"; do
                echo -e "  ${CYAN}Trying: pip install $pkg (mirror: $(basename $mirror), flags: $flag)${RESET}"
                if $PYTHON_BIN -m pip install --upgrade "$pkg" -i "$mirror" $flag 2>/dev/null; then
                    return 0
                fi
            done
        done
        # Final attempt with no special flags
        $PYTHON_BIN -m pip install "$pkg" 2>/dev/null
        return $?
    }

    for dep in $DEPS; do
        echo -e "  ${CYAN}Installing $dep...${RESET}"
        if install_with_fallback "$dep"; then
            ok "$dep installed"
        else
            fail "$dep FAILED. Try: pip install $dep"
        fi
    done
fi

# ── Create directories ────────────────────────────────────────
log "Creating project directories..."
mkdir -p "$SCRIPT_DIR/backend/logs" \
         "$SCRIPT_DIR/backend/database" \
         "$SCRIPT_DIR/backend/config" \
         "$SCRIPT_DIR/backend/temp" \
         "$SCRIPT_DIR/backend-php/logs" \
         "$SCRIPT_DIR/backend-php/downloads"
ok "Directories created"

# ── Test yt-dlp ───────────────────────────────────────────────
log "Testing yt-dlp..."
if yt-dlp --version &>/dev/null; then
    ok "yt-dlp working: $(yt-dlp --version)"
else
    fail "yt-dlp test failed"
fi

# ── Summary ────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${RESET}"
echo -e "${GREEN}  MegaDL Installation Complete!${RESET}"
echo -e "${GREEN}════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${CYAN}Start server:${RESET}  bash run.sh"
echo -e "  ${CYAN}Update:${RESET}        bash update.sh"
echo -e "  ${CYAN}Check deps:${RESET}     python3 check_deps.py"
echo ""
echo -e "  ${CYAN}Open browser:${RESET}  http://localhost:5000"
echo ""
