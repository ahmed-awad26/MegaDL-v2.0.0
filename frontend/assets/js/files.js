/**
 * MegaDL — files.js · logs.js · diagnostics.js · search.js · pwa.js
 * Combined auxiliary modules for file browser, logs viewer, diagnostics,
 * global search, and PWA install prompt.
 */

/* ══════════════════════════════════════════════════════════════
   FILES MODULE — grouped by channel, with player & details
   ══════════════════════════════════════════════════════════════ */

MegaDL.Files = (() => {
  const { API, Utils } = MegaDL;
  const { formatBytes, escapeHTML, haptic } = Utils;

  let currentPath = '';

  /* ── Player modal ────────────────────────────────────────── */
  let playerModal = null;

  function _ensurePlayer() {
    if (playerModal) return;
    playerModal = document.createElement('div');
    playerModal.className = 'modal-backdrop';
    playerModal.id = 'file-player-modal';
    playerModal.style.cssText = 'display:none;z-index:700;background:var(--bg-overlay)';
    playerModal.innerHTML = `
      <div class="modal" style="max-width:90vw;width:800px;background:#000;border-radius:12px;overflow:hidden">
        <div class="modal-header" style="background:#111;color:#fff;padding:10px 16px">
          <span class="modal-title" id="player-title" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">Video</span>
          <button class="icon-btn" id="player-close-btn" style="color:#fff">✕</button>
        </div>
        <div class="modal-body" style="padding:0;background:#000">
          <video id="file-video-player" controls style="width:100%;max-height:70vh;display:none" autoplay></video>
          <audio id="file-audio-player" controls style="width:100%;display:none" autoplay></audio>
        </div>
      </div>
    `;
    document.body.appendChild(playerModal);

    document.getElementById('player-close-btn')?.addEventListener('click', _closePlayer);
    playerModal.addEventListener('click', e => { if (e.target === playerModal) _closePlayer(); });

    const videoEl = document.getElementById('file-video-player');
    const audioEl = document.getElementById('file-audio-player');
    videoEl?.addEventListener('ended', _closePlayer);
    audioEl?.addEventListener('ended', _closePlayer);
  }

  function _openPlayer(filePath, fileName) {
    _ensurePlayer();
    const isVideo = /\.(mp4|mkv|webm|avi|mov)$/i.test(fileName);
    const videoEl = document.getElementById('file-video-player');
    const audioEl = document.getElementById('file-audio-player');
    const titleEl = document.getElementById('player-title');
    if (titleEl) titleEl.textContent = fileName;

    if (videoEl) { videoEl.style.display = isVideo ? 'block' : 'none'; videoEl.src = ''; }
    if (audioEl) { audioEl.style.display = isVideo ? 'none' : 'block'; audioEl.src = ''; }

    const streamUrl = API.getStreamUrl ? API.getStreamUrl(filePath) : `/api/files/stream/${encodeURIComponent(filePath)}`;
    if (isVideo && videoEl) { videoEl.src = streamUrl; videoEl.load(); videoEl.play().catch(() => {}); }
    if (!isVideo && audioEl) { audioEl.src = streamUrl; audioEl.load(); audioEl.play().catch(() => {}); }

    playerModal.style.display = 'flex';
    haptic('medium');
  }

  function _closePlayer() {
    if (!playerModal) return;
    playerModal.style.display = 'none';
    const videoEl = document.getElementById('file-video-player');
    const audioEl = document.getElementById('file-audio-player');
    if (videoEl) { videoEl.pause(); videoEl.src = ''; }
    if (audioEl) { audioEl.pause(); audioEl.src = ''; }
  }

  /* ── Duration formatting ─────────────────────────────────── */
  function _formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
  }

  /* ── Public API ──────────────────────────────────────────── */

  async function init() {
    document.getElementById('refresh-files-btn')?.addEventListener('click', () => load(currentPath));
    document.getElementById('open-folder-btn')?.addEventListener('click', openFolder);
  }

  async function load(path = '') {
    currentPath = path;
    const grid = document.getElementById('file-grid');
    if (!grid) return;

    grid.innerHTML = '<div class="empty-state"><div class="empty-icon animate-spin">🔄</div><div class="empty-title">Loading...</div></div>';

    const pathEl = document.getElementById('file-path-display');
    if (pathEl) {
      try {
        const info = await API.getSettings();
        const base = info.dlFolder || info.dl_folder || 'downloads';
        pathEl.textContent = `📁 ${base}${path ? '/' + path : ''}`;
      } catch { pathEl.textContent = ''; }
    }

    try {
      const res   = await API.listFiles(path);
      const files = res.files || [];
      _renderGrouped(grid, files);
      _updateBreadcrumb(path);
    } catch {
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load files</div></div>';
    }
  }

  /* ── Grouped rendering ───────────────────────────────────── */

  function _renderGrouped(grid, files) {
    if (!files.length) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">📂</div><div class="empty-title">Folder is empty</div></div>';
      return;
    }

    const dirs   = files.filter(f => f.type === 'dir');
    const media  = files.filter(f => f.type === 'file' && f.duration !== undefined);
    const others = files.filter(f => f.type === 'file' && f.duration === undefined);

    const parts = [];

    // ── Directories (channels) — collapsible sections ────
    for (const d of dirs) {
      parts.push(`
        <div class="file-group">
          <div class="file-group-header" onclick="MegaDL.Files.load('${escapeHTML(d.path)}')">
            <span class="file-group-icon">📁</span>
            <span class="file-group-name">${escapeHTML(d.name)}</span>
            <span class="file-group-count">${formatBytes(d.size || 0)}</span>
            <span class="file-group-arrow">›</span>
          </div>
        </div>
      `);
    }

    // ── Media files (with duration) ──────────────────────
    if (media.length) {
      parts.push(`<div class="file-group"><div class="file-group-header active" style="cursor:default"><span class="file-group-icon">🎬</span><span class="file-group-name">Media</span><span class="file-group-count">${media.length} files</span></div>`);
      for (const f of media) {
        parts.push(_fileRow(f));
      }
      parts.push('</div>');
    }

    // ── Other files (no duration) ────────────────────────
    if (others.length) {
      parts.push(`<div class="file-group"><div class="file-group-header active" style="cursor:default"><span class="file-group-icon">📄</span><span class="file-group-name">Other</span><span class="file-group-count">${others.length} files</span></div>`);
      for (const f of others) {
        parts.push(_fileRow(f));
      }
      parts.push('</div>');
    }

    grid.innerHTML = parts.join('');

    // Wire clicks
    grid.querySelectorAll('.file-row').forEach(row => {
      row.addEventListener('click',       () => _handleFileClick(row));
      row.addEventListener('contextmenu', e => _showFileContextMenu(e, row));
    });
  }

  function _fileRow(f) {
    const icon = f.duration !== undefined
      ? (f.name.match(/\.(mp4|mkv|webm|avi|mov)$/i) ? '🎬' : '🎵')
      : Utils.getFileIcon(f.name);
    const dur = f.duration ? _formatDuration(f.duration) : '';
    const size = f.size ? formatBytes(f.size) : '';
    return `
      <div class="file-row" data-path="${escapeHTML(f.path)}" data-type="${f.type}" data-media="${f.duration !== undefined}">
        <span class="file-row-icon">${icon}</span>
        <span class="file-row-name">${escapeHTML(f.name)}</span>
        <span class="file-row-dur">${dur}</span>
        <span class="file-row-size">${size}</span>
      </div>
    `;
  }

  function _handleFileClick(row) {
    const path  = row.dataset.path;
    const type  = row.dataset.type;
    const media = row.dataset.media === 'true';
    haptic('light');

    if (type === 'dir') {
      load(path);
    } else if (media) {
      const name = row.querySelector('.file-row-name')?.textContent || path;
      _openPlayer(path, name);
    } else {
      window.open(API.getDownloadUrl(path), '_blank');
    }
  }

  /* ── Breadcrumb ──────────────────────────────────────────── */

  function _updateBreadcrumb(path) {
    const crumb = document.getElementById('breadcrumb');
    if (!crumb) return;
    const parts = ['Downloads', ...path.split('/').filter(Boolean)];
    crumb.innerHTML = parts.map((p, i) => `
      ${i > 0 ? '<span class="breadcrumb-sep">›</span>' : ''}
      <span class="breadcrumb-item${i === parts.length - 1 ? ' active' : ''}" data-index="${i}">${escapeHTML(p)}</span>
    `).join('');

    crumb.querySelectorAll('[data-index]').forEach(el => {
      el.addEventListener('click', () => {
        const idx   = parseInt(el.dataset.index);
        load(path.split('/').slice(0, idx).join('/'));
      });
    });
  }

  /* ── Context menu ────────────────────────────────────────── */

  function _showFileContextMenu(e, row) {
    e.preventDefault();
    haptic('light');
    const path = row.dataset.path;
    const name = row.querySelector('.file-row-name')?.textContent;
    const media = row.dataset.media === 'true';

    document.querySelectorAll('.context-menu').forEach(m => m.remove());

    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.cssText = `left:${e.clientX}px;top:${e.clientY}px`;
    menu.innerHTML = media
      ? `<div class="context-item" data-action="play">▶ Play</div><div class="context-item" data-action="open">📂 Open</div><div class="context-sep"></div><div class="context-item" data-action="rename">✏️ Rename</div><div class="context-sep"></div><div class="context-item danger" data-action="delete">🗑 Delete</div>`
      : `<div class="context-item" data-action="open">📂 Open</div><div class="context-item" data-action="rename">✏️ Rename</div><div class="context-sep"></div><div class="context-item danger" data-action="delete">🗑 Delete</div>`;

    document.body.appendChild(menu);

    menu.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', async () => {
        menu.remove();
        const action = btn.dataset.action;
        if (action === 'play')  { _closePlayer(); _openPlayer(path, name || path); }
        if (action === 'open')  window.open(API.getDownloadUrl(path), '_blank');
        if (action === 'delete') {
          MegaDL.App?.confirm(`Delete "${name}"?`, async () => {
            await API.deleteFile(path);
            load(currentPath);
          });
        }
        if (action === 'rename') {
          const newName = prompt('New filename:', name);
          if (newName) {
            await API.renameFile(path, newName);
            load(currentPath);
          }
        }
      });
    });

    const close = e2 => { if (!menu.contains(e2.target)) { menu.remove(); document.removeEventListener('click', close); } };
    setTimeout(() => document.addEventListener('click', close), 50);
  }

  function openFolder() {
    MegaDL.App?.toast('Open folder in system is browser-limited', 'info');
  }

  return { init, load, _closePlayer };
})();


