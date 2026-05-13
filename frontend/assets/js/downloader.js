/**
 * MegaDL — downloader.js
 * Handles URL input, video info fetching, format selection, and starting downloads.
 */

MegaDL.Downloader = (() => {
  const { API, Utils, Config } = MegaDL;
  const { parseUrls, sanitizeUrl, formatBytes, formatDuration, formatNumber,
          buildYtdlpCommand, escapeHTML, haptic, show, hide, toggle, copyToClipboard } = Utils;

  /* ── State ───────────────────────────────────────────────── */
  let currentInfo   = null;
  let selectedFormat = null;
  let isFetching    = false;

  /* ── DOM refs ────────────────────────────────────────────── */
  const $ = id => document.getElementById(id);

  /* ── Init ────────────────────────────────────────────────── */

  function init() {
    // Fetch Info button
    $('fetch-info-btn')?.addEventListener('click', fetchInfo);

    // Download button
    $('download-btn')?.addEventListener('click', startDownload);

    // Confirm download (from info card)
    $('confirm-download-btn')?.addEventListener('click', confirmDownload);

    // Paste button
    $('paste-btn')?.addEventListener('click', async () => {
      const text = await Utils.readClipboard();
      if (text) {
        const input = $('url-input');
        if (input) {
          input.value = text.trim();
          input.dispatchEvent(new Event('input'));
          haptic('light');
        }
      }
    });

    // Copy command button
    $('copy-cmd-btn')?.addEventListener('click', async () => {
      const code = $('cmd-preview-code')?.textContent;
      if (code) {
        await copyToClipboard(code);
        MegaDL.App?.toast('Command copied!', 'success');
      }
    });

    // Live command preview on option changes
    ['url-input','quality-select','format-select','mode-select',
     'opt-subs','opt-thumb','opt-meta','opt-sponsor','opt-cookies','opt-clean-url','opt-latest-only']
      .forEach(id => {
        $(`${id}`)?.addEventListener('change', _updateCommandPreview);
        $(`${id}`)?.addEventListener('input',  _updateCommandPreview);
      });

    // Ctrl+Enter = fetch info; Ctrl+D = download
    document.addEventListener('keydown', e => {
      if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); fetchInfo(); }
      if (e.ctrlKey && e.key === 'd')     { e.preventDefault(); startDownload(); }
    });

    // Space bar = pause/resume first active job (when not in input)
    document.addEventListener('keydown', e => {
      if (e.key === ' ' && !e.target.matches('input,textarea,select')) {
        e.preventDefault();
        const active = MegaDL.Jobs.getActive();
        if (active.length) {
          const job = active[0];
          job.state === 'paused'
            ? API.resumeJob(job.id)
            : API.pauseJob(job.id);
        }
      }
    });

    // Drag & drop URLs (desktop)
    document.addEventListener('dragover', e => e.preventDefault());
    document.addEventListener('drop', e => {
      e.preventDefault();
      const text = e.dataTransfer.getData('text');
      if (text) {
        const input = $('url-input');
        if (input) {
          input.value = text.trim();
          fetchInfo();
        }
      }
    });

    // Batch queue page
    $('parse-batch-btn')?.addEventListener('click', parseBatchUrls);
    $('start-batch-btn')?.addEventListener('click', startBatchDownload);

    // Quick paste modal
    $('quick-paste-go')?.addEventListener('click', () => {
      const url = $('quick-paste-input')?.value;
      if (url) {
        const input = $('url-input');
        if (input) input.value = url;
        hide('modal-paste');
        startDownload();
      }
    });

    // Desktop FAB
    $('desktop-fab')?.addEventListener('click', () => {
      MegaDL.Router.navigate('home');
      setTimeout(() => $('url-input')?.focus(), 200);
    });
  }

  /* ── Build current options from UI ──────────────────────── */

  function _buildOptions() {
    const settings = MegaDL.Settings?.getCurrent() || {};
    return {
      quality:        $('quality-select')?.value  || settings.defQuality || 'best',
      format:         $('format-select')?.value   || 'mp4',
      mode:           _getEffectiveMode(),
      embedSubs:      $('opt-subs')?.checked      || settings.embedSubs   || false,
      embedThumb:     $('opt-thumb')?.checked     || settings.embedThumb  || true,
      embedMeta:      $('opt-meta')?.checked      || settings.embedMeta   || true,
      sponsorblock:   $('opt-sponsor')?.checked   || settings.sponsorblock || false,
      cookies:        $('opt-cookies')?.checked   || false,
      latestOnly:     $('opt-latest-only')?.checked || false,
      mergeFormat:    settings.mergeFormat || 'mp4',
      proxy:          settings.proxy       || '',
      retries:        settings.retries     || 3,
      fragRetries:    settings.fragRetries || 5,
      concurrentFrag: settings.concurrentFrag || 4,
      speedLimit:     settings.speedLimit  || 0,
      subLang:        settings.subLang     || 'en',
      archiveMode:    settings.archiveMode || true,
      verbose:        settings.verbose     || false,
      customArgs:     settings.customArgs  || '',
    };
  }

  /* ── Update command preview ──────────────────────────────── */

  function _updateCommandPreview() {
    const urls = parseUrls($('url-input')?.value || '');
    const url  = urls[0] || 'https://youtube.com/watch?v=...';
    const opts = _buildOptions();
    const cmd  = buildYtdlpCommand(url, opts);
    const pre  = $('cmd-preview-code');
    const wrap = $('cmd-preview');
    if (pre && wrap) {
      pre.textContent = cmd;
      wrap.style.display = 'block';
    }
  }

  /* ── Fetch video info ────────────────────────────────────── */

  /* ── Detect YouTube channel URLs ─────────────────────────── */
  function _isChannelUrl(url) {
    return /youtube\.com\/(@|channel\/|c\/|user\/)/i.test(url);
  }

  function _showChannelModeOptions(show) {
    const group = $('channel-mode-group');
    if (group) group.style.display = show ? 'block' : 'none';
    if (!show) {
      // Reset mode to single when not a channel
      const modeSelect = $('mode-select');
      if (modeSelect && modeSelect.value === 'single') return;
    }
  }

  function _getEffectiveMode() {
    const mode = $('mode-select')?.value || 'single';
    const channelMode = $('channel-mode-select')?.value;
    const isChannel = _isChannelUrl($('url-input')?.value || '');
    if (isChannel && channelMode && channelMode !== 'none') {
      return channelMode;
    }
    return mode;
  }

  function _isChannelMode(mode) {
    return ['playlists_only', 'uploads_only', 'playlists_and_uploads',
            'all_uncategorized', 'latest_since_last_run'].includes(mode);
  }

  function _showPlaylistSelector(url, playlists) {
    // Remove existing modal
    const old = document.getElementById('playlist-selector-modal');
    if (old) old.remove();

    const modal = document.createElement('div');
    modal.id = 'playlist-selector-modal';
    modal.className = 'modal-backdrop';
    modal.style.cssText = 'display:flex;z-index:600;background:var(--bg-overlay)';

    modal.innerHTML = `
      <div class="modal" style="max-width:520px;width:90%;max-height:80vh;display:flex;flex-direction:column">
        <div class="modal-header">
          <span class="modal-title">📋 Select Playlists</span>
          <button class="icon-btn" onclick="document.getElementById('playlist-selector-modal')?.remove()">✕</button>
        </div>
        <div class="modal-body" style="flex:1;overflow-y:auto;padding:12px 0">
          <div style="padding:0 16px 12px;font-size:0.82rem;color:var(--text-muted)">
            Select the playlists you want to download from this channel
          </div>
          <div id="playlist-list">
            ${playlists.map((p, i) => `
              <label class="playlist-item" data-index="${i}">
                <input type="checkbox" class="playlist-check" data-id="${escapeHTML(p.id)}" checked />
                <span class="playlist-thumb" style="background-image:url(${escapeHTML(p.thumbnail || '')})"></span>
                <span class="playlist-info">
                  <span class="playlist-title">${escapeHTML(p.title)}</span>
                  <span class="playlist-meta">${p.video_count} videos</span>
                </span>
              </label>
            `).join('')}
          </div>
        </div>
        <div class="modal-footer" style="padding:12px 16px;display:flex;gap:8px;justify-content:flex-end;border-top:1px solid var(--glass-border)">
          <button class="btn btn-secondary" id="pl-select-all">Select All</button>
          <button class="btn btn-secondary" id="pl-deselect-all">Deselect All</button>
          <button class="btn btn-primary" id="pl-download-btn">⬇ Download Selected</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    document.getElementById('pl-select-all')?.addEventListener('click', () => {
      modal.querySelectorAll('.playlist-check').forEach(cb => cb.checked = true);
    });
    document.getElementById('pl-deselect-all')?.addEventListener('click', () => {
      modal.querySelectorAll('.playlist-check').forEach(cb => cb.checked = false);
    });
    document.getElementById('pl-download-btn')?.addEventListener('click', () => {
      const selected = [...modal.querySelectorAll('.playlist-check:checked')].map(cb => cb.dataset.id);
      if (!selected.length) {
        MegaDL.App?.toast('Select at least one playlist', 'warning');
        return;
      }
      modal.remove();
      _queuePlaylistDownloads(url, selected);
    });
  }

  async function _queuePlaylistDownloads(channelUrl, playlistIds) {
    if (!playlistIds.length) return;
    const opts = _buildOptions();
    const urls = playlistIds.map(pid => `${channelUrl}?list=${pid}`);

    MegaDL.App?.toast(`⬇ Queueing ${urls.length} playlists...`, 'info');
    try {
      await API.startBatch(urls, { ...opts, max_parallel: 2 });
      haptic('success');
      MegaDL.App?.toast(`✅ ${urls.length} playlists queued!`, 'success');
      MegaDL.Router.navigate('active');
      MegaDL.Jobs.forceRefresh();
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    }
  }

  /* ── Fetch info ──────────────────────────────────────────── */

  async function fetchInfo() {
    if (isFetching) return;
    const raw  = $('url-input')?.value?.trim();
    const urls = parseUrls(raw);
    if (!urls.length) {
      MegaDL.App?.toast('Please paste a URL first', 'warning');
      return;
    }

    let url = urls[0];

    // Clean URL if toggle is enabled
    const cleanUrlEnabled = $('opt-clean-url')?.checked ?? true;
    if (cleanUrlEnabled) {
      try {
        const cleanRes = await API.urlClean([url], true);
        if (cleanRes.cleaned && cleanRes.cleaned[0]) {
          const cleanedUrl = cleanRes.cleaned[0];
          if (cleanedUrl !== url) {
            MegaDL.App?.toast('🧹 URL cleaned', 'info');
            url = cleanedUrl;
          }
        }
      } catch (err) {
        console.warn('URL cleaning failed:', err);
        // Continue with original URL if cleaning fails
      }
    }

    const safeUrl = sanitizeUrl(url);
    if (!safeUrl) {
      MegaDL.App?.toast('⚠️ URL appears to be blocked or invalid', 'error');
      return;
    }

    // Check for YouTube channel URL → show channel mode & playlist selector
    if (_isChannelUrl(safeUrl)) {
      _showChannelModeOptions(true);
      isFetching = true;
      const btn = $('fetch-info-btn');
      if (btn) { btn.disabled = true; btn.innerHTML = `<span class="loading-spinner sm"></span><span>Loading channel...</span>`; }
      try {
        const res = await API.getChannelPlaylists(safeUrl);
        if (res.playlists && res.playlists.length > 0) {
          _showPlaylistSelector(safeUrl, res.playlists);
          haptic('success');
        } else if (res.needs_api_key) {
          MegaDL.App?.toast('⚠️ YouTube API key needed. Go to Settings → Integrations.', 'warning');
        } else {
          MegaDL.App?.toast('No public playlists found for this channel', 'info');
        }
      } catch (err) {
        MegaDL.App?.toast(`❌ ${err.message}`, 'error');
      } finally {
        isFetching = false;
        if (btn) { btn.disabled = false; btn.innerHTML = `<span class="btn-icon">🔍</span><span>Fetch Info</span>`; }
      }
      return;
    } else {
      _showChannelModeOptions(false);
    }

    isFetching = true;
    const btn = $('fetch-info-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-spinner sm"></span><span>Fetching...</span>`;
    }

    // Hide previous info card
    hide('video-info-card');

    try {
      const data = await API.fetchInfo(safeUrl, _buildOptions());

      if (!data || !data.title) throw new Error('No info returned');

      currentInfo = data;
      _renderInfoCard(data);
      show('video-info-card', 'block');
      haptic('success');

      // Auto-scroll to info card on mobile
      $('video-info-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message || 'Could not fetch info'}`, 'error');
    } finally {
      isFetching = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon">🔍</span><span>Fetch Info</span>`;
      }
    }
  }

  /* ── Render video info card ──────────────────────────────── */

  function _renderInfoCard(data) {
    const { formatBytes: fb, formatDuration: fd, formatNumber: fn, escapeHTML } = Utils;

    // Thumbnail
    const thumb = $('video-thumb');
    if (thumb) { thumb.src = data.thumbnail || ''; thumb.alt = data.title || ''; }

    // Text fields
    Utils.setText('video-title',    data.title     || '—');
    Utils.setText('video-uploader', data.uploader  || data.channel || '—');
    Utils.setText('video-duration', fd(data.duration));
    Utils.setText('video-resolution', data.resolution || (data.height ? `${data.height}p` : '—'));
    Utils.setText('video-size',     data.filesize  ? fb(data.filesize) : '—');
    Utils.setText('video-views',    data.view_count ? `👁 ${fn(data.view_count)}` : '—');

    // Enriched metadata
    if (data.id) {
      Utils.setText('video-id', `🆔 ${escapeHTML(data.id)}`);
    }
    const likesEl = $('video-likes');
    if (likesEl) {
      if (data.like_count != null) {
        likesEl.textContent = `👍 ${fn(data.like_count)}`;
        likesEl.style.display = '';
      } else {
        likesEl.style.display = 'none';
      }
    }
    const commentsEl = $('video-comments');
    if (commentsEl) {
      if (data.comment_count != null) {
        commentsEl.textContent = `💬 ${fn(data.comment_count)}`;
        commentsEl.style.display = '';
      } else {
        commentsEl.style.display = 'none';
      }
    }
    const uploadDateEl = $('video-upload-date');
    if (uploadDateEl) {
      if (data.upload_date) {
        const d = data.upload_date;
        uploadDateEl.textContent = `📅 ${d.substring(0,4)}-${d.substring(4,6)}-${d.substring(6,8)}`;
        uploadDateEl.style.display = '';
      } else {
        uploadDateEl.style.display = 'none';
      }
    }

    // Channel info
    const channelEl = $('video-channel');
    if (channelEl) {
      let parts = [];
      if (data.channel_id) parts.push(`📺 ${escapeHTML(data.channel_id)}`);
      if (data.channel) parts.push(`by ${escapeHTML(data.channel)}`);
      channelEl.textContent = parts.join(' · ');
    }

    // Description
    const descEl = $('video-description');
    if (descEl && data.description) {
      descEl.textContent = data.description.substring(0, 300);
      descEl.title = data.description;
    }

    // Tags
    const tagsEl = $('video-tags');
    if (tagsEl && data.tags && data.tags.length) {
      tagsEl.innerHTML = data.tags.slice(0, 10).map(t =>
        `<span class="tag" style="display:inline-block;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:2px 8px;font-size:.7rem;margin:2px">${escapeHTML(t)}</span>`
      ).join('');
    }

    // Channel ID (hidden stat chip)
    const channelIdEl = $('video-channel-id');
    if (channelIdEl && data.channel_id) {
      channelIdEl.textContent = `📺 ${escapeHTML(data.channel_id)}`;
      channelIdEl.style.display = '';
    } else if (channelIdEl) {
      channelIdEl.style.display = 'none';
    }

    // "Fetch Uncategorized" button for YouTube channels
    const isYtChannel = data.extractor === 'youtube' && data.channel_id;
    let uncatBtn = document.getElementById('fetch-uncategorized-btn');
    if (isYtChannel) {
      if (!uncatBtn) {
        uncatBtn = document.createElement('button');
        uncatBtn.id = 'fetch-uncategorized-btn';
        uncatBtn.className = 'btn btn-sm btn-secondary';
        uncatBtn.style.marginTop = '8px';
        uncatBtn.innerHTML = '📋 Fetch Uncategorized Videos';
        uncatBtn.addEventListener('click', async () => {
          uncatBtn.disabled = true;
          uncatBtn.textContent = 'Fetching...';
          try {
            const channelUrl = data.webpage_url || data.original_url || '';
            const res = await API.ytUncategorized(channelUrl);
            if (res.videos && res.videos.length > 0) {
              const urls = res.videos.map(v => v.url);
              $('url-input').value = urls.join('\n');
              MegaDL.App?.toast(`📋 ${res.uncategorized} uncategorized videos loaded into URL input`, 'success');
            } else {
              MegaDL.App?.toast('✅ All uploads are in playlists (no uncategorized found)', 'success');
            }
          } catch (err) {
            MegaDL.App?.toast(`❌ ${err.message}`, 'error');
          } finally {
            uncatBtn.disabled = false;
            uncatBtn.textContent = '📋 Fetch Uncategorized Videos';
          }
        });
        $('video-tags')?.after?.(uncatBtn);
      }
      uncatBtn.style.display = '';
    } else if (uncatBtn) {
      uncatBtn.style.display = 'none';
    }

    // Format picker
    _renderFormatPicker(data.formats || []);
  }

  /* ── Format picker ───────────────────────────────────────── */

  function _renderFormatPicker(formats) {
    const container = $('format-picker');
    if (!container) return;

    if (!formats.length) {
      container.innerHTML = '';
      return;
    }

    const seen  = new Set();
    const items = [];

    const audioFmts = formats.filter(f => !f.height && f.acodec && f.acodec !== 'none');
    const videoFmts = formats.filter(f => f.height).sort((a, b) => b.height - a.height);

    videoFmts.forEach(f => {
      const key = `${f.height}p${f.fps || ''}${f.vcodec || ''}`;
      if (!seen.has(key)) {
        seen.add(key);
        let label = `${f.height}p`;
        if (f.fps && f.fps > 30) label += ` ${Math.round(f.fps)}fps`;
        const badges = [];
        if (f.vcodec) {
          const codecLabel = { 'av01': 'AV1', 'vp9': 'VP9', 'vp09': 'VP9', 'hevc': 'HDR', 'h265': 'HEVC', 'h264': 'H.264' }[f.vcodec.replace(/\./g,'').toLowerCase().substring(0,4)] || f.vcodec.substring(0,6);
          badges.push(codecLabel);
        }
        if (f.dynamic_range && f.dynamic_range !== 'SDR') badges.push(f.dynamic_range.toUpperCase());
        if (f.has_drm) badges.push('🔒 DRM');
        items.push({
          id: f.format_id, label, ext: f.ext || 'mp4',
          size: f.filesize, type: 'video',
          badges: badges.join(' · '),
          detail: f.protocol ? f.protocol.toUpperCase() : '',
        });
      }
    });

    audioFmts.slice(0, 3).forEach(f => {
      const aCodec = f.acodec ? f.acodec.substring(0, 4).toUpperCase() : '';
      const channels = f.audio_channels ? `${f.audio_channels}ch` : '';
      const badges = [aCodec, channels].filter(Boolean).join(' · ');
      items.push({
        id: f.format_id, label: aCodec === 'OPUS' ? 'Opus' : aCodec === 'MP4A' ? 'AAC' : 'Audio',
        ext: 'm4a', size: f.filesize, type: 'audio',
        badges, detail: `${f.abr ? Math.round(f.abr) + 'k' : ''}${f.language ? ' · ' + f.language : ''}`,
      });
    });

    container.innerHTML = items.map((item, idx) => {
      const sizeLabel = item.size ? ` · ${Utils.formatBytes(item.size)}` : '';
      const icon = item.type === 'audio' ? '🎵 ' : '🎬 ';
      const badges = item.badges ? `<span class="fmt-badges" style="font-size:.65rem;color:var(--text-muted);margin-left:6px">${item.badges}</span>` : '';
      const detail = item.detail ? `<span class="fmt-detail" style="font-size:.6rem;color:var(--text-muted);margin-left:4px">${item.detail}</span>` : '';
      return `<button class="format-btn${idx === 0 ? ' selected' : ''}" 
        data-format-id="${escapeHTML(item.id)}" 
        data-ext="${item.ext}">
        ${icon}${item.label}${sizeLabel}${badges}${detail}
      </button>`;
    }).join('');

    if (items.length) selectedFormat = items[0];

    container.querySelectorAll('.format-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.format-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        selectedFormat = {
          id:  btn.dataset.formatId,
          ext: btn.dataset.ext,
        };
      });
    });
  }

  /* ── Start download (from URL input directly) ────────────── */

  async function startDownload() {
    const raw  = $('url-input')?.value?.trim();
    const urls = parseUrls(raw);

    if (!urls.length) {
      MegaDL.App?.toast('Please paste a URL first', 'warning');
      return;
    }

    // Multiple URLs → go to batch flow
    if (urls.length > 1) {
      _handleMultipleUrls(urls);
      return;
    }

    await _queueDownload(urls[0]);
  }

  /* ── Confirm download from info card ─────────────────────── */

  async function confirmDownload() {
    const raw  = $('url-input')?.value?.trim();
    const urls = parseUrls(raw);
    if (!urls.length) return;
    await _queueDownload(urls[0], selectedFormat);
  }

  /* ── Queue single download ───────────────────────────────── */

  async function _queueDownload(url, format = null) {
    const safeUrl = sanitizeUrl(url);
    if (!safeUrl) {
      MegaDL.App?.toast('⚠️ URL blocked or invalid', 'error');
      return;
    }

    const opts = { ..._buildOptions() };
    if (format?.id)  opts.format_id  = format.id;
    if (format?.ext) opts.format_ext = format.ext;

    // Handle YouTube channel modes — queue the channel URL with mode flag
    if (_isChannelMode(opts.mode)) {
      const btn = $('download-btn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="loading-spinner sm"></span><span>Queuing channel...</span>`;
      }
      try {
        // For channel modes, queue the channel URL directly — backend handles the logic
        const res = await API.startDownload(safeUrl, opts);
        haptic('success');
        const modeLabels = {
          playlists_only: '📂 Playlists',
          uploads_only: '📤 Uploads',
          playlists_and_uploads: '📂+📤 Playlists+Uploads',
          all_uncategorized: '📂+📤+📁 All+Uncategorized',
          latest_since_last_run: '🆕 Latest',
        };
        MegaDL.App?.toast(`⬇️ ${modeLabels[opts.mode] || opts.mode} queued!`, 'success');
        _resetAfterDownload();
        MegaDL.Router.navigate('active');
      } catch (err) {
        MegaDL.App?.toast(`❌ ${err.message}`, 'error');
      } finally {
        const btn2 = $('download-btn');
        if (btn2) { btn2.disabled = false; btn2.innerHTML = `<span>⬇️ Download</span>`; }
      }
      return;
    }

    const btn = $('download-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-spinner sm"></span><span>Queuing...</span>`;
    }

    try {
      const res = await API.startDownload(safeUrl, opts);
      haptic('success');
      MegaDL.App?.toast(`⬇️ Download queued!`, 'success');

      // Clear input
      _resetAfterDownload();

      // Navigate to active jobs
      MegaDL.Router.navigate('active');
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      const btn2 = $('download-btn');
      if (btn2) {
        btn2.disabled = false;
        btn2.innerHTML = `<span>⬇️ Download</span>`;
      }
    }
  }

  function _resetAfterDownload() {
    const input = $('url-input');
    if (input) input.value = '';
    hide('video-info-card');
    currentInfo   = null;
    selectedFormat = null;
  }

  /* ── Handle multiple URLs pasted ─────────────────────────── */

  function _handleMultipleUrls(urls) {
    // Pre-fill batch queue and navigate
    const batchArea = $('batch-urls');
    if (batchArea) batchArea.value = urls.join('\n');
    MegaDL.Router.navigate('queue');
    MegaDL.App?.toast(`📋 ${urls.length} URLs moved to Batch Queue`, 'info');
  }

  /* ── Batch queue parsing ─────────────────────────────────── */

  function parseBatchUrls() {
    const raw  = $('batch-urls')?.value || '';
    const urls = parseUrls(raw);

    const container = $('batch-queue-list');
    if (!container) return;

    if (!urls.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-subtitle">No valid URLs found</div></div>';
      return;
    }

    container.innerHTML = urls.map((url, i) => `
      <div class="batch-item queued" data-url="${escapeHTML(url)}" data-index="${i}">
        <span class="batch-item-url">${escapeHTML(url)}</span>
        <span class="batch-item-status chip chip-muted">queued</span>
        <button class="icon-btn" onclick="this.closest('.batch-item').remove()" title="Remove">✕</button>
      </div>
    `).join('');

    MegaDL.App?.toast(`Parsed ${urls.length} URLs`, 'success');
  }

  /* ── Start batch download ────────────────────────────────── */

  async function startBatchDownload() {
    const items = [...document.querySelectorAll('.batch-item[data-url]')];
    if (!items.length) {
      parseBatchUrls();
      return;
    }

    const urls = items.map(el => el.dataset.url).filter(Boolean);
    const quality  = $('batch-quality')?.value  || 'best';
    const parallel = $('batch-parallel')?.value || 2;

    const btn = $('start-batch-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Starting...'; }

    try {
      await API.startBatch(urls, { quality, max_parallel: parseInt(parallel), ..._buildOptions() });
      haptic('success');
      MegaDL.App?.toast(`⬇️ ${urls.length} downloads queued!`, 'success');
      MegaDL.Router.navigate('active');
      MegaDL.Jobs.forceRefresh();
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Start All'; }
    }
  }

  /* ── Expose ──────────────────────────────────────────────── */
  return { init, fetchInfo, startDownload, confirmDownload, parseBatchUrls, startBatchDownload };
})();
