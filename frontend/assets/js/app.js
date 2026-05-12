/**
 * MegaDL — app.js
 * Main application orchestrator.
 * Bootstraps all modules, wires up UI events, manages toasts and modals.
 */

MegaDL.App = (() => {
  const { API, Utils, Config, Router, Jobs, Downloader,
          Settings, Files, Logs, Diagnostics, Search, PWA, Telegram } = MegaDL;
  const { show, hide, toggle, haptic, formatBytes, formatRelativeTime,
          escapeHTML, store, debounce } = Utils;

  /* ── Bootstrap ───────────────────────────────────────────── */

  async function init() {
    // Init router first (pages need to exist)
    Router.init();

    // Register per-page handlers
    Router.register('files',       { onEnter: () => Files.load('') });
    Router.register('logs',        { onEnter: () => Logs.fetchLogs() });
    Router.register('diagnostics', { onEnter: () => Diagnostics.run() });
    Router.register('telegram',    { onEnter: () => Telegram.onEnter() });
    Router.register('downloads',   { onEnter: () => loadDownloads() });
    Router.register('history',     { onEnter: () => loadHistory() });
    Router.register('archive',     { onEnter: () => loadArchive() });
    Router.register('favorites',   { onEnter: () => loadFavorites() });
    Router.register('settings',    { onEnter: () => Settings.refresh() });
    Router.register('home',        { onEnter: () => {} });
    Router.register('active',      { onEnter: () => {} });
    Router.register('failed',      { onEnter: () => MegaDL.Jobs.checkFailedLinks() });

    // Init modules
    await Settings.init();
    Downloader.init();
    Files.init();
    Logs.init();
    Diagnostics.init();
    Telegram.init();
    Search.init();
    PWA.init();
    Jobs.init();

    // Wire UI
    _initSidebar();
    _initModals();
    _initBulkControls();
    _initPageToolbars();

    // Detect backend then start
    const backend = await API.detectBackend();
    _updateBackendIndicator(backend);
    Logs.appendLog(`Backend: ${backend || 'none detected'}`, backend ? 'info' : 'warning');

    // Start job polling
    Jobs.startPolling();

    // Start stats polling
    _startStatsPolling();

    // Load history for about/stats
    await _refreshStats();

    // Check first-run setup (Telegram API keys)
    _checkFirstRunSetup();

    // Show app and hide splash
    _hideSplash();

    // Store version
    document.getElementById('app-version')?.textContent && null;
    [
      document.getElementById('app-version'),
      document.getElementById('about-version'),
    ].forEach(el => { if (el) el.textContent = Config.version; });

    document.getElementById('about-backend')?.textContent && null;
    const abBE = document.getElementById('about-backend');
    if (abBE) abBE.textContent = backend ? `${backend.charAt(0).toUpperCase() + backend.slice(1)} Backend` : 'Not connected';

    document.getElementById('about-platform')?.textContent && null;
    const abPl = document.getElementById('about-platform');
    if (abPl) {
      const standalone = window.matchMedia('(display-mode: standalone)').matches;
      const mobile = /Android|iPhone|iPad/i.test(navigator.userAgent);
      abPl.textContent = standalone ? 'Installed PWA' : mobile ? 'Mobile Browser' : 'Web Browser';
    }

    Logs.appendLog('MegaDL ready', 'info');
  }

  /* ── First-Run Setup ────────────────────────────────────── */

  function _checkFirstRunSetup() {
    const settings = MegaDL.Settings?.getCurrent() || {};
    const hasApiId = settings.telegram_api_id && settings.telegram_api_id.length > 0;
    const hasApiHash = settings.telegram_api_hash && settings.telegram_api_hash.length > 0;

    if (!hasApiId || !hasApiHash) {
      setTimeout(() => _showSetupOverlay(), 1500);
    }
  }

  function _showSetupOverlay() {
    // Check if already exists
    if (document.getElementById('setup-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'setup-overlay';
    overlay.className = 'modal-backdrop';
    overlay.style.cssText = 'display:flex;z-index:600;background:var(--bg-overlay)';

    overlay.innerHTML = `
      <div class="modal glass-card" style="max-width:480px;width:90%">
        <div class="modal-header">
          <span class="modal-title" style="font-size:1.1rem">⚙️ First-Time Setup</span>
        </div>
        <div class="modal-body">
          <div class="modal-message" style="margin-bottom:16px;line-height:1.6">
            Welcome to MegaDL! To enable Telegram downloads, enter your API credentials.
            <br><br>
            <small style="color:var(--text-muted)">
              Get them at <a href="https://my.telegram.org/apps" target="_blank" rel="noopener" style="color:var(--accent)">my.telegram.org/apps</a>
            </small>
          </div>
          <div class="setting-item" style="margin-bottom:12px">
            <div class="setting-info">
              <div class="setting-name">API ID</div>
              <div class="setting-desc">Your Telegram API ID (integer)</div>
            </div>
            <input type="text" class="setting-input" id="setup-api-id" placeholder="1234567" />
          </div>
          <div class="setting-item" style="margin-bottom:16px">
            <div class="setting-info">
              <div class="setting-name">API Hash</div>
              <div class="setting-desc">Your Telegram API hash (hex string)</div>
            </div>
            <input type="text" class="setting-input" id="setup-api-hash" placeholder="a1b2c3d4e5f6..." />
          </div>
          <div class="action-row">
            <button class="btn btn-secondary" id="setup-skip-btn">Skip</button>
            <button class="btn btn-primary" id="setup-save-btn">Save & Continue</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    document.getElementById('setup-save-btn')?.addEventListener('click', async () => {
      const apiId = document.getElementById('setup-api-id')?.value?.trim();
      const apiHash = document.getElementById('setup-api-hash')?.value?.trim();
      if (!apiId || !apiHash) {
        MegaDL.App?.toast('Please enter both API ID and API Hash', 'warning');
        return;
      }
      await API.saveSettings({ telegram_api_id: apiId, telegram_api_hash: apiHash });
      MegaDL.Settings?.updateKeys({ telegram_api_id: apiId, telegram_api_hash: apiHash });
      overlay.remove();
      MegaDL.App?.toast('✅ Telegram credentials saved!', 'success');
    });

    document.getElementById('setup-skip-btn')?.addEventListener('click', () => {
      overlay.remove();
      MegaDL.App?.toast('You can configure Telegram later in Settings > Integrations', 'info');
    });
  }

  /* ── Splash hide ─────────────────────────────────────────── */

  function _hideSplash() {
    const splash = document.getElementById('splash-screen');
    const app    = document.getElementById('app');
    setTimeout(() => {
      if (splash) splash.classList.add('hide');
      if (app)    app.style.display = 'flex';
      setTimeout(() => { if (splash) splash.style.display = 'none'; }, 500);
    }, 1200);
  }

  /* ── Backend indicator ───────────────────────────────────── */

  function _updateBackendIndicator(backend) {
    const dot   = document.querySelector('.backend-dot');
    const label = document.getElementById('backend-label');
    if (dot) dot.className = `backend-dot ${backend ? 'online' : 'error'}`;
    if (label) label.textContent = backend
      ? `${backend.charAt(0).toUpperCase() + backend.slice(1)} Backend`
      : 'No backend';
  }

  /* ── Sidebar (mobile) ────────────────────────────────────── */

  function _initSidebar() {
    const btn     = document.getElementById('menu-btn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    btn?.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      overlay?.classList.toggle('visible', open);
      haptic('light');
    });

    overlay?.addEventListener('click', () => {
      sidebar?.classList.remove('open');
      overlay.classList.remove('visible');
    });
  }

  /* ── Modals ──────────────────────────────────────────────── */

  function _initModals() {
    // Close buttons
    document.querySelectorAll('[data-modal]').forEach(btn => {
      btn.addEventListener('click', () => {
        const modal = document.getElementById(btn.dataset.modal);
        if (modal) modal.style.display = 'none';
      });
    });

    // Close on backdrop click
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
      backdrop.addEventListener('click', e => {
        if (e.target === backdrop) backdrop.style.display = 'none';
      });
    });

    // Confirm dialog
    let _confirmCallback = null;
    document.getElementById('confirm-ok-btn')?.addEventListener('click', () => {
      if (_confirmCallback) _confirmCallback();
      _confirmCallback = null;
      hide('modal-confirm');
    });
    document.getElementById('confirm-cancel-btn')?.addEventListener('click', () => {
      _confirmCallback = null;
      hide('modal-confirm');
    });

    // Store confirm fn on MegaDL.App
    MegaDL.App._showConfirm = (message, title, cb) => {
      _confirmCallback = cb;
      const titleEl = document.getElementById('confirm-title');
      const msgEl   = document.getElementById('confirm-message');
      if (titleEl) titleEl.textContent = title || 'Confirm';
      if (msgEl)   msgEl.textContent   = message;
      show('modal-confirm', 'flex');
    };
  }

  /* ── Bulk job controls ───────────────────────────────────── */

  function _initBulkControls() {
    document.getElementById('pause-all-btn')?.addEventListener('click',  () => { haptic(); Jobs.pauseAll();  });
    document.getElementById('resume-all-btn')?.addEventListener('click', () => { haptic(); Jobs.resumeAll(); });
    document.getElementById('cancel-all-btn')?.addEventListener('click', () => {
      confirm('Cancel all active downloads?', () => Jobs.cancelAll());
    });
    document.getElementById('clear-history-btn')?.addEventListener('click', () => {
      confirm('Clear all history?', async () => {
        await API.clearHistory();
        loadHistory();
      });
    });
    document.getElementById('clear-failed-btn')?.addEventListener('click', () => { haptic(); Jobs.clearFailedLinks(); });
    document.getElementById('retry-failed-btn')?.addEventListener('click', () => { haptic(); Jobs.retryFailedLinks(); });

    document.getElementById('clear-archive-btn')?.addEventListener('click', () => {
      confirm('Clear archive?', async () => {
        await API.clearArchive();
        loadArchive();
      });
    });
  }

  /* ── Page toolbars ───────────────────────────────────────── */

  function _initPageToolbars() {
    // Downloads search/sort/filter
    const dlSearch = document.getElementById('dl-search');
    dlSearch?.addEventListener('input', debounce(loadDownloads, 300));
    document.getElementById('dl-sort')?.addEventListener('change', loadDownloads);
    document.getElementById('dl-filter')?.addEventListener('change', loadDownloads);

    // History search
    document.getElementById('hist-search')?.addEventListener('input', debounce(loadHistory, 300));
  }

  /* ── Stats polling ───────────────────────────────────────── */

  function _startStatsPolling() {
    _refreshStats();
    setInterval(_refreshStats, Config.statsPollInterval);
  }

  async function _refreshStats() {
    try {
      const stats = await API.getStats();
      Utils.setText('stat-total',  stats.total   || 0);
      Utils.setText('stat-active', stats.active  || 0);
      Utils.setText('stat-done',   stats.done    || 0);
      Utils.setText('stat-size',   formatBytes(stats.total_bytes || 0));

      // Storage bar
      if (stats.storage) {
        const pct = (stats.storage.used / stats.storage.total * 100).toFixed(1);
        const fill = document.getElementById('storage-fill');
        const text = document.getElementById('storage-text');
        if (fill) fill.style.width = `${pct}%`;
        if (text) text.textContent = `${formatBytes(stats.storage.used)} / ${formatBytes(stats.storage.total)}`;
      }
    } catch {}
  }

  /* ── Downloads page ──────────────────────────────────────── */

  async function loadDownloads() {
    const grid    = document.getElementById('downloads-grid');
    if (!grid) return;

    const q      = document.getElementById('dl-search')?.value?.trim() || '';
    const sort   = document.getElementById('dl-sort')?.value  || 'date_desc';
    const filter = document.getElementById('dl-filter')?.value || 'all';

    try {
      const res  = await API.getJobs({ sort, filter, q });
      const list = res.jobs || [];

      if (!list.length) {
        grid.innerHTML = '<div class="empty-state"><div class="empty-icon">📂</div><div class="empty-title">No downloads found</div></div>';
        return;
      }

      grid.innerHTML = list.map(job => {
        const thumb = job.thumbnail
          ? `<img class="dl-card-thumb" src="${escapeHTML(job.thumbnail)}" loading="lazy" alt="" />`
          : `<div class="dl-card-thumb" style="display:flex;align-items:center;justify-content:center;font-size:2rem">${Utils.getSiteIcon(job.url || '')}</div>`;
        const dur = job.duration ? `<span class="dl-card-duration">${Utils.formatDuration(job.duration)}</span>` : '';
        return `
          <div class="dl-card" data-job-id="${escapeHTML(job.id)}">
            <div class="dl-card-thumb-wrap">${thumb}${dur}</div>
            <div class="dl-card-title">${escapeHTML(job.title || job.url || '—')}</div>
            <div class="dl-card-meta">${job.state} · ${formatRelativeTime(job.created_at)}</div>
          </div>
        `;
      }).join('');

      grid.querySelectorAll('[data-job-id]').forEach(card => {
        card.addEventListener('click', () => Jobs.showJobDetail(card.dataset.jobId));
      });
    } catch {
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load downloads</div></div>';
    }
  }

  /* ── History page ────────────────────────────────────────── */

  async function loadHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;
    const q = document.getElementById('hist-search')?.value?.trim() || '';
    try {
      const res  = await API.getHistory(200);
      let items  = res.history || [];
      if (q) items = items.filter(h => (h.title || h.url || '').toLowerCase().includes(q.toLowerCase()));

      if (!items.length) {
        list.innerHTML = '<div class="empty-state"><div class="empty-icon">🕒</div><div class="empty-title">No history</div></div>';
        return;
      }

      list.innerHTML = items.map(h => `
        <div class="history-item">
          <img class="history-thumb" src="${escapeHTML(h.thumbnail || '')}" alt="" loading="lazy"
            onerror="this.style.display='none'" />
          <div class="history-info">
            <div class="history-title">${escapeHTML(h.title || h.url || '—')}</div>
            <div class="history-meta">${formatRelativeTime(h.created_at)} · ${h.state}</div>
          </div>
          <span class="history-re-dl" data-url="${escapeHTML(h.url || '')}">↓ Redownload</span>
        </div>
      `).join('');

      list.querySelectorAll('[data-url]').forEach(btn => {
        btn.addEventListener('click', e => {
          e.stopPropagation();
          const input = document.getElementById('url-input');
          if (input) input.value = btn.dataset.url;
          Router.navigate('home');
          haptic('medium');
        });
      });
    } catch {
      list.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load history</div></div>';
    }
  }

  /* ── Archive page ────────────────────────────────────────── */

  async function loadArchive() {
    const list = document.getElementById('archive-list');
    if (!list) return;
    try {
      const res   = await API.getArchive();
      const items = res.archive || [];
      if (!items.length) {
        list.innerHTML = '<div class="empty-state"><div class="empty-icon">📦</div><div class="empty-title">Archive empty</div></div>';
        return;
      }
      list.innerHTML = items.map(item => `
        <div class="archive-item">
          <div class="history-info">
            <div class="history-title">${escapeHTML(item.title || item.id || '—')}</div>
            <div class="archive-id">${escapeHTML(item.id || '')}</div>
            <div class="history-meta">${formatRelativeTime(item.ts)}</div>
          </div>
        </div>
      `).join('');
    } catch {}
  }

  /* ── Favorites page ──────────────────────────────────────── */

  async function loadFavorites() {
    const list = document.getElementById('favorites-list');
    if (!list) return;
    try {
      const res   = await API.getFavorites();
      const items = res.favorites || [];
      if (!items.length) {
        list.innerHTML = '<div class="empty-state"><div class="empty-icon">⭐</div><div class="empty-title">No favorites yet</div></div>';
        return;
      }
      list.innerHTML = items.map(item => `
        <div class="fav-item">
          <img class="history-thumb" src="${escapeHTML(item.thumbnail || '')}" alt="" loading="lazy"
            onerror="this.style.display='none'" />
          <div class="history-info">
            <div class="history-title">${escapeHTML(item.title || item.url || '—')}</div>
            <div class="history-meta">⭐ Saved · ${formatRelativeTime(item.created_at)}</div>
          </div>
          <button class="icon-btn" onclick="MegaDL.API.removeFavorite('${escapeHTML(item.id)}').then(()=>MegaDL.App.loadFavs())" title="Remove">✕</button>
        </div>
      `).join('');
    } catch {}
  }

  /* ── Toast notifications ─────────────────────────────────── */

  function toast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-msg">${escapeHTML(message)}</span>`;
    container.appendChild(t);

    // Auto-remove
    setTimeout(() => {
      t.classList.add('hide');
      setTimeout(() => t.remove(), 400);
    }, duration);

    // Click to dismiss
    t.addEventListener('click', () => {
      t.classList.add('hide');
      setTimeout(() => t.remove(), 400);
    });

    // Log it too
    const level = type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'info';
    Logs.appendLog(message, level);
  }

  /* ── Confirm dialog ──────────────────────────────────────── */

  function confirm(message, callback, title = 'Confirm') {
    MegaDL.App._showConfirm?.(message, title, callback);
  }

  /* ── Expose public API ───────────────────────────────────── */
  return {
    init,
    toast,
    confirm,
    loadDownloads,
    loadHistory,
    loadArchive,
    loadFavs: loadFavorites,
  };
})();

/* ── Boot ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => MegaDL.App.init());