/* ══════════════════════════════════════════════════════════════
   LOGS MODULE
   ══════════════════════════════════════════════════════════════ */

MegaDL.Logs = (() => {
  const { API, Utils } = MegaDL;
  const { escapeHTML } = Utils;

  let autoScroll = true;
  let pollTimer  = null;

  function init() {
    document.getElementById('clear-logs-btn')?.addEventListener('click', async () => {
      await API.clearLogs().catch(() => {});
      document.getElementById('logs-viewer').innerHTML = '';
      MegaDL.App?.toast('Logs cleared', 'success');
    });

    document.getElementById('export-logs-btn')?.addEventListener('click', exportLogs);

    document.getElementById('logs-autoscroll')?.addEventListener('change', e => {
      autoScroll = e.target.checked;
    });

    document.getElementById('log-level-filter')?.addEventListener('change', fetchLogs);
  }

  async function fetchLogs() {
    const level = document.getElementById('log-level-filter')?.value || 'all';
    try {
      const res  = await API.getLogs(level !== 'all' ? { level } : {});
      const logs = res.logs || res || [];
      renderLogs(logs);
    } catch {}
  }

  function renderLogs(logs) {
    const viewer = document.getElementById('logs-viewer');
    if (!viewer) return;

    if (!logs.length) {
      viewer.innerHTML = '<div class="log-entry info"><span class="log-time">--:--:--</span><span class="log-level info">INFO</span><span class="log-msg">No logs yet</span></div>';
      return;
    }

    viewer.innerHTML = logs.map(log => `
      <div class="log-entry ${log.level || 'info'}">
        <span class="log-time">${log.time || '--:--:--'}</span>
        <span class="log-level ${log.level || 'info'}">${(log.level || 'info').toUpperCase()}</span>
        <span class="log-msg">${escapeHTML(log.message || log.msg || '')}</span>
      </div>
    `).join('');

    if (autoScroll) viewer.scrollTop = viewer.scrollHeight;
  }

  // Called from app to append a new log entry live
  function appendLog(message, level = 'info') {
    const viewer = document.getElementById('logs-viewer');
    if (!viewer) return;
    const now  = new Date().toTimeString().slice(0, 8);
    const item = document.createElement('div');
    item.className = `log-entry ${level}`;
    item.innerHTML = `
      <span class="log-time">${now}</span>
      <span class="log-level ${level}">${level.toUpperCase()}</span>
      <span class="log-msg">${escapeHTML(message)}</span>
    `;
    viewer.appendChild(item);
    if (autoScroll) viewer.scrollTop = viewer.scrollHeight;
  }

  async function exportLogs() {
    try {
      const res  = await API.getLogs();
      const logs = res.logs || res || [];
      const text = logs.map(l => `[${l.time}] [${l.level?.toUpperCase()}] ${l.message}`).join('\n');
      const blob = new Blob([text], { type: 'text/plain' });
      const url  = URL.createObjectURL(blob);
      const a    = Object.assign(document.createElement('a'), { href: url, download: `megadl-logs-${Date.now()}.txt` });
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  }

  function startPolling() {
    stopPolling();
    fetchLogs();
    pollTimer = setInterval(fetchLogs, 5000);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
  }

  return { init, fetchLogs, appendLog, startPolling, stopPolling };
})();


/* ══════════════════════════════════════════════════════════════
   DIAGNOSTICS MODULE
   ══════════════════════════════════════════════════════════════ */

MegaDL.Diagnostics = (() => {
  const { API } = MegaDL;

  function init() {
    document.getElementById('run-diag-btn')?.addEventListener('click', run);
  }

  async function run() {
    const btn = document.getElementById('run-diag-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }

    const output = document.getElementById('diag-output');
    if (output) output.textContent = 'Running diagnostics...\n';

    // Set all to loading
    ['python','ytdlp','ffmpeg','php','backend','storage','perms','network'].forEach(id => {
      _setDiagItem(id, '⏳', 'Checking...', '');
    });

    try {
      const res = await API.runDiagnostics();
      _renderResults(res);
    } catch (err) {
      if (output) output.textContent += `\n❌ Backend not reachable: ${err.message}`;
      // Run client-side checks
      await _clientSideChecks();
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Run Check'; }
    }
  }

  function _renderResults(res) {
    const output = document.getElementById('diag-output');
    const checks = res.checks || {};
    const log    = [];

    _applyCheck('python',  checks.python,  log);
    _applyCheck('ytdlp',   checks.ytdlp,   log);
    _applyCheck('ffmpeg',  checks.ffmpeg,  log);
    _applyCheck('php',     checks.php,     log);
    _applyCheck('backend', { ok: true, version: res.backend || 'unknown' }, log);
    _applyCheck('storage', checks.storage, log);
    _applyCheck('perms',   checks.writable, log);
    _applyCheck('network', checks.network, log);

    if (output) output.textContent = log.join('\n');
  }

  function _applyCheck(id, data, log) {
    if (!data) {
      _setDiagItem(id, '❓', 'Not checked', 'fail');
      log.push(`[${id.toUpperCase()}] Not checked`);
      return;
    }
    const ok      = data.ok || data.available || data.writable;
    const version = data.version || '';
    const status  = ok ? '✅' : '❌';
    const cls     = ok ? 'ok' : 'fail';
    const label   = ok ? (version ? version : 'OK') : (data.error || 'Not found');
    _setDiagItem(id, status, label, cls);
    log.push(`[${id.toUpperCase()}] ${status} ${label}`);
  }

  function _setDiagItem(id, status, value, cls) {
    const item  = document.getElementById(`diag-${id}`);
    if (!item) return;
    const valEl = item.querySelector('.diag-value');
    const stEl  = item.querySelector('.diag-status');
    if (valEl) valEl.textContent = value;
    if (stEl)  stEl.textContent  = status;
    item.className = `diag-item ${cls || ''}`.trim();
  }

  async function _clientSideChecks() {
    const output = document.getElementById('diag-output');
    const log    = ['=== Client-Side Checks ==='];

    // Network check
    const online = navigator.onLine;
    _setDiagItem('network', online ? '✅' : '❌', online ? 'Online' : 'Offline', online ? 'ok' : 'fail');
    log.push(`[NETWORK] ${online ? '✅ Online' : '❌ Offline'}`);

    // Backend detection
    const backend = API.getBackend();
    _setDiagItem('backend', backend ? '✅' : '❌', backend || 'Not detected', backend ? 'ok' : 'fail');
    log.push(`[BACKEND] ${backend || 'Not detected'}`);

    // Storage check
    try {
      localStorage.setItem('_megadl_test', '1');
      localStorage.removeItem('_megadl_test');
      _setDiagItem('storage', '✅', 'LocalStorage OK', 'ok');
      log.push('[STORAGE] ✅ LocalStorage OK');
    } catch {
      _setDiagItem('storage', '❌', 'LocalStorage unavailable', 'fail');
      log.push('[STORAGE] ❌ LocalStorage unavailable');
    }

    if (output) output.textContent += '\n' + log.join('\n');
  }

  return { init, run };
})();


/* ══════════════════════════════════════════════════════════════
   SEARCH MODULE
   ══════════════════════════════════════════════════════════════ */

MegaDL.Search = (() => {
  const { API, Utils } = MegaDL;
  const { debounce, escapeHTML, formatRelativeTime } = Utils;

  function init() {
    document.getElementById('search-btn')?.addEventListener('click', open);
    document.getElementById('close-search-btn')?.addEventListener('click', close);

    const input = document.getElementById('global-search');
    input?.addEventListener('input', debounce(search, 300));

    // Close on Escape
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') close();
    });

    // Close backdrop click
    document.getElementById('search-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'search-overlay') close();
    });
  }

  function open() {
    const overlay = document.getElementById('search-overlay');
    const input   = document.getElementById('global-search');
    if (overlay) overlay.style.display = 'flex';
    if (input)   { input.value = ''; setTimeout(() => input.focus(), 100); }
  }

  function close() {
    const overlay = document.getElementById('search-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  async function search() {
    const q = document.getElementById('global-search')?.value?.trim();
    const results = document.getElementById('search-results');
    if (!results) return;

    if (!q || q.length < 2) {
      results.innerHTML = '<div class="empty-state"><div class="empty-subtitle">Start typing to search...</div></div>';
      return;
    }

    results.innerHTML = '<div class="empty-state"><div class="empty-icon animate-spin">🔍</div></div>';

    // Search locally from jobs first, then history
    const allJobs = MegaDL.Jobs.getAll().filter(j =>
      (j.title || '').toLowerCase().includes(q.toLowerCase()) ||
      (j.url   || '').toLowerCase().includes(q.toLowerCase())
    );

    let history = [];
    try {
      const res = await API.getHistory(200);
      history = (res.history || []).filter(h =>
        (h.title || '').toLowerCase().includes(q.toLowerCase())
      );
    } catch {}

    if (!allJobs.length && !history.length) {
      results.innerHTML = `<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-title">No results for "${escapeHTML(q)}"</div></div>`;
      return;
    }

    results.innerHTML = [
      ...allJobs.map(j => _resultHTML(j, 'job')),
      ...history.slice(0, 20).map(h => _resultHTML(h, 'history')),
    ].join('');
  }

  function _resultHTML(item, type) {
    const icon  = type === 'job' ? '⬇️' : '🕒';
    const state = type === 'job' ? `<span class="job-state ${item.state}">${item.state}</span>` : '';
    return `
      <div class="list-item" data-type="${type}" data-id="${escapeHTML(item.id || '')}">
        <div class="list-item-content">
          <div class="list-title">${escapeHTML(item.title || item.url || '—')}</div>
          <div class="list-subtitle">${icon} ${type} · ${MegaDL.Utils.formatRelativeTime(item.created_at || item.ts)}</div>
        </div>
        ${state}
      </div>
    `;
  }

  return { init, open, close };
})();


