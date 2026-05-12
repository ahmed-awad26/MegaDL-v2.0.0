# MegaDL v2.0.0

> **Professional Download Manager** — YouTube, TikTok, Instagram, Telegram, and 1000+ sites  
> Android-like PWA · Flask + PHP Backends · yt-dlp powered · Telegram integration

<p align="center">
  <img src="docs/screenshot-home.png" width="280" alt="MegaDL Home" />
  <img src="docs/screenshot-active.png" width="280" alt="Active Downloads" />
</p>

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎯 **1000+ sites** | YouTube, TikTok, Instagram, Twitter/X, Reddit, SoundCloud, Twitch, Vimeo… |
| 📱 **Android PWA** | Installs like a native app, works offline |
| ⬇️ **Batch downloads** | Paste multiple URLs, auto-parallel queue |
| 🎵 **Audio extraction** | MP3, M4A, Opus with thumbnail + metadata |
| 🔍 **Smart info fetch** | Thumbnail, duration, resolution, formats before download |
| ⚙️ **Dual backend** | Auto-switches between Python/Flask and PHP |
| 📊 **Live progress** | Real-time speed, ETA, fragment tracking |
| 🔄 **Auto-retry** | Automatic retry on failure with configurable attempts |
| 🎬 **SponsorBlock** | Skip sponsored segments in YouTube videos |
| 📋 **History & Archive** | Full download history, yt-dlp archive file support |
| 🔒 **Secure** | URL sanitization, path traversal protection, blocked ad domains |
| 🌙 **AMOLED Dark** | Material You design with dynamic accent colors |

### Telegram Integration

| Feature | Details |
|---|---|
| 📱 **Telegram Auth** | Phone login with 2FA support, persistent session & credential storage |
| 💬 **Dialog Browser** | Browse channels, groups, and private chats |
| 📂 **Media Scan** | Scan chat by media type (photos, videos, documents, audio) with size estimation |
| 🖼️ **Media Filtering** | Per-type limits and checkboxes for selective downloads |
| 📝 **Smart Filenames** | 7-layer fallback: `DocumentAttributeFilename` → audio/video metadata → caption → date → ID |
| 🤖 **Bot Pool** | Weighted AI scoring (40% load, 35% speed, 20% reliability, 5% recency) for bot selection |
| ⏸️ **Resumable Downloads** | 2MB rollback buffer prevents incomplete chunk corruption |
| 🔄 **Deduplication** | Tracks message IDs to avoid re-downloading across chats |
| 📜 **Download History** | Per-chat history with file type, size, and status tracking |

### URL Cleaner & File Hosting

| Feature | Details |
|---|---|
| 🧹 **URL Cleaner** | Strips tracking parameters, resolves short URLs |
| ☁️ **Mega.nz** | Direct download support |
| 🗂️ **Google Drive** | Direct download support |
| 🔗 **MediaFire** | Direct download support |
| 📦 **Direct URLs** | Fallback chain for direct file downloads |
| ▶️ **Unlisted Playlists** | YouTube unlisted playlist support via dedicated mode |

---

## 🚀 Quick Start

### Option 1 — Python/Flask (Recommended)

```bash
# 1. Install dependencies
pip install flask flask-cors yt-dlp telethon cryptg

# 2. Start server
cd MegaDL
bash run.sh
# OR: python backend/app.py

# 3. Open browser
# http://localhost:5000
```

### Option 2 — PHP (XAMPP / AWebServer / KSWEB)

```
1. Copy the MegaDL/ folder to your web server root
   - XAMPP:     C:/xampp/htdocs/MegaDL/
   - AWebServer: /sdcard/AWebServer/www/MegaDL/
   - KSWEB:     /sdcard/ksweb/www/MegaDL/

2. Enable mod_rewrite in Apache

3. Open: http://localhost/MegaDL/backend-php/api/
   The frontend at http://localhost/MegaDL/frontend/ detects the PHP backend automatically.
```

### Option 3 — Termux (Android)

