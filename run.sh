#!/bin/bash
# ============================================================
# MegaDL — run.sh
# Start the Flask backend server with auto-dependency check
# ============================================================

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

PORT="${MEGADL_PORT:-5000}"
HOST="${MEGADL_HOST:-0.0.0.0}"

# Find Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}[✗] Python not found. Run: bash install.sh${RESET}"
    exit 1
fi

# ── Auto-check dependencies ──────────────────────────────────
if [ -f "$SCRIPT_DIR/check_deps.py" ]; then
    echo -e "${CYAN}[MegaDL] Checking dependencies...${RESET}"
    $PYTHON "$SCRIPT_DIR/check_deps.py" --check-only 2>/dev/null
    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${YELLOW}[!] Some dependencies are missing.${RESET}"
        echo -e "${YELLOW}[!] Run: bash install.sh${RESET}"
        echo -e "${YELLOW}[!] Or: $PYTHON check_deps.py${RESET}"
        echo ""
        echo -e "${YELLOW}[!] Starting anyway in 3 seconds...${RESET}"
        sleep 3
    fi
else
    # Quick inline check for critical deps
    echo -e "${CYAN}[MegaDL] Quick dependency check...${RESET}"
    MISSING=""
    $PYTHON -c "import flask" 2>/dev/null || MISSING="$MISSING flask"
    $PYTHON -c "import yt_dlp" 2>/dev/null || MISSING="$MISSING yt-dlp"
    $PYTHON -c "import telethon" 2>/dev/null || MISSING="$MISSING telethon"
    if [ -n "$MISSING" ]; then
        echo -e "${YELLOW}[!] Missing: $MISSING${RESET}"
        echo -e "${YELLOW}[!] Run: bash install.sh${RESET}"
    fi
fi

echo -e "${CYAN}[MegaDL] Starting server on http://localhost:$PORT${RESET}"
cd "$BACKEND_DIR" || exit 1
MEGADL_PORT="$PORT" MEGADL_HOST="$HOST" $PYTHON app.py
