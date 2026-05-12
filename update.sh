#!/usr/bin/env bash
# ============================================================
# MegaDL — update.sh
# Pull latest from GitHub repo + update all dependencies
# ============================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

log()  { echo -e "${CYAN}[MegaDL]${RESET} $1"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $1"; }
warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
fail() { echo -e "${RED}[✗]${RESET} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/.update.conf"

# ── Load config ──────────────────────────────────────────────
REPO_URL=""
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# ── Determine repo URL ───────────────────────────────────────
get_repo_url() {
    # 1) If we're inside a git repo, get the origin URL
    if [ -d "$SCRIPT_DIR/.git" ]; then
        local url
        url=$(git -C "$SCRIPT_DIR" config --get remote.origin.url 2>/dev/null || echo "")
        if [ -n "$url" ]; then
            echo "$url"
            return 0
        fi
    fi

    # 2) Fall back to config file
    if [ -n "$REPO_URL" ]; then
        echo "$REPO_URL"
        return 0
    fi

    echo ""
    return 1
}

# ── Pull latest code from GitHub ─────────────────────────────
pull_latest() {
    local url="$1"

    if [ -d "$SCRIPT_DIR/.git" ]; then
        log "Git repository detected — pulling latest changes..."
        git -C "$SCRIPT_DIR" stash --include-untracked 2>/dev/null || true
        if git -C "$SCRIPT_DIR" pull origin "$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)" 2>/dev/null; then
            ok "Repository updated to latest commit"
            log "Recent changes:"
            git -C "$SCRIPT_DIR" log --oneline -5 2>/dev/null || true
        else
            warn "Git pull failed. Check your network or git status."
        fi
        git -C "$SCRIPT_DIR" stash pop 2>/dev/null || true
    else
        log "No .git directory found."
        log "Cloning repository from $url into a temporary directory..."
        local tmp_dir
        tmp_dir=$(mktemp -d)
        git clone --depth=1 "$url" "$tmp_dir" 2>/dev/null || {
            fail "Could not clone repository. Check URL: $url"
            rm -rf "$tmp_dir"
            log "You can set your repo URL in $CONFIG_FILE:"
            echo "  REPO_URL=\"https://github.com/YOUR_USER/MegaDL.git\""
            return 1
        }

        # Copy files (preserve existing configs and downloads)
        log "Merging updated files (preserving your config + downloads)..."
        rsync -a --ignore-existing \
            "$tmp_dir/backend/config/" "$SCRIPT_DIR/backend/config/" 2>/dev/null || true

        rsync -a \
            --exclude='.git' \
            --exclude='.update.conf' \
            --exclude='backend/config/settings.json' \
            --exclude='backend/database/' \
            --exclude='backend/downloads/' \
            --exclude='backend/temp/' \
            --exclude='backend/logs/' \
            "$tmp_dir/" "$SCRIPT_DIR/" 2>/dev/null || {
            # Fallback: simple copy without rsync
            cp -r "$tmp_dir/frontend" "$SCRIPT_DIR/" 2>/dev/null || true
            cp -r "$tmp_dir/backend" "$SCRIPT_DIR/" 2>/dev/null || true
            cp "$tmp_dir/requirements.txt" "$SCRIPT_DIR/" 2>/dev/null || true
            cp "$tmp_dir/README.md" "$SCRIPT_DIR/" 2>/dev/null || true
            cp "$tmp_dir/run.sh" "$SCRIPT_DIR/" 2>/dev/null || true
            cp "$tmp_dir/install.sh" "$SCRIPT_DIR/" 2>/dev/null || true
        }

        rm -rf "$tmp_dir"
        ok "Repository updated successfully"
    fi
}

# ── Update Python deps ───────────────────────────────────────
update_deps() {
    log "Updating Python dependencies..."

    PIP_CMD="pip3"
    if ! command -v pip3 &>/dev/null; then
        PIP_CMD="pip"
    fi

    # Upgrade pip itself
    $PIP_CMD install --upgrade pip 2>/dev/null || true

    # Install from requirements.txt if it exists
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        log "Installing packages from requirements.txt..."
        $PIP_CMD install --upgrade -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null \
            || $PIP_CMD install --upgrade -r "$SCRIPT_DIR/requirements.txt" --break-system-packages 2>/dev/null \
            || warn "Some packages may have failed — check manually"
    else
        # Install core packages individually
        $PIP_CMD install --upgrade flask flask-cors yt-dlp telethon cryptg aiofiles psutil requests openpyxl pillow 2>/dev/null \
            || $PIP_CMD install --upgrade flask flask-cors yt-dlp telethon cryptg aiofiles psutil requests openpyxl pillow --break-system-packages 2>/dev/null \
            || warn "Some packages may have failed — check manually"
    fi

    # Update yt-dlp separately (most critical)
    log "Updating yt-dlp..."
    $PIP_CMD install --upgrade yt-dlp 2>/dev/null \
        || $PIP_CMD install --upgrade yt-dlp --break-system-packages 2>/dev/null \
        || warn "yt-dlp update failed"

    ok "Dependencies updated"
}

# ── Main ─────────────────────────────────────────────────────
echo ""
log "Starting MegaDL update..."
echo ""

# Step 1: Get repo URL and pull latest code
REPO=$(get_repo_url || echo "")
if [ -n "$REPO" ]; then
    pull_latest "$REPO"
else
    warn "No repository configured."
    warn "To enable code updates from GitHub, create $CONFIG_FILE with:"
    echo ""
    echo "  REPO_URL=\"https://github.com/YOUR_USER/MegaDL.git\""
    echo ""
    log "Skipping code update — only updating dependencies."
fi

# Step 2: Update dependencies (always)
echo ""
update_deps

# Step 3: Show versions
echo ""
log "Current versions:"
if command -v yt-dlp &>/dev/null; then
    ok "yt-dlp: $(yt-dlp --version 2>/dev/null || echo 'unknown')"
fi
if command -v ffmpeg &>/dev/null; then
    ok "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
fi
if python3 --version &>/dev/null; then
    ok "Python: $(python3 --version 2>&1)"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${RESET}"
echo -e "${GREEN}  MegaDL Update Complete!${RESET}"
echo -e "${GREEN}════════════════════════════════════════${RESET}"
echo ""
log "Restart the server to apply changes:  bash run.sh"
echo ""
