# Telegram Downloader Feature Analysis: AntiGravity vs MegaDL

## Overview
AntiGravity Suite (Telegram downloader) contains many advanced features that MegaDL's Telegram module lacks. Below is a detailed comparison and implementation roadmap.

---

## 📊 Feature Comparison

### 1. **Authentication & Credentials**

#### AntiGravity ✅
- Store API ID/Hash in configuration file
- Persistent session management via Telethon
- 2FA support built-in
- Auto-load credentials from environment variables

#### MegaDL ❌
- Basic auth flow
- No persistent credential storage
- Session handling exists but incomplete

**Action**: Implement persistent credential storage

---

### 2. **Media Type Filtering**

#### AntiGravity ✅
- Photo filtering (InputMessagesFilterPhotos)
- Video filtering (InputMessagesFilterVideo)
- Document filtering (InputMessagesFilterDocument)
- Audio filtering (InputMessagesFilterMusic)
- Per-type limit configuration (e.g., "Last 50 photos")
- Bulk view modal for browsing before download

#### MegaDL ❌
- Basic media filtering
- No per-type limit controls
- No bulk view/preview

**Action**: Add selective media type filters with limits

---

### 3. **Scan/Preview Capabilities**

#### AntiGravity ✅
- `scan_chat_media()`: Count files and total size before downloading
- `list_chat_media()`: List specific media type with sizes
- Shows count + size breakdown (Photos, Videos, Docs, Audio)
- Auto-shows overview in config modal
- UI displays statistics

#### MegaDL ❌
- No pre-download scanning
- No size estimation
- No media count preview

**Action**: Implement chat media scanning with statistics

---

### 4. **Download Management**

#### AntiGravity ✅
- Smart resumable downloads with rollback (2MB buffer)
- Pause/Resume functionality with state persistence
- Stop with save state
- Concurrent downloads (5 concurrent semaphore)
- Original filename preservation (multiple fallback strategies)
- Skip existing files option
- Memory-efficient message processing

#### MegaDL ✅ (Partially)
- Some pause/resume support
- Basic concurrent downloads
- But missing: resumable downloads, smart rollback, filename preservation logic

**Action**: Enhance download resumption and filename handling

---

### 5. **Filename Preservation**

#### AntiGravity ✅
```python
Priority:
1. DocumentAttributeFilename (most reliable)
2. Audio/Video metadata (performer, title)
3. Caption text
4. Date-based naming (YYYYMMDD_HHMMSS)
5. ID-based fallback
```

#### MegaDL ❌
- Basic filename handling
- No smart attribute extraction

**Action**: Implement multi-layer filename fallback logic

---

### 6. **Download State Persistence**

#### AntiGravity ✅
- `downloads_state.json`: Saves all job states
- Auto-resume on restart (running → paused)
- Per-job logging
- Full history of operations
- Memory management with message_ids list

#### MegaDL ✅ (Partially)
- Database storage exists
- But missing: detailed per-job state, full history

**Action**: Enhance state persistence with detailed logs

---

### 7. **Bot Pool System (AI Scoring)**

#### AntiGravity ✅
```python
Weighted AI scoring model:
- Load balancing (active_tasks) - 40% weight
- Speed metrics (avg_speed_bps) - 35% weight
- Failure rate (total_failed/total) - 20% weight
- Recency (time since last use) - 5% weight

Features:
- Token validation via Telegram Bot API
- Per-bot statistics tracking
- Dynamic bot selection based on score
```

#### MegaDL ✅ (Partially)
- Bot pool exists
- But missing: AI scoring system, performance metrics, dynamic selection

**Action**: Implement weighted AI scoring for bot selection

---

### 8. **Performance Monitoring**

#### AntiGravity ✅
- CPU usage monitoring (real-time)
- RAM usage monitoring
- Network download speed & total
- Network upload speed & total
- Storage usage calculation
- Dialog count badge

#### MegaDL ❌
- No system monitoring
- No performance metrics display

**Action**: Add system resource monitoring dashboard

---

### 9. **API Key Management**

#### AntiGravity ✅
- Universal provider support (OpenAI, Claude, Gemini, etc.)
- Key validation before saving
- Masked key display for security
- Load keys from file
- Set/Delete operations

#### MegaDL ✅
- API key manager exists
- But needs: better validation, masked display

**Action**: Enhance API key validation and UI masking

---

### 10. **Background Customization**

#### AntiGravity ✅
- Custom background image upload
- Blur intensity control (0-50px)
- Opacity/transparency control
- LocalStorage persistence

#### MegaDL ❌
- No background customization

**Action**: Add custom background & blur controls (nice-to-have)

---

### 11. **Download Folder Organization**

#### AntiGravity ✅
```
downloads/Telegram/{ChatName}/
```

#### MegaDL ✅
- Smart folder structure based on platform
- But: no grouping by media type

**Action**: Add media type subfolder organization

---

### 12. **Archive System**

#### AntiGravity ✅
- Two archive formats:
  - `master.txt`: yt-dlp format (file IDs)
  - `master.json`: Extended metadata (title, time)