```bash
# Install Termux from F-Droid (not Play Store)

# Clone or copy MegaDL to Termux storage
cd ~
# paste your MegaDL folder here

# Run installer
bash install.sh

# Start server
bash run.sh
```

---

## 📦 Installation Details

### Prerequisites

| Dependency | Required | Install |
|---|---|---|
| Python 3.8+ | For Flask backend | `pkg install python` (Termux) |
| Flask | For Flask backend | `pip install flask flask-cors` |
| yt-dlp | Core download engine | `pip install yt-dlp` |
| FFmpeg | For merging video/audio | `pkg install ffmpeg` |
| Telethon | For Telegram integration | `pip install telethon cryptg` |
| PHP 8.0+ | For PHP backend | Included with XAMPP / KSWEB |

### Auto-Detection

MegaDL automatically detects your environment:
- **Download folder**: Detects `/sdcard/Download` (Android), `~/Downloads` (Linux/Mac), `C:/Users/.../Downloads` (Windows)
- **Backend**: Tries Python/Flask first, falls back to PHP automatically
- **Binaries**: Searches PATH + common install locations for yt-dlp and FFmpeg

---

## 📁 Project Structure

```
MegaDL/
├── frontend/              # Web UI (vanilla HTML/CSS/JS PWA)
│   ├── index.html
│   ├── manifest.json
│   ├── service-worker.js
│   └── assets/
│       ├── css/           # Main, animations, components, pages
│       └── js/            # Config, utils, api, router, jobs, downloader, telegram, app
│
├── backend/               # Python/Flask backend
│   ├── app.py             # Flask entry point
│   ├── config/
│   │   └── settings.py    # Persistent JSON-based settings
│   ├── database/
│   │   └── db.py          # SQLite ORM
│   ├── services/
│   │   ├── ytdlp_service.py       # yt-dlp wrapper
│   │   ├── telegram_service.py    # Telethon client, auth, download, bot pool
│   │   ├── tg_scan_service.py     # Media scanning by type with size estimation
│   │   ├── tg_filename_service.py # 7-layer smart filename extraction
│   │   ├── tg_resume_service.py   # Resumable downloads with 2MB rollback
│   │   ├── tg_bot_scorer.py       # Weighted AI bot pool scoring
│   │   ├── url_cleaner.py         # URL sanitization and short URL resolution
│   │   └── filehost_service.py    # Mega, GDrive, MediaFire, direct URL downloads
│   ├── jobs/
│   │   └── queue.py       # Download queue manager
│   └── routes/
│       ├── telegram.py    # All Telegram API endpoints (31 routes)
│       ├── filehost.py    # URL cleaner & file hosting endpoints
│       ├── ytdlp.py       # yt-dlp routes (playlists, channel uploads)
│       └── ...            # jobs, files, settings, logs, etc.
│
├── backend-php/           # PHP backend
│   ├── api/index.php      # Router
│   ├── api/handlers/      # info, download, jobs, files, diagnostics
│   ├── config/Config.php
│   ├── database/Database.php
│   ├── utils/helpers.php
│   └── jobs/watcher.php   # Background progress monitor
│
├── install.sh             # Termux/Linux installer
├── run.sh                 # Start Flask server
└── update.sh              # Update yt-dlp
```

---

## 🌐 API Reference

All endpoints return JSON: `{ "ok": true, ...data }` or `{ "ok": false, "error": "..." }`

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/ping` | Health check, backend type |
| POST | `/api/info` | Extract video metadata |
| POST | `/api/download` | Start a download |
| POST | `/api/batch` | Start multiple downloads |

### Job Management

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/jobs` | List all jobs (`?filter=&sort=&q=`) |
| GET | `/api/jobs/:id` | Get job details |
| DELETE | `/api/jobs/:id` | Delete job |
| POST | `/api/jobs/:id/pause` | Pause job |
| POST | `/api/jobs/:id/resume` | Resume job |
| POST | `/api/jobs/:id/cancel` | Cancel job |
| POST | `/api/jobs/:id/retry` | Retry failed job |
| GET | `/api/jobs/:id/logs` | Get job logs |
| POST | `/api/jobs/pause-all` | Pause all active |
| POST | `/api/jobs/resume-all` | Resume all paused |
| POST | `/api/jobs/cancel-all` | Cancel all active |

