/**
 * MegaDL — jobs.js
 * Live job tracking: polling, rendering, state management.
 */

MegaDL.Jobs = (() => {
  const { API, Utils, Config } = MegaDL;
  const { formatBytes, formatSpeed, formatDuration, formatETA, formatRelativeTime,
          buildProgressRing, escapeHTML, show, hide, toggle, haptic } = Utils;

  /* ── State ───────────────────────────────────────────────── */
  let jobs        = new Map(); // jobId → jobData
  let pollTimer   = null;
  let eventSource = null;
  let isPaused    = false;
  let useSSE      = true; // prefer SSE, fallback to polling

  /* ── Polling ─────────────────────────────────────────────── */

  function startPolling() {
    stopPolling();
    if (useSSE) _sseConnect();
    _poll();
    pollTimer = setInterval(_poll, Config.jobPollInterval);
  }

  function stopPolling() {
    _sseDisconnect();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  /* ── SSE (Server-Sent Events) ────────────────────────────── */

  function _sseConnect() {
    try {
      const baseUrl = MegaDL.Config.pythonBackendUrl || 'http://localhost:5000';
      eventSource = new EventSource(`${baseUrl}/api/progress`);
      eventSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.jobs) _processJobUpdate(data.jobs);
        } catch {}
      };
      eventSource.onerror = () => {
        _sseDisconnect();
        useSSE = false; // fallback to polling only
      };
    } catch {
      useSSE = false;
    }
  }

  function _sseDisconnect() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  async function _poll() {
    if (isPaused) return;
    try {
      const res = await API.getJobs();
      const list = res.jobs || res || [];
      _processJobUpdate(list);
    } catch { /* silent fail — backend might be starting */ }
  }

  /* ── Process job list from backend ──────────────────────── */

  function _processJobUpdate(list) {
    const newMap = new Map();
    let activeCount = 0;

    for (const job of list) {
      // Flatten video tracking info from options (for HTTP polling path)
      if (job.options && !job.current_video_title) {
        const opts = job.options;
        if (opts._video_title) job.current_video_title = opts._video_title;
        if (opts._video_index) job.current_video_index = opts._video_index;
        if (opts._video_total) job.total_videos = opts._video_total;
      }

      const prev = jobs.get(job.id);

      // Detect transitions
      if (prev && prev.state !== job.state) {
        _onStateChange(job, prev.state);
      }

      newMap.set(job.id, job);
      if (['running', 'queued', 'fetching'].includes(job.state)) activeCount++;
    }

    jobs = newMap;

    // Update badge counts
    _updateBadges(activeCount);

    // Re-render lists
    _renderActiveJobs();
    _renderHomeActivePreview();

    // Check failed links periodically
    checkFailedLinks();
  }

  /* ── State change side effects ───────────────────────────── */

  function _onStateChange(job, prevState) {
    if (job.state === 'done') {
      haptic('success');
      MegaDL.App?.toast(`✅ Done: ${job.title || 'Download'}`, 'success');
      _fireNotification('✅ Download Complete', job.title || 'Download finished');
      // Animate card
      const card = document.querySelector(`[data-job-id="${job.id}"]`);
      if (card) {
        card.classList.add('just-done');
        setTimeout(() => card.classList.remove('just-done'), 600);
      }
    }
    if (job.state === 'error') {
      haptic('error');
      MegaDL.App?.toast(`❌ Failed: ${job.title || 'Download'}`, 'error');
      _fireNotification('❌ Download Failed', job.title || 'Download error');
    }
  }

  /* ── Browser Notifications ───────────────────────────────── */

  function _requestNotifyPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }

  function _fireNotification(title, body) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    try {
      const n = new Notification(title, {
        body: body,
        icon: '/assets/icons/icon-192.png',
        silent: false,
      });
      n.onclick = () => { window.focus(); n.close(); };
      setTimeout(() => n.close(), 6000);
    } catch {}
  }

  /* ── Badge updates ───────────────────────────────────────── */

  function _updateBadges(count) {
    const ids = ['active-badge', 'bnav-active-badge'];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = count;
      el.style.display = count > 0 ? 'flex' : 'none';
    });
  }

  /* ── Failed Links ────────────────────────────────────────── */

  async function checkFailedLinks() {
    const navItem = document.getElementById('nav-failed');
    const badge = document.getElementById('failed-badge');
    try {
      const res = await API.getFailedLinks();
      const failed = res.failed_links || [];
      const count = failed.length;
      if (navItem) navItem.style.display = count > 0 ? '' : 'none';
      if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
      }
      // Render if page is active
      const page = document.getElementById('page-failed');
      if (page && page.classList.contains('active')) {
        _renderFailedLinks(failed);
      }
    } catch {}
  }

  function _renderFailedLinks(failed) {
    const container = document.getElementById('failed-links-container');
    if (!container) return;
    if (!failed || !failed.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><div class="empty-title">No failed links</div><div class="empty-subtitle">All downloads completed successfully</div></div>';
      document.getElementById('nav-failed').style.display = 'none';
      return;
    }
    container.innerHTML = '<div class="failed-links-list" style="display:flex;flex-direction:column;gap:8px">' +
      failed.map(f => `
        <div class="glass-card" style="padding:12px;display:flex;flex-direction:column;gap:4px">
          <div style="font-size:.8rem;word-break:break-all">${escapeHTML(f.url || f.title || '—')}</div>
          ${f.error ? `<div style="font-size:.75rem;color:var(--error)">❌ ${escapeHTML(f.error)}</div>` : ''}
          ${f.job_id ? `<div style="font-size:.65rem;color:var(--text-muted)">Job: ${escapeHTML(f.job_id)}</div>` : ''}
        </div>
      `).join('') + '</div>';
  }

  async function clearFailedLinks() {
    try {
      await API.clearFailedLinks();
      checkFailedLinks();
      MegaDL.App?.toast('Failed links cleared', 'success');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    }
  }

  async function retryFailedLinks() {
    try {
      const res = await API.getFailedLinks();
      const failed = res.failed_links || [];
      const urls = failed.map(f => f.url).filter(Boolean);
      if (!urls.length) {
        MegaDL.App?.toast('No failed links to retry', 'info');
        return;
      }
      await API.startBatch(urls);
      await clearFailedLinks();
      MegaDL.App?.toast(`🔄 Retrying ${urls.length} failed links`, 'success');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    }
  }

  /* ── Render: Active Jobs page ────────────────────────────── */

  function _renderActiveJobs() {
    const container = document.getElementById('active-jobs-list');
    if (!container) return;

    const activeJobs = [...jobs.values()].filter(j =>
      ['running', 'queued', 'fetching', 'paused'].includes(j.state)
    );

    if (activeJobs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⏳</div>
          <div class="empty-title">No active jobs</div>
          <div class="empty-subtitle">Downloads in progress appear here</div>
        </div>`;
      return;
    }

    _reconcileJobCards(container, activeJobs);
  }

  /* ── Render: Home page preview (top 3 active) ────────────── */

  function _renderHomeActivePreview() {
    const container = document.getElementById('home-active-jobs');
    const emptyState = document.getElementById('home-empty-state');
    if (!container) return;

    const active = [...jobs.values()]
      .filter(j => ['running', 'queued', 'fetching', 'paused'].includes(j.state))
      .slice(0, 3);

    if (emptyState) emptyState.style.display = active.length ? 'none' : 'block';

    // Remove old preview cards
    container.querySelectorAll('.job-card').forEach(c => c.remove());

    // Add new preview cards
    active.forEach(job => {
      const card = _buildJobCard(job, true);
      container.appendChild(card);
    });
  }

  /* ── DOM Reconciliation: update existing cards in-place ──── */

  function _reconcileJobCards(container, jobList) {
    const existingCards = new Map(
      [...container.querySelectorAll('[data-job-id]')]
        .map(el => [el.dataset.jobId, el])
    );

    const rendered = new Set();

    jobList.forEach((job, index) => {
      rendered.add(job.id);
      const existing = existingCards.get(job.id);

      if (existing) {
        // Update in-place (fast path)
        _updateJobCard(existing, job);
      } else {
        // Insert new card
        const card = _buildJobCard(job);
        // Insert at correct position
        const cards = [...container.querySelectorAll('[data-job-id]')];
        if (index < cards.length) {
          container.insertBefore(card, cards[index]);
        } else {
          container.appendChild(card);
        }
      }
    });

    // Remove stale cards
    existingCards.forEach((el, id) => {
      if (!rendered.has(id)) el.remove();
    });

    // Show/hide empty state
    const emptyEl = container.querySelector('.empty-state');
    if (emptyEl) emptyEl.style.display = jobList.length ? 'none' : 'block';
  }

  /* ── Build job card HTML ─────────────────────────────────── */

  function _buildJobCard(job, compact = false) {
    const card = document.createElement('div');
    card.className = `job-card ${job.state}`;
    card.dataset.jobId = job.id;
    card.innerHTML = _jobCardHTML(job, compact);
    _attachJobCardListeners(card, job);
    return card;
  }

  function _jobCardHTML(job, compact) {
    const pct     = Math.min(100, Math.max(0, job.progress || 0));
    const speed   = formatSpeed(job.speed || 0);
    const eta     = formatETA(job.eta);
    const size    = job.total_bytes ? formatBytes(job.total_bytes) : '—';
    const title   = escapeHTML(job.title || job.url || 'Downloading...');
    const url     = escapeHTML(job.url || '');
    const thumb   = job.thumbnail
      ? `<img class="job-thumb" src="${escapeHTML(job.thumbnail)}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : `<div class="job-thumb-placeholder">${MegaDL.Utils.getSiteIcon(job.url || '')}</div>`;

    const stateLabel = {
      queued:   '⏳ Queued',
      fetching: '🔍 Fetching',
      running:  '⬇️ Downloading',
      paused:   '⏸ Paused',
      done:     '✅ Done',
      error:    '❌ Failed',
      cancelled:'✕ Cancelled',
    }[job.state] || job.state;

    const actions = _jobActionsHTML(job);

    const progressFillClass = job.state === 'done' ? 'done' : job.state === 'error' ? 'error' : '';

    // Video tracking info for playlists
    let videoInfo = '';
    if (job.current_video_title) {
      const vt = escapeHTML(job.current_video_title);
      if (job.total_videos > 1) {
        videoInfo = `<div class="job-video-info">🎬 ${vt} <span class="job-video-count">(${job.current_video_index}/${job.total_videos})</span></div>`;
      } else {
        videoInfo = `<div class="job-video-info">🎬 ${vt}</div>`;
      }
    } else if (job.current_video_index > 0 && job.total_videos > 1) {
      videoInfo = `<div class="job-video-info">📋 Video ${job.current_video_index}/${job.total_videos}</div>`;
    }

    return `
      <div class="job-header">
        ${thumb}
        <div class="job-info">
          <div class="job-title" title="${title}">${title}</div>
          ${videoInfo}
          <div class="job-url">${url}</div>
          <div class="job-state ${job.state}">${stateLabel}</div>
        </div>
        ${buildProgressRing(pct, 36)}
      </div>
      <div class="job-progress-section">
        <div class="job-progress-bar">
          <div class="job-progress-fill ${progressFillClass}" style="width:${pct}%"></div>
        </div>
        <div class="job-progress-info">
          <span>${pct.toFixed(1)}% · ${size}</span>
          ${job.state === 'running' ? `
            <span><span class="job-speed">${speed}</span> · ETA ${eta}</span>
            <span>${job.fragment ? `Frag ${job.fragment}` : ''}</span>
          ` : ''}
        </div>
      </div>
      ${!compact ? `<div class="job-actions">${actions}</div>` : ''}
    `;
  }

  function _jobActionsHTML(job) {
    const btns = [];

    if (job.state === 'running') {
      btns.push(`<button class="job-action-btn" data-action="pause">⏸ Pause</button>`);
    }
    if (job.state === 'paused') {
      btns.push(`<button class="job-action-btn" data-action="resume">▶ Resume</button>`);
    }
    if (['running', 'queued', 'fetching', 'paused'].includes(job.state)) {
      btns.push(`<button class="job-action-btn danger" data-action="cancel">✕ Cancel</button>`);
    }
    if (job.state === 'error') {
      btns.push(`<button class="job-action-btn" data-action="retry">🔄 Retry</button>`);
    }
    if (job.state === 'done') {
      btns.push(`<button class="job-action-btn" data-action="open">📂 Open</button>`);
      btns.push(`<button class="job-action-btn" data-action="fav">⭐ Fav</button>`);
    }
    btns.push(`<button class="job-action-btn" data-action="logs">📄 Logs</button>`);
    if (['done', 'error', 'cancelled'].includes(job.state)) {
      btns.push(`<button class="job-action-btn danger" data-action="delete">🗑 Delete</button>`);
    }

    return btns.join('');
  }

  /* ── Update existing card without full rebuild ───────────── */

  function _updateJobCard(card, job) {
    // Update state class
    card.className = `job-card ${job.state}`;

    // Update progress bar
    const pct  = Math.min(100, Math.max(0, job.progress || 0));
    const fill = card.querySelector('.job-progress-fill');
    if (fill) {
      fill.style.width = `${pct}%`;
      fill.className = `job-progress-fill ${job.state === 'done' ? 'done' : job.state === 'error' ? 'error' : ''}`;
    }

    // Update progress text
    const info = card.querySelector('.job-progress-info');
    if (info) {
      const speed = formatSpeed(job.speed || 0);
      const eta   = formatETA(job.eta);
      const size  = job.total_bytes ? formatBytes(job.total_bytes) : '—';
      info.innerHTML = `
        <span>${pct.toFixed(1)}% · ${size}</span>
        ${job.state === 'running' ? `
          <span><span class="job-speed">${speed}</span> · ETA ${eta}</span>
          <span>${job.fragment ? `Frag ${job.fragment}` : ''}</span>
        ` : ''}
      `;
    }

    // Update state badge
    const stateBadge = card.querySelector('.job-state');
    if (stateBadge) {
      stateBadge.className = `job-state ${job.state}`;
      const stateLabel = {
        queued: '⏳ Queued', fetching: '🔍 Fetching', running: '⬇️ Downloading',
        paused: '⏸ Paused', done: '✅ Done', error: '❌ Failed', cancelled: '✕ Cancelled',
      }[job.state] || job.state;
      stateBadge.textContent = stateLabel;
    }

    // Update video tracking info
    const videoInfoEl = card.querySelector('.job-video-info');
    if (videoInfoEl || job.current_video_title) {
      if (videoInfoEl) {
        // Update existing
        if (job.current_video_title) {
          const vt = escapeHTML(job.current_video_title);
          if (job.total_videos > 1) {
            videoInfoEl.innerHTML = `🎬 ${vt} <span class="job-video-count">(${job.current_video_index}/${job.total_videos})</span>`;
          } else {
            videoInfoEl.textContent = `🎬 ${vt}`;
          }
        } else if (job.current_video_index > 0 && job.total_videos > 1) {
          videoInfoEl.innerHTML = `📋 Video ${job.current_video_index}/${job.total_videos}`;
        }
      } else {
        // Create video info element
        const jobInfo = card.querySelector('.job-info');
        if (jobInfo) {
          const vt = escapeHTML(job.current_video_title || '');
          let newVideoEl = document.createElement('div');
          newVideoEl.className = 'job-video-info';
          if (job.total_videos > 1) {
            newVideoEl.innerHTML = `🎬 ${vt} <span class="job-video-count">(${job.current_video_index}/${job.total_videos})</span>`;
          } else {
            newVideoEl.textContent = `🎬 ${vt}`;
          }
          jobInfo.insertBefore(newVideoEl, card.querySelector('.job-url'));
        }
      }
    }

    // Update progress ring
    const ringWrap = card.querySelector('.progress-ring');
    if (ringWrap) ringWrap.outerHTML = buildProgressRing(pct, 36);

    // Update actions if state changed
    const actionsDiv = card.querySelector('.job-actions');
    if (actionsDiv) actionsDiv.innerHTML = _jobActionsHTML(job);

    // Re-attach listeners (after DOM update)
    card.querySelectorAll('[data-action]').forEach(btn => {
      btn.onclick = null; // remove old
    });
    _attachJobCardListeners(card, job);
  }

  /* ── Attach event listeners to job card buttons ──────────── */

  function _attachJobCardListeners(card, job) {
    card.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const action = btn.dataset.action;
        haptic('light');
        await _handleJobAction(job.id, action);
      });
    });

    // Click card to see details
    card.addEventListener('click', e => {
      if (e.target.closest('[data-action]')) return;
      showJobDetail(job.id);
    });
  }

  /* ── Handle job button actions ───────────────────────────── */

  async function _handleJobAction(jobId, action) {
    try {
      switch (action) {
        case 'pause':   await API.pauseJob(jobId);  break;
        case 'resume':  await API.resumeJob(jobId); break;
        case 'cancel':  await API.cancelJob(jobId); break;
        case 'retry':   await API.retryJob(jobId);  break;
        case 'delete':  await API.deleteJob(jobId); jobs.delete(jobId); _poll(); break;
        case 'fav':     await API.addFavorite(jobId); MegaDL.App?.toast('⭐ Added to favorites', 'success'); break;
        case 'open': {
          const url = API.getDownloadUrl(jobId);
          window.open(url, '_blank');
          break;
        }
        case 'logs': {
          await showJobDetail(jobId);
          break;
        }
      }
      // Force an immediate re-poll
      await _poll();
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    }
  }

  /* ── Job Detail Modal ────────────────────────────────────── */

  async function showJobDetail(jobId) {
    const modal = document.getElementById('modal-job-detail');
    const body  = document.getElementById('modal-job-body');
    const title = document.getElementById('modal-job-title');
    if (!modal || !body) return;

    const job = jobs.get(jobId);
    if (!job) return;

    if (title) title.textContent = job.title || 'Download Details';

    // Fetch logs
    let logs = '';
    try {
      const logRes = await API.getJobLogs(jobId);
      logs = logRes.logs || logRes || '';
    } catch {}

    // Fetch failed links
    let failedHTML = '';
    try {
      const flRes = await API.getFailedLinks(jobId);
      const fl = flRes.failed_links || [];
      if (fl.length > 0) {
        failedHTML = fl.map(f => `
          <div class="info-row">
            <span class="info-key" style="color:var(--error)">❌</span>
            <span class="info-val" style="font-size:0.78rem">${escapeHTML(f.url)}<br><span style="color:var(--error)">${escapeHTML(f.error)}</span></span>
          </div>
        `).join('');
      }
    } catch {}

    const pct  = Math.min(100, Math.max(0, job.progress || 0));
    const size = job.total_bytes ? formatBytes(job.total_bytes) : '—';

    body.innerHTML = `
      <div class="job-detail-section">
        <div class="job-detail-title">Info</div>
        <div class="info-row"><span class="info-key">URL</span><span class="info-val">${escapeHTML(job.url || '—')}</span></div>
        <div class="info-row"><span class="info-key">State</span><span class="info-val">${job.state}</span></div>
        <div class="info-row"><span class="info-key">Progress</span><span class="info-val">${pct.toFixed(1)}%</span></div>
        <div class="info-row"><span class="info-key">Size</span><span class="info-val">${size}</span></div>
        <div class="info-row"><span class="info-key">Speed</span><span class="info-val">${formatSpeed(job.speed || 0)}</span></div>
        <div class="info-row"><span class="info-key">ETA</span><span class="info-val">${formatETA(job.eta)}</span></div>
        <div class="info-row"><span class="info-key">Job ID</span><span class="info-val">${escapeHTML(job.id)}</span></div>
        ${job.error ? `<div class="info-row"><span class="info-key">Error</span><span class="info-val" style="color:var(--error)">${escapeHTML(job.error)}</span></div>` : ''}
      </div>
      ${failedHTML ? `
      <div class="job-detail-section">
        <div class="job-detail-title">❌ Failed Links (${document.querySelectorAll('.info-row .info-key:contains(\"❌\")').length || ''})</div>
        ${failedHTML}
      </div>` : ''}
      <div class="job-detail-section">
        <div class="job-detail-title">Live Log</div>
        <div class="job-detail-log" id="job-detail-log-content">${escapeHTML(logs || 'No logs yet...')}</div>
      </div>
      <div class="action-row">
        ${job.state === 'running' ? `<button class="btn btn-secondary btn-sm" onclick="MegaDL.Jobs._handleJobAction('${job.id}','pause')">⏸ Pause</button>` : ''}
        ${job.state === 'paused'  ? `<button class="btn btn-primary btn-sm"   onclick="MegaDL.Jobs._handleJobAction('${job.id}','resume')">▶ Resume</button>` : ''}
        ${job.state === 'error'   ? `<button class="btn btn-primary btn-sm"   onclick="MegaDL.Jobs._handleJobAction('${job.id}','retry')">🔄 Retry</button>` : ''}
        ${job.state === 'done'    ? `<button class="btn btn-primary btn-sm"   onclick="window.open('${API.getDownloadUrl(job.id)}','_blank')">📂 Open File</button>` : ''}
      </div>
    `;

    modal.style.display = 'flex';

    // Auto-scroll log
    const logEl = document.getElementById('job-detail-log-content');
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
  }

  /* ── Bulk actions ────────────────────────────────────────── */

  async function pauseAll()  { try { await API.pauseAll();  await _poll(); } catch {} }
  async function resumeAll() { try { await API.resumeAll(); await _poll(); } catch {} }
  async function cancelAll() { try { await API.cancelAll(); await _poll(); } catch {} }

  /* ── Getters ─────────────────────────────────────────────── */

  function getAll()    { return [...jobs.values()]; }
  function getActive() { return [...jobs.values()].filter(j => ['running','queued','fetching'].includes(j.state)); }
  function getDone()   { return [...jobs.values()].filter(j => j.state === 'done'); }
  function get(id)     { return jobs.get(id); }

  /* ── Init ────────────────────────────────────────────────── */
  function init() {
    _requestNotifyPermission();
  }

  /* ── Expose ──────────────────────────────────────────────── */
  return {
    init, startPolling, stopPolling,
    pauseAll, resumeAll, cancelAll,
    showJobDetail,
    getAll, getActive, getDone, get,
    _handleJobAction, // exposed for inline onclick
    forceRefresh: _poll,
    checkFailedLinks, clearFailedLinks, retryFailedLinks,
  };
})();