/* ══════════════════════════════════════════════════════════════
   PWA MODULE
   ══════════════════════════════════════════════════════════════ */

MegaDL.PWA = (() => {
  let deferredPrompt = null;

  function init() {
    // Capture install event
    window.addEventListener('beforeinstallprompt', e => {
      e.preventDefault();
      deferredPrompt = e;
      // Show install banner after 3 seconds
      setTimeout(showBanner, 3000);
    });

    window.addEventListener('appinstalled', () => {
      hideBanner();
      MegaDL.App?.toast('📱 MegaDL installed successfully!', 'success');
    });

    document.getElementById('pwa-install')?.addEventListener('click', install);
    document.getElementById('pwa-dismiss')?.addEventListener('click', () => {
      hideBanner();
      MegaDL.Utils.store.set('pwa_dismissed', Date.now());
    });
  }

  function showBanner() {
    const dismissed = MegaDL.Utils.store.get('pwa_dismissed');
    // Don't show if dismissed within last 7 days
    if (dismissed && Date.now() - dismissed < 7 * 86400000) return;
    // Don't show if already in standalone mode
    if (window.matchMedia('(display-mode: standalone)').matches) return;

    const banner = document.getElementById('pwa-banner');
    if (banner) banner.style.display = 'flex';
  }

  function hideBanner() {
    const banner = document.getElementById('pwa-banner');
    if (banner) banner.style.display = 'none';
  }

  async function install() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    deferredPrompt = null;
    hideBanner();
    if (outcome === 'accepted') MegaDL.App?.toast('Installing MegaDL...', 'success');
  }

  return { init, install };
})();