- Prevents duplicate downloads
- Per-job tracking

#### MegaDL ✅ (Partially)
- Archive exists
- But needs: JSON format, extended metadata

**Action**: Enhance archive with JSON metadata

---

## 🔧 Implementation Priority

### **CRITICAL (Block Issues)**
1. ✅ Fix Telegram credentials not persisting
2. ✅ Implement persistent credential storage
3. ✅ Add 2FA password handling
4. Implement chat media scanning (stats preview)
5. Add smart filename preservation logic

### **HIGH (Core Features)**
6. Implement resumable downloads with rollback
7. Add per-media-type filtering with limits
8. Implement weighted AI bot pool scoring
9. Add download state persistence & logging
10. Add bulk media preview modal

### **MEDIUM (Polish)**
11. Add system resource monitoring dashboard
12. Enhance API key validation & UI masking
13. Implement media type subfolder organization
14. Add background customization

### **LOW (Nice-to-have)**
15. Add custom background blur/opacity controls

---

## 📁 Files to Implement/Modify in MegaDL

### New Files
- `backend/services/tg_scan_service.py` - Media scanning logic
- `backend/services/tg_filename_service.py` - Filename extraction
- `backend/services/tg_bot_scorer.py` - AI bot selection
- `frontend/assets/js/tg-scan.js` - Scan UI logic
- `frontend/assets/js/tg-bots.js` - Bot pool scoring display

### Modified Files
- `backend/services/telegram_service.py` - Add scanning, AI scoring
- `backend/routes/telegram.py` - Add new endpoints
- `frontend/index.html` - Add scan/filter UI
- `frontend/assets/js/telegram.js` - Enhanced Telegram logic

---

## 🚀 Implementation Checklist

### Phase 1: Credential & Auth (Fix)
- [ ] Save API ID/Hash to settings
- [ ] Auto-load from environment
- [ ] Persist session properly
- [ ] Test 2FA flow

### Phase 2: Scanning & Preview
- [ ] Implement `scan_chat_media()` backend
- [ ] Add media count/size API endpoint
- [ ] Create scan modal UI
- [ ] Test with real chat

### Phase 3: Smart Downloads
- [ ] Implement `_get_original_filename()` logic
- [ ] Add filename attribute extraction
- [ ] Implement rollback mechanism
- [ ] Test resume from pause

### Phase 4: Bot Pool Scoring
- [ ] Implement BotStats tracking
- [ ] Add weighted scoring formula
- [ ] Create bot selection algorithm
- [ ] Display metrics in UI

### Phase 5: Polish
- [ ] Add system monitoring
- [ ] Enhance archive system
- [ ] Add background customization
- [ ] Test end-to-end

---

## Code Examples from AntiGravity

### Smart Filename Extraction
```python
def _get_original_filename(message) -> str:
    if message.document:
        # 1. DocumentAttributeFilename
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                return _safe_name(attr.file_name)
        # 2. Audio/Video metadata
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeAudio):
                performer = attr.performer or ""
                title = attr.title or ""
                return f"{performer} - {title}"
        # 3. Fallback
        return f"file_{message.id}"
```

### Resumable Download
```python
async def _download_resumable(self, client, message, file_path, job):
    CHUNK_SIZE = 1024 * 1024
    resume_offset = 0
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        resume_offset = max(0, file_size - ROLLBACK)
        resume_offset = (resume_offset // CHUNK_SIZE) * CHUNK_SIZE
    
    with open(file_path, "wb" if resume_offset == 0 else "r+b") as f:
        if resume_offset > 0:
            f.seek(resume_offset)
            f.truncate()
        async for chunk in client.iter_download(message, offset=resume_offset):
            if job["status"] != "running":
                raise Exception("Job paused or stopped")
            f.write(chunk)
```

### AI Bot Scoring
```python
def _score_bot(self, b: BotStats) -> float:
    fail_rate = (b.total_failed / (b.total_done + b.total_failed)) if (b.total_done + b.total_failed) > 0 else 0.0
    
    load_score = 1.0 / (1 + b.active_tasks)           # 40%
    speed_score = min(b.avg_speed_bps / 1_000_000, 1) # 35%
    fail_score = 1.0 - fail_rate                       # 20%
    time_score = min((time.time() - b.last_used) / 60, 1.0) # 5%
    
    return (0.40 * load_score + 0.35 * speed_score + 0.20 * fail_score + 0.05 * time_score)
```

---

## Testing Plan

1. **Auth Testing**
   - Save credentials to .env
   - Auto-load on startup
   - Verify session persistence

2. **Scanning Testing**
   - Test with channel (public, private)
   - Verify counts accurate
   - Check size calculation

3. **Download Testing**
   - Test pause/resume
   - Verify filename preservation
   - Check resumable logic with large files

4. **Bot Pool Testing**
   - Add 2-3 bot tokens
   - Monitor scoring
   - Verify best bot selection

5. **Integration Testing**
   - Test full flow: auth → scan → download → resume
   - Test with multiple chats in parallel
   - Verify state persistence on restart