### Library

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/history` | Download history |
| DELETE | `/api/history` | Clear history |
| GET | `/api/archive` | Archive entries |
| GET/POST/DELETE | `/api/favorites` | Manage favorites |
| GET | `/api/files` | Browse download folder |
| POST | `/api/files/delete` | Delete a file |
| POST | `/api/files/rename` | Rename a file |
| GET | `/api/files/download/:path` | Download a file |

### System

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/settings` | Get settings |
| POST | `/api/settings` | Save settings |
| GET | `/api/logs` | System logs (`?level=`) |
| DELETE | `/api/logs` | Clear logs |
| GET | `/api/diagnostics` | Run system check |
| GET | `/api/stats` | Usage statistics |

### Telegram — Auth & Credentials

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tg/status` | Auth status & current user |
| POST | `/api/tg/send-code` | Request login code |
| POST | `/api/tg/sign-in` | Verify code & sign in |
| POST | `/api/tg/sign-in-password` | Submit 2FA password |
| POST | `/api/tg/logout` | Disconnect & clear session |
| POST | `/api/tg/save-creds` | Save API ID/Hash to settings & .env |
| GET | `/api/tg/creds-status` | Check credential source & validity |
| POST | `/api/tg/validate-credentials` | Test API credentials against Telegram |

### Telegram — Dialogs & Messages

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tg/dialogs` | List all chats/channels/groups |
| GET | `/api/tg/messages` | Fetch messages (`?dialog_id=&limit=&media_only=`) |
| POST | `/api/tg/scan-chat` | Scan chat media by type with size estimation |
| POST | `/api/tg/download` | Start download (account or bot mode) |
| POST | `/api/tg/bot-download` | Download all media from bot's saved messages |
| GET | `/api/tg/history` | Telegram download history |
| GET | `/api/tg/current-file` | Currently downloading file |

### Telegram — Bot Pool

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tg/bot-pool` | List bot tokens (masked) |
| POST | `/api/tg/bot-pool/add` | Add bot token to pool |
| POST | `/api/tg/bot-pool/remove` | Remove bot token |
| GET | `/api/tg/bot-pool/status` | Check all bot connectivity |
| POST | `/api/tg/bot-pool/download-all` | Download from specific bot |

### Telegram — Bot Scoring (Weighted AI)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tg/bot-scores` | Weighted AI scores for all bots |
| POST | `/api/tg/bot-scores/select` | Select best bot from available tokens |
| POST | `/api/tg/bot-scores/record-success` | Record successful download |
| POST | `/api/tg/bot-scores/record-failure` | Record failed download |

### Telegram — Resumable Downloads

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/tg/resume/init` | Initialize resumable job |
| POST | `/api/tg/resume/progress` | Update download progress |
| POST | `/api/tg/resume/pause` | Pause with 2MB rollback |
| POST | `/api/tg/resume/resume` | Get resume offset |
| POST | `/api/tg/resume/complete` | Mark completed & rename file |
| POST | `/api/tg/resume/fail` | Mark failed with error |
| GET | `/api/tg/resume/status` | Active jobs & stats |

### URL Cleaner & File Hosting

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/url/clean` | Strip tracking, resolve short URLs |
| POST | `/api/url/info` | Get URL metadata |
| POST | `/api/url/preview` | Preview URL content |
| POST | `/api/url/preview-content` | Extract content from URL |
| POST | `/api/filehost/download` | Download from file-hosting platform |

