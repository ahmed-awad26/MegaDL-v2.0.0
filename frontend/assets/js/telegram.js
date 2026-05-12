/**
 * MegaDL — telegram.js
 * Telegram integration: login wizard, dialog browser, bulk download.
 */

MegaDL.Telegram = (() => {
  const { API, Utils, Router } = MegaDL;
  const { escapeHTML, show, hide, haptic, formatBytes } = Utils;

  /* ── State ───────────────────────────────────────────────── */
  let currentStep = 'login';   // login | dialogs | messages
  let dialogs = [];
  let messages = [];
  let selectedDialog = null;
  let selectedMessages = new Set();
  let isAuthorized = false;
  let loginPhone = '';
  let retryAfter = 0; // seconds to wait before resend

  /* ── DOM refs cache ──────────────────────────────────────── */
  const $ = id => document.getElementById(id);

  /* ── Init ────────────────────────────────────────────────── */
  function init() {
    _wireLoginEvents();
    _wireDialogEvents();
    _wireMessageEvents();
    _wireBotPoolEvents();
    _wireScanEvents();
    _wireBotScoreEvents();
  }

  /* ── Entry point: called when Telegram page is shown ─────── */
  async function onEnter() {
    _checkStatus();
    refreshBotPool();
  }

  async function _checkStatus() {
    const statusEl = $('tg-status');
    if (statusEl) statusEl.textContent = 'Checking...';

    try {
      const res = await API.tgStatus();
      isAuthorized = res.authorized;

      if (res.missing_dep) {
        _showStep('login');
        if (statusEl) {
          statusEl.innerHTML = '<span style="color:var(--warning)">⚠️ Telethon not installed.</span>';
        }
        const installBtn = document.createElement('button');
        installBtn.className = 'btn btn-primary full-width';
        installBtn.textContent = '⬇ Install Telethon Now';
        installBtn.style.marginTop = '12px';
        installBtn.onclick = async function() {
          this.disabled = true;
          this.textContent = 'Installing...';
          try {
            const res = await API.installDependency('telethon');
            if (res.success) {
              MegaDL.App?.toast('✅ Telethon installed!', 'success');
              setTimeout(_checkStatus, 1000);
            } else {
              MegaDL.App?.toast('❌ Install failed. Run: pip install telethon cryptg', 'error');
            }
          } catch {
            MegaDL.App?.toast('❌ Install error. Run: pip install telethon cryptg', 'error');
          }
          this.remove();
        };
        if (statusEl) statusEl.after(installBtn);
        return;
      }

      if (res.error) {
        _showStep('login');
        if (statusEl) {
          statusEl.innerHTML = `<span style="color:var(--warning)">⚠️ ${escapeHTML(res.error)}</span>`;
        }
        return;
      }

      if (isAuthorized) {
        _showStep('dialogs');
        if (res.user) {
          const user = res.user;
          if (statusEl) {
            statusEl.innerHTML = `✅ Logged in as <strong>${escapeHTML(user.first_name || user.username || user.phone || 'User')}</strong>`;
          }
        }
        await loadDialogs();
      } else {
        _showStep('login');
        if (statusEl) statusEl.textContent = 'Not logged in. Enter your phone number below.';
      }
    } catch (err) {
      _showStep('login');
      if (statusEl) statusEl.textContent = `⚠️ ${err.message || 'Could not reach backend'}`;
      const retryBtn = document.createElement('button');
      retryBtn.className = 'btn btn-sm btn-secondary';
      retryBtn.textContent = '🔄 Retry';
      retryBtn.style.margin = '8px auto';
      retryBtn.onclick = _checkStatus;
      if (statusEl) statusEl.after(retryBtn);
    }
  }

  /* ── Step management ─────────────────────────────────────── */
  function _showStep(step) {
    ['tg-login-step', 'tg-dialogs-step', 'tg-messages-step'].forEach(id => hide(id));
    currentStep = step;
    if (step === 'login')    show('tg-login-step', 'block');
    if (step === 'dialogs')  show('tg-dialogs-step', 'block');
    if (step === 'messages') show('tg-messages-step', 'block');
    const logoutWrap = $('tg-logout-wrap');
    if (logoutWrap) logoutWrap.style.display = isAuthorized ? 'block' : 'none';
  }

  /* ══════════════════════════════════════════════════════════
     LOGIN WIZARD
     ══════════════════════════════════════════════════════════ */

  function _wireLoginEvents() {
    $('tg-send-code-btn')?.addEventListener('click', sendCode);
    $('tg-verify-btn')?.addEventListener('click', verifyCode);
    $('tg-password-btn')?.addEventListener('click', sendPassword);
    $('tg-logout-btn')?.addEventListener('click', doLogout);
    $('tg-resend-code-btn')?.addEventListener('click', sendCode);
    $('tg-phone-input')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendCode();
    });
    $('tg-code-input')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') verifyCode();
    });
    $('tg-password-input')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendPassword();
    });
  }

  function _showLoginForm(form) {
    ['tg-form-phone', 'tg-form-code', 'tg-form-password'].forEach(id => hide(id));
    show(form, 'block');
  }

  async function sendCode() {
    const phone = $('tg-phone-input')?.value?.trim();
    if (!phone) { MegaDL.App?.toast('Enter phone number', 'warning'); return; }

    const btn = $('tg-send-code-btn');
    _setBtnLoading(btn, true, 'Sending...');

    // Hide resend button
    const resendBtn = $('tg-resend-code-btn');
    if (resendBtn) resendBtn.style.display = 'none';

    try {
      const res = await API.tgSendCode(phone);
      if (res.error) {
        // Handle specific error codes
        if (res.code === 'ALL_OPTIONS_USED') {
          MegaDL.App?.toast('❌ All verification methods used. Wait 10 minutes.', 'error');
          _showLoginForm('tg-form-phone');
          if (resendBtn) {
            resendBtn.textContent = '⏳ Wait 10 min before retry';
            resendBtn.disabled = true;
            resendBtn.style.display = 'block';
            setTimeout(() => {
              resendBtn.textContent = '🔄 Resend Code';
              resendBtn.disabled = false;
            }, 60000); // Enable after 1 min as basic guidance
          }
          return;
        }
        if (res.code === 'FLOOD_WAIT') {
          MegaDL.App?.toast('❌ Too many attempts. Wait a few minutes.', 'error');
          _showLoginForm('tg-form-phone');
          return;
        }
        if (res.code === 'INVALID_PHONE') {
          MegaDL.App?.toast('❌ Invalid phone format. Use +1234567890', 'error');
          return;
        }
        MegaDL.App?.toast(`❌ ${res.error}`, 'error');
        return;
      }
      if (res.authorized) {
        isAuthorized = true;
        _showStep('dialogs');
        await loadDialogs();
        return;
      }
      loginPhone = phone;
      _showLoginForm('tg-form-code');
      const _cd = $('tg-code-display');
      if (_cd) {
        _cd.textContent = `Code sent to ${phone}`;
        _cd.className = 'tg-code-info';
      }
      $('tg-code-input')?.focus();
      // Show resend button
      if (resendBtn) resendBtn.style.display = 'block';
      haptic('light');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      _setBtnLoading(btn, false, 'Send Code');
    }
  }

  async function verifyCode() {
    const code = $('tg-code-input')?.value?.trim();
    if (!code) { MegaDL.App?.toast('Enter the code', 'warning'); return; }

    const btn = $('tg-verify-btn');
    _setBtnLoading(btn, true, 'Verifying...');

    try {
      const res = await API.tgSignIn(loginPhone, code);
      if (res.need_password) {
        _showLoginForm('tg-form-password');
        $('tg-password-input')?.focus();
        return;
      }
      if (res.error) {
        // Handle phone code invalid/expired
        const errLower = (res.error || '').toLowerCase();
        if (errLower.includes('phone code') || errLower.includes('invalid code') || errLower.includes('expired')) {
          MegaDL.App?.toast('❌ Invalid or expired code. Request a new one.', 'error');
          const cd = $('tg-code-display');
          if (cd) {
            cd.textContent = '❌ Code invalid. Click "Resend Code" to get a new one.';
            cd.className = 'tg-code-info tg-error';
          }
          return;
        }
        MegaDL.App?.toast(`❌ ${res.error}`, 'error');
        return;
      }
      if (res.authorized) {
        isAuthorized = true;
        MegaDL.App?.toast('✅ Telegram logged in!', 'success');
        _showStep('dialogs');
        await loadDialogs();
      }
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      _setBtnLoading(btn, false, 'Verify');
    }
  }

  async function sendPassword() {
    const password = $('tg-password-input')?.value;
    if (!password) { MegaDL.App?.toast('Enter 2FA password', 'warning'); return; }

    const btn = $('tg-password-btn');
    _setBtnLoading(btn, true, 'Signing in...');

    try {
      const res = await API.tgSignInPassword(password);
      if (res.error) {
        MegaDL.App?.toast(`❌ ${res.error}`, 'error');
        return;
      }
      if (res.authorized) {
        isAuthorized = true;
        MegaDL.App?.toast('✅ Telegram logged in!', 'success');
        _showStep('dialogs');
        await loadDialogs();
      }
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      _setBtnLoading(btn, false, 'Sign In');
    }
  }

  async function doLogout() {
    try {
      await API.tgLogout();
      isAuthorized = false;
      dialogs = [];
      messages = [];
      selectedDialog = null;
      selectedMessages.clear();
      _showStep('login');
      _showLoginForm('tg-form-phone');
      MegaDL.App?.toast('Logged out', 'info');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    }
  }

  /* ══════════════════════════════════════════════════════════
     DIALOG BROWSER
     ══════════════════════════════════════════════════════════ */

  function _wireDialogEvents() {
    $('tg-refresh-dialogs')?.addEventListener('click', loadDialogs);
    $('tg-dialog-search')?.addEventListener('input', Utils.debounce(_filterDialogs, 300));
  }

  async function loadDialogs() {
    const list = $('tg-dialog-list');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div><div class="empty-title">Loading dialogs...</div></div>';

    try {
      const res = await API.tgDialogs();
      dialogs = res.dialogs || [];
      _renderDialogs(dialogs);
    } catch (err) {
      list.innerHTML = `<div class="empty-state"><div class="empty-title">❌ ${escapeHTML(err.message)}</div></div>`;
    }
  }

  function _renderDialogs(dlgList) {
    const list = $('tg-dialog-list');
    if (!list) return;

    if (!dlgList.length) {
      list.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">No dialogs found</div></div>';
      return;
    }

    list.innerHTML = dlgList.map(d => {
      const icon = d.type === 'channel' ? '📢' : d.type === 'group' ? '👥' : '💬';
      const unread = d.unread_count > 0 ? `<span class="tg-unread-badge">${d.unread_count}</span>` : '';
      return `
        <div class="tg-dialog-item" data-dialog-id="${d.id}" data-dialog-name="${escapeHTML(d.name)}">
          <div class="tg-dialog-icon">${icon}</div>
          <div class="tg-dialog-info">
            <div class="tg-dialog-name">${escapeHTML(d.name || 'Unknown')}</div>
            <div class="tg-dialog-preview">${escapeHTML(d.message || d.type) || ''}</div>
          </div>
          ${unread}
          <div class="tg-dialog-type chip chip-muted">${d.type}</div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.tg-dialog-item').forEach(el => {
      el.addEventListener('click', () => openDialog(el.dataset.dialogId, el.dataset.dialogName));
    });

    const _dc = $('tg-dialog-count'); if (_dc) _dc.textContent = `${dlgList.length} dialogs`;
  }

  function _filterDialogs() {
    const q = ($('tg-dialog-search')?.value || '').toLowerCase();
    _renderDialogs(dialogs.filter(d => (d.name || '').toLowerCase().includes(q)));
  }

  async function openDialog(dialogId, dialogName) {
    selectedDialog = { id: parseInt(dialogId), name: dialogName };
    selectedMessages.clear();
    _showStep('messages');

    const header = $('tg-msg-header');
    if (header) header.innerHTML = `
      <button class="btn btn-sm btn-secondary" id="tg-back-to-dialogs">← Back</button>
      <span style="font-weight:600;margin-left:12px">${escapeHTML(dialogName)}</span>
    `;
    $('tg-back-to-dialogs')?.addEventListener('click', () => {
      _showStep('dialogs');
    });

    await loadMessages();
  }

  /* ══════════════════════════════════════════════════════════
     MESSAGE BROWSER
     ══════════════════════════════════════════════════════════ */

  function _wireMessageEvents() {
    $('tg-msg-download-btn')?.addEventListener('click', downloadSelected);
    $('tg-msg-select-all')?.addEventListener('change', e => {
      const checked = e.target.checked;
      selectedMessages.clear();
      if (checked) messages.forEach(m => selectedMessages.add(m.id));
      _renderMessages(messages);
      _updateMsgActions();
    });
    $('tg-msg-media-only')?.addEventListener('change', () => {
      _renderMessages(messages);
    });
    $('tg-msg-mode')?.addEventListener('change', _updateMsgActions);
  }

  async function loadMessages() {
    if (!selectedDialog) return;

    const list = $('tg-msg-list');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div><div class="empty-title">Loading messages...</div></div>';

    try {
      const mediaOnly = ($('tg-msg-media-only')?.checked) ? '1' : '0';
      const res = await API.tgMessages(selectedDialog.id, 100, 0, mediaOnly);
      messages = res.messages || [];
      _renderMessages(messages);
      _updateMsgActions();
    } catch (err) {
      list.innerHTML = `<div class="empty-state"><div class="empty-title">❌ ${escapeHTML(err.message)}</div></div>`;
    }
  }

  function _renderMessages(msgList) {
    const list = $('tg-msg-list');
    if (!list) return;

    const mediaOnly = $('tg-msg-media-only')?.checked;

    let filtered = msgList;
    if (mediaOnly) filtered = msgList.filter(m => m.has_media);

    if (!filtered.length) {
      list.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">No messages found</div></div>';
      return;
    }

    const mediaIcons = {
      photo: '🖼️', video: '🎬', audio: '🎵', document: '📄',
      webpage: '🔗', poll: '📊', text: '💬',
    };

    list.innerHTML = filtered.map(m => {
      const checked = selectedMessages.has(m.id) ? 'checked' : '';
      const icon = mediaIcons[m.media_type] || '📄';
      return `
        <div class="tg-msg-item ${checked}" data-msg-id="${m.id}">
          <label class="tg-msg-check">
            <input type="checkbox" ${checked} data-msg-id="${m.id}" />
          </label>
          <div class="tg-msg-icon">${icon}</div>
          <div class="tg-msg-info">
            <div class="tg-msg-text">${escapeHTML(m.text || m.file_name || '(no text)')}</div>
            <div class="tg-msg-meta">
              ${m.media_type} · ${m.size ? formatBytes(m.size) : '—'} · ${m.date ? new Date(m.date).toLocaleString() : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.tg-msg-item').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.closest('.tg-msg-check input')) return;
        const cb = el.querySelector('input[type="checkbox"]');
        if (cb) {
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event('change'));
        }
      });
    });

    list.querySelectorAll('.tg-msg-check input').forEach(cb => {
      cb.addEventListener('change', () => {
        const mid = parseInt(cb.dataset.msgId);
        if (cb.checked) selectedMessages.add(mid);
        else selectedMessages.delete(mid);
        cb.closest('.tg-msg-item')?.classList.toggle('checked', cb.checked);
        _updateMsgActions();
      });
    });

    const _mc = $('tg-msg-count'); if (_mc) _mc.textContent = `${filtered.length} messages (${selectedMessages.size} selected)`;
  }

  function _updateMsgActions() {
    const count = selectedMessages.size;
    const btn = $('tg-msg-download-btn');
    if (btn) {
      btn.disabled = count === 0;
      btn.innerHTML = count > 0
        ? `<span>⬇️ Download ${count} file${count > 1 ? 's' : ''}</span>`
        : `<span>⬇️ Download</span>`;
    }

    const selectAll = $('tg-msg-select-all');
    if (selectAll) {
      const visibleMsgs = [...document.querySelectorAll('.tg-msg-item')].length;
      selectAll.checked = count > 0 && count >= visibleMsgs;
    }
  }

  /* ══════════════════════════════════════════════════════════
     BOT POOL MANAGER
     ══════════════════════════════════════════════════════════ */

  function _wireBotPoolEvents() {
    $('tg-bot-pool-add-btn')?.addEventListener('click', addBotToPool);
    $('tg-bot-pool-refresh-btn')?.addEventListener('click', refreshBotPool);
  }

  async function addBotToPool() {
    const input = $('tg-bot-pool-input');
    const token = input?.value?.trim();
    if (!token) { MegaDL.App?.toast('Enter a bot token', 'warning'); return; }

    const btn = $('tg-bot-pool-add-btn');
    btn.disabled = true;
    btn.textContent = 'Adding...';

    try {
      const res = await API.tgBotPoolAdd(token);
      if (res.ok) {
        MegaDL.App?.toast('✅ Bot added to pool', 'success');
        input.value = '';
        _renderBotPool(res.pool || []);
      } else {
        MegaDL.App?.toast(`❌ ${res.error || 'Failed to add bot'}`, 'error');
      }
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Add';
    }
  }

  function _renderBotPool(pool) {
    const list = $('tg-bot-pool-list');
    if (!list) return;

    if (!pool || pool.length === 0) {
      list.innerHTML = '<div class="empty-state sm"><div class="empty-subtitle">No bots in pool. Add one above.</div></div>';
      return;
    }

    list.innerHTML = pool.map((token, i) => `
      <div class="setting-item" style="border-bottom:1px solid var(--border);padding:6px 0">
        <span style="font-family:monospace;font-size:.8rem">${escapeHTML(token)}</span>
        <button class="btn btn-sm btn-danger" data-bot-index="${i}" data-bot-token="${encodeURIComponent(token)}" style="margin-left:auto">✕</button>
      </div>
    `).join('');

    list.querySelectorAll('button[data-bot-token]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const tokenRaw = btn.dataset.botToken;
        if (!tokenRaw) return;
        const token = decodeURIComponent(tokenRaw);
        try {
          const res = await API.tgBotPoolRemove(token);
          if (res.ok) {
            MegaDL.App?.toast('Bot removed', 'info');
            _renderBotPool(res.pool || []);
          }
        } catch (err) {
          MegaDL.App?.toast(`❌ ${err.message}`, 'error');
        }
      });
    });
  }

  async function refreshBotPool() {
    const statusEl = $('tg-bot-pool-status');
    if (statusEl) statusEl.textContent = 'Refreshing...';
    try {
      const [listRes, statusRes] = await Promise.all([
        API.tgBotPoolList(),
        API.tgBotPoolStatus(),
      ]);
      _renderBotPool(listRes.pool || []);
      if (statusRes && statusRes.bots) {
        const okCount = statusRes.bots.filter(b => b.ok).length;
        const total = statusRes.bots.length;
        if (statusEl) statusEl.textContent = `${okCount}/${total} bots online`;
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = `Error: ${err.message}`;
    }
  }

  /* ══════════════════════════════════════════════════════════
     DOWNLOAD
     ══════════════════════════════════════════════════════════ */

  /* ── Media Scanning ─────────────────────────────────────── */
  function _wireScanEvents() {
    $('tg-scan-btn')?.addEventListener('click', scanMedia);
  }

  async function scanMedia() {
    if (!selectedDialog) { MegaDL.App?.toast('Select a dialog first', 'warning'); return; }

    const btn = $('tg-scan-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner sm"></span> Scanning...';

    const resultsEl = $('tg-scan-results');
    if (resultsEl) {
      resultsEl.style.display = 'block';
      resultsEl.innerHTML = '<div class="empty-state sm"><div class="loading-spinner"></div><div class="empty-title">Scanning media...</div></div>';
    }

    // Gather selected media types
    const mediaTypes = [];
    document.querySelectorAll('.tg-media-filter:checked').forEach(cb => mediaTypes.push(cb.value));
    const limit = parseInt($('tg-media-limit')?.value || '100', 10);

    try {
      const limitPerType = {};
      mediaTypes.forEach(t => { limitPerType[t] = limit; });

      const res = await API.tgScanChat(selectedDialog.id, mediaTypes, limitPerType);
      if (res.ok && resultsEl) {
        resultsEl.innerHTML = _renderScanResults(res);
        MegaDL.App?.toast(`✅ Scan complete: ${res.total_count} files found`, 'success');
      } else if (resultsEl) {
        resultsEl.innerHTML = `<div class="empty-state sm"><div class="empty-title">❌ ${escapeHTML(res.error || 'Scan failed')}</div></div>`;
      }
    } catch (err) {
      if (resultsEl) {
        resultsEl.innerHTML = `<div class="empty-state sm"><div class="empty-title">❌ ${escapeHTML(err.message)}</div></div>`;
      }
      MegaDL.App?.toast(`❌ Scan error: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '🔍 Scan Media';
    }
  }

  function _renderScanResults(res) {
    if (!res.media || Object.keys(res.media).length === 0) {
      return '<div class="empty-state sm"><div class="empty-icon">📭</div><div class="empty-subtitle">No media found</div></div>';
    }

    const mediaLabels = {
      photo: { icon: '🖼️', label: 'Photos' },
      video: { icon: '🎬', label: 'Videos' },
      document: { icon: '📄', label: 'Documents' },
      audio: { icon: '🎵', label: 'Audio' },
    };

    const mediaRows = Object.entries(res.media).map(([type, data]) => {
      const info = mediaLabels[type] || { icon: '📁', label: type };
      return `
        <div class="tg-scan-row">
          <span>${info.icon} ${info.label}</span>
          <span><strong>${data.count}</strong> files</span>
          <span>${formatBytes(data.total_size)}</span>
        </div>
      `;
    }).join('');

    const totalSize = res.total_size || 0;

    return `
      <div class="tg-scan-results-card">
        <div class="tg-scan-header">
          <span style="font-weight:600">📊 Scan Results</span>
          <span class="chip chip-primary">${res.total_count} files · ${formatBytes(totalSize)}</span>
        </div>
        <div class="tg-scan-rows">${mediaRows}</div>
        <div class="tg-scan-actions" style="margin-top:8px;display:flex;gap:8px">
          <button class="btn btn-sm btn-primary" onclick="MegaDL.Telegram.downloadAllScanResults()">⬇️ Download All</button>
          <button class="btn btn-sm btn-secondary" onclick="document.getElementById('tg-scan-results').style.display='none'">✕ Close</button>
        </div>
      </div>
    `;
  }

  function downloadAllScanResults() {
    if (selectedMessages.size === 0 && messages.length > 0) {
      messages.forEach(m => selectedMessages.add(m.id));
      _renderMessages(messages);
      _updateMsgActions();
    }
    downloadSelected();
  }

  /* ── Bot Scores ──────────────────────────────────────────── */
  function _wireBotScoreEvents() {
    $('tg-bot-scores-btn')?.addEventListener('click', toggleBotScores);
  }

  async function toggleBotScores() {
    const container = $('tg-bot-scores');
    if (!container) return;

    if (container.style.display === 'block') {
      container.style.display = 'none';
      return;
    }

    container.style.display = 'block';
    container.innerHTML = '<div class="empty-state sm"><div class="loading-spinner"></div><div class="empty-subtitle">Loading scores...</div></div>';

    try {
      const res = await API.tgBotScores();
      if (res.scores && res.scores.length > 0) {
        container.innerHTML = `
          <div style="font-size:0.85rem;margin-bottom:8px;color:var(--text-muted)">
            Weighted AI Scores: 40% load · 35% speed · 20% reliability · 5% recency
          </div>
          ${res.scores.map(s => {
            const pct = Math.round(s.score * 100);
            const color = pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)';
            return `
              <div class="setting-item" style="border-bottom:1px solid var(--border);padding:6px 0">
                <span style="font-family:monospace;font-size:.8rem">${escapeHTML(s.token_masked)}</span>
                <div style="flex:1;margin:0 12px">
                  <div style="display:flex;justify-content:space-between;font-size:.75rem">
                    <span>Score: ${pct}%</span>
                    <span>Tasks: ${s.stats.active_tasks} · Speed: ${formatBytes(s.stats.avg_speed_bps)}/s</span>
                  </div>
                  <div style="height:4px;background:var(--border);border-radius:2px;margin-top:2px">
                    <div style="height:100%;width:${pct}%;background:${color};border-radius:2px;transition:width .3s"></div>
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        `;
      } else {
        container.innerHTML = '<div class="empty-state sm"><div class="empty-subtitle">No bots in pool to score.</div></div>';
      }
    } catch (err) {
      container.innerHTML = `<div class="empty-state sm"><div class="empty-title">❌ ${escapeHTML(err.message)}</div></div>`;
    }
  }

  /* ── Download ────────────────────────────────────────────── */

  async function downloadSelected() {
    if (!selectedDialog || selectedMessages.size === 0) return;

    const msgIds = [...selectedMessages];
    const mode = $('tg-msg-mode')?.value || 'account';
    const botToken = $('tg-bot-token')?.value?.trim() || '';
    const dlFolder = $('tg-dl-folder')?.value || '';

    const btn = $('tg-msg-download-btn');
    _setBtnLoading(btn, true, 'Starting...');

    try {
      const res = await API.tgDownload(selectedDialog.id, msgIds, mode, botToken, dlFolder);
      if (res.jobs) {
        MegaDL.App?.toast(`⬇️ ${res.count} download(s) queued`, 'success');
        Router.navigate('active');
      } else if (res.forwarded !== undefined) {
        MegaDL.App?.toast(`↪️ ${res.forwarded}/${res.total} forwarded to bot`, 'success');
      } else {
        MegaDL.App?.toast('⬇️ Download started', 'success');
      }
      haptic('success');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      _setBtnLoading(btn, false, 'Download');
    }
  }

  function _setBtnLoading(btn, loading, text) {
    if (!btn) return;
    btn.disabled = loading;
    btn.innerHTML = loading
      ? `<span class="loading-spinner sm"></span><span>${text}</span>`
      : `<span>${text}</span>`;
  }

  /* ── Expose ──────────────────────────────────────────────── */
  return { init, onEnter, loadDialogs, loadMessages, downloadAllScanResults, toggleBotScores };
})();