### YouTube-Specific

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/youtube/playlists` | List channel playlists |
| GET | `/api/ytdlp/uncategorized` | Uncategorized videos |
| GET | `/api/ytdlp/channel-uploads` | Channel uploads |
| GET | `/api/ytdlp/latest-report` | Latest report |
| GET | `/api/ytdlp/check-update` | Check yt-dlp version |
| POST | `/api/ytdlp/update` | Update yt-dlp |

---

## ⚙️ Configuration

Settings are stored in `backend/config/settings.json` (Python) or `backend-php/config/settings.json` (PHP).

Key settings:

```json
{
  "dl_folder":       "/sdcard/Download/MegaDL",
  "def_quality":     "best",
  "merge_format":    "mp4",
  "concurrent_frag": 4,
  "max_parallel":    3,
  "retries":         3,
  "embed_thumb":     true,
  "embed_meta":      true,
  "sponsorblock":    false,
  "archive_mode":    true,
  "speed_limit":     0,
  "telegram_api_id": "",
  "telegram_api_hash": ""
}
```

**Telegram credentials** can be configured via:
1. UI: Settings → Integrations → Telegram API section
2. Environment: `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`
3. Both — settings.json takes priority, `.env` as fallback

---

## 📱 PWA Installation

1. Open MegaDL in Chrome/Edge on Android
2. Tap the **Install** banner or browser menu → "Add to Home Screen"
3. MegaDL opens fullscreen like a native app

On desktop: click the install icon (⊕) in the address bar.

---

## 🔧 Troubleshooting

### "yt-dlp not found"
```bash
pip install yt-dlp
# or on Termux:
pkg install yt-dlp
```

### "FFmpeg not found" (videos download as separate files)
```bash
# Termux
pkg install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows: Download from https://ffmpeg.org/download.html
# Add to PATH or place ffmpeg.exe in the same folder as yt-dlp
```

### "telethon not installed" (Telegram features)
```bash
pip install telethon cryptg
```

### Download fails with "HTTP Error 403"
- Enable the **Cookies** option in the download form
- Export cookies from your browser using a cookies.txt extension
- Place `cookies.txt` in the downloads folder

### "No backend detected" in UI
- Ensure Flask is running: `python backend/app.py`
- Check `http://localhost:5000/api/ping` in browser
- For PHP: ensure Apache + mod_rewrite is enabled

### Android storage permission
```bash
# In Termux
termux-setup-storage
# Then grant storage permission when prompted
```

### Speed is slow
- Increase **Concurrent Fragments** in Settings → Network (try 8-16)
- Increase **Max Parallel Downloads**
- Disable speed limit (set to 0)

---

## 🔒 Security Notes

- URL sanitization blocks known ad/redirect domains
- Path traversal protection on all file operations
- No credentials stored in code — use `.env` or settings file
- All file operations are scoped to the configured download folder
- Input validation on all API endpoints
- Bot tokens masked in UI (`123456:****w11`)
- Telegram session files stored per-user in `.sessions/`

---

## 📋 Keyboard Shortcuts (Desktop)

| Shortcut | Action |
|---|---|
| `Ctrl + Enter` | Fetch video info |
| `Ctrl + D` | Start download |
| `Space` | Pause/Resume first active download |
| `Escape` | Close search/modal |
| `N` | New download (focuses URL input) |

---

## 🛠️ Tech Stack

- **Frontend**: Vanilla HTML5, CSS3, JavaScript (ES2022+), PWA
- **Python Backend**: Flask 3, flask-cors, SQLite3, threading, asyncio
- **PHP Backend**: PHP 8+, SQLite3, proc_open, shell_exec
- **Download Engine**: yt-dlp (supports 1000+ sites)
- **Telegram**: Telethon 1.43+ (MTProto client)
- **Media Processing**: FFmpeg (merge, convert, embed)
- **Design**: Material You, AMOLED dark mode, CSS custom properties

---

## 📄 License

MIT License — Free for personal and commercial use.

---

<p align="center">
  made with 💖 by ahmed awad
</p>

---

<p align="center">
  Made with ❤️ · Powered by <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a> & <a href="https://github.com/LonamiWebs/Telethon">Telethon</a>
</p>
