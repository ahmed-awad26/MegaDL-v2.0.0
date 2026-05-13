/**
 * MegaDL — settings.js
 * Load/save user settings, theme switching, accent colors,
 * YouTube API key validation, Dependencies Dashboard.
 */

MegaDL.Settings = (() => {
  const { API, Utils, Config } = MegaDL;
  const { store, show, hide } = Utils;

  /* ── Current settings in memory ─────────────────────────── */
  let current = { ...Config.defaults };

  /* ── Field → settings key map ────────────────────────────── */
  const fieldMap = {
    's-dl-folder':         'dlFolder',
    's-def-quality':       'defQuality',
    's-auto-retry':        'autoRetry',
    's-auto-resume':       'autoResume',
    's-theme':             'theme',
    's-haptic':            'haptic',
    's-speed-limit':       'speedLimit',
    's-timeout':           'timeout',
    's-retries':           'retries',
    's-proxy':             'proxy',
    's-max-dl':            'maxParallel',
    's-frag-concurrent':   'concurrentFrag',
    's-merge-format':      'mergeFormat',
    's-embed-subs':        'embedSubs',
    's-sub-lang':          'subLang',
    's-embed-thumb':       'embedThumb',
    's-embed-meta':        'embedMeta',
    's-sponsorblock':      'sponsorblock',
    's-custom-args':       'customArgs',
    's-verbose':           'verbose',
    's-archive':           'archiveMode',
    's-debug':             'debugMode',
    's-youtube-api-key':   'youtube_api_key',
    's-telegram-api-id':   'telegram_api_id',
    's-telegram-api-hash': 'telegram_api_hash',
    's-blur-intensity':    'blurIntensity',
    's-dynamic-bg':        'dynamicBg',
    's-glass-effect':      'glassEffect',
  };

  /* ── Init ────────────────────────────────────────────────── */

  async function init() {
    const defaults = {
      ...Config.defaults,
      blurIntensity: 16,
      dynamicBg: true,
      glassEffect: true,
    };

    const saved = store.get('settings', {});
    current = { ...defaults, ...saved };

    _applyToUI(current);
    _applyTheme(current.theme || 'dark');
    _applyAccent(store.get('accent', '#6c63ff'));
    _applyBlur(current.blurIntensity || 16);
    _applyDynamicBg(current.dynamicBg !== false);
    _applyGlassEffect(current.glassEffect !== false);

    try {
      const remote = await API.getSettings();
      if (remote) {
        current = { ...current, ...remote };
        store.set('settings', current);
        _applyToUI(current);
      }
    } catch { /* offline */ }

    _wireTabs();
    _wireButtons();
    _wireAccentPicker();
    _wireBlurSlider();
    _wireDynamicBg();
    _wireGlassEffect();

    // Load yt-dlp current version
    try { await initYtdlpInfo(); } catch {}

    // Wire API key manager
    _wireApiKeyManager();
  }

  /* ── Wire tabs ──────────────────────────────────────────── */

  function _wireTabs() {
    document.querySelectorAll('.settings-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        const panel = document.getElementById(`settings-${tab.dataset.tab}`);
        if (panel) panel.classList.add('active');
      });
    });
  }

  /* ── Wire buttons ───────────────────────────────────────── */

  function _wireButtons() {
    document.getElementById('save-settings-btn')?.addEventListener('click', saveSettings);

    document.getElementById('reset-settings-btn')?.addEventListener('click', () => {
      MegaDL.App?.confirm('Reset all settings to defaults?', async () => {
        current = { ...Config.defaults };
        store.set('settings', current);
        _applyToUI(current);
        _applyTheme('dark');
        _applyAccent('#6c63ff');
        MegaDL.App?.toast('Settings reset to defaults', 'success');
      });
    });

    document.getElementById('s-theme')?.addEventListener('change', e => {
      const theme = e.target.value;
      _applyTheme(theme);
      current.theme = theme;
      store.set('settings', current);
    });

    // YouTube API key validation
    document.getElementById('validate-youtube-key-btn')?.addEventListener('click', validateYoutubeKey);

    // Dependencies check
    document.getElementById('check-deps-btn')?.addEventListener('click', checkDependencies);

    // Telegram API validation + save
    document.getElementById('validate-tg-api-btn')?.addEventListener('click', validateTelegramApi);
    document.getElementById('save-tg-api-btn')?.addEventListener('click', saveTelegramApi);

    // yt-dlp update
    document.getElementById('check-ytdlp-update-btn')?.addEventListener('click', checkYtdlpUpdate);
    document.getElementById('update-ytdlp-btn')?.addEventListener('click', updateYtdlp);

    // Download folder
    document.getElementById('save-dl-folder-btn')?.addEventListener('click', saveDlFolder);
    document.getElementById('test-dl-folder-btn')?.addEventListener('click', testDlFolder);
  }

  /* ── Accent picker ──────────────────────────────────────── */

  function _wireAccentPicker() {
    document.querySelectorAll('.accent-dot').forEach(dot => {
      dot.addEventListener('click', () => {
        const color = dot.dataset.color;
        _applyAccent(color);
        store.set('accent', color);
        document.querySelectorAll('.accent-dot').forEach(d => d.classList.remove('selected'));
        dot.classList.add('selected');
        Utils.haptic('light');
      });
    });

    const savedAccent = store.get('accent', '#6c63ff');
    document.querySelectorAll('.accent-dot').forEach(d => {
      if (d.dataset.color === savedAccent) d.classList.add('selected');
    });
  }

  /* ── Apply settings to form fields ──────────────────────── */

  function _applyToUI(settings) {
    Object.entries(fieldMap).forEach(([fieldId, key]) => {
      const el = document.getElementById(fieldId);
      if (!el) return;
      const val = settings[key];
      if (val === undefined || val === null) return;
      if (el.type === 'checkbox') el.checked = !!val;
      else el.value = val;
    });
  }

  /* ── Read settings from form fields ─────────────────────── */

  function _readFromUI() {
    const out = {};
    Object.entries(fieldMap).forEach(([fieldId, key]) => {
      const el = document.getElementById(fieldId);
      if (!el) return;
      if (el.type === 'checkbox') out[key] = el.checked;
      else if (el.type === 'number') out[key] = parseFloat(el.value) || 0;
      else out[key] = el.value;
    });
    return out;
  }

  /* ── Save settings ──────────────────────────────────────── */

  async function saveSettings() {
    const fromUI = _readFromUI();
    current = { ...current, ...fromUI };
    store.set('settings', current);

    _applyTheme(current.theme || 'dark');

    const btn = document.getElementById('save-settings-btn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }

    try {
      await API.saveSettings(current);
      MegaDL.App?.toast('✅ Settings saved', 'success');
    } catch {
      MegaDL.App?.toast('Settings saved locally', 'info');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '💾 Save Settings';
      }
    }
  }

  /* ── Download Folder ────────────────────────────────────── */

  async function saveDlFolder() {
    const input = document.getElementById('s-dl-folder');
    const status = document.getElementById('dl-folder-status');
    const path = input?.value?.trim();
    if (!path) {
      if (status) { status.textContent = '❌ Enter a path first'; status.style.color = 'var(--error)'; }
      return;
    }

    const btn = document.getElementById('save-dl-folder-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
    if (status) { status.textContent = '⏳ Saving...'; status.style.color = 'var(--text-muted)'; }

    try {
      await API.saveSettings({ dl_folder: path });
      current.dl_folder = path;
      store.set('settings', current);
      if (status) { status.textContent = '✅ Download path saved!'; status.style.color = 'var(--success)'; }
      MegaDL.App?.toast('✅ Download folder updated', 'success');
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '💾 Save Path'; }
    }
  }

  async function testDlFolder() {
    const input = document.getElementById('s-dl-folder');
    const status = document.getElementById('dl-folder-status');
    const path = input?.value?.trim();
    if (!path) {
      if (status) { status.textContent = '❌ Enter a path first'; status.style.color = 'var(--error)'; }
      return;
    }

    const btn = document.getElementById('test-dl-folder-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Testing...'; }
    if (status) { status.textContent = '⏳ Testing write access...'; status.style.color = 'var(--text-muted)'; }

    try {
      // Quick client-side test: just check if the path looks valid
      const isWin = navigator.userAgent.includes('Windows');
      const looksValid = isWin
        ? /^[a-zA-Z]:\\/.test(path) || /^\\\\/.test(path)
        : path.startsWith('/');
      if (!looksValid) {
        if (status) { status.textContent = '⚠️ Path format may be invalid'; status.style.color = 'var(--warning)'; }
        return;
      }
      // Also test via backend
      const data = await API.testDlFolder(path);
      if (data.writable) {
        if (status) { status.textContent = '✅ Path is writable!'; status.style.color = 'var(--success)'; }
        MegaDL.App?.toast('✅ Download folder is writable', 'success');
      } else {
        if (status) { status.textContent = `❌ ${data.error || 'Not writable'}`; status.style.color = 'var(--error)'; }
      }
    } catch (err) {
      if (status) { status.textContent = `⚠️ ${err.message}`; status.style.color = 'var(--warning)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🔍 Test'; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     YOUTUBE API KEY VALIDATION
     ══════════════════════════════════════════════════════════ */

  async function validateYoutubeKey() {
    const input = document.getElementById('s-youtube-api-key');
    const status = document.getElementById('youtube-key-status');
    if (!input || !status) return;

    const apiKey = input.value.trim();
    if (!apiKey) {
      status.textContent = '❌ Enter an API key first';
      status.style.color = 'var(--error)';
      return;
    }

    const btn = document.getElementById('validate-youtube-key-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Validating...'; }

    try {
      const res = await API.validateYoutubeKey(apiKey);
      if (res.valid) {
        status.textContent = '✅ Valid YouTube API key';
        status.style.color = 'var(--success)';
        MegaDL.App?.toast('✅ YouTube API key is valid!', 'success');
        // Save to settings
        current.youtube_api_key = apiKey;
        store.set('settings', current);
        await API.saveSettings({ youtube_api_key: apiKey });
      } else {
        status.textContent = `❌ ${res.error || 'Invalid key'}`;
        status.style.color = 'var(--error)';
        MegaDL.App?.toast('❌ YouTube API key invalid', 'error');
      }
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
      status.style.color = 'var(--error)';
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Validate'; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     TELEGRAM API VALIDATION
     ══════════════════════════════════════════════════════════ */

  async function validateTelegramApi() {
    const apiId = document.getElementById('s-telegram-api-id')?.value?.trim();
    const apiHash = document.getElementById('s-telegram-api-hash')?.value?.trim();
    const status = document.getElementById('tg-api-status');
    if (!apiId || !apiHash) {
      if (status) { status.textContent = '❌ Enter both API ID and Hash first'; status.style.color = 'var(--error)'; }
      return;
    }

    if (status) { status.textContent = '⏳ Validating...'; status.style.color = 'var(--text-muted)'; }

    const btn = document.getElementById('validate-tg-api-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Validating...'; }

    try {
      const res = await API.tgValidateCredentials(apiId, apiHash);
      if (res.valid) {
        if (status) { status.textContent = '✅ Credentials valid — Telegram reachable'; status.style.color = 'var(--success)'; }
        MegaDL.App?.toast('✅ Telegram credentials are valid!', 'success');
      } else {
        if (status) { status.textContent = `❌ ${res.error || 'Invalid credentials'}`; status.style.color = 'var(--error)'; }
        MegaDL.App?.toast('❌ Telegram credentials invalid', 'error');
      }
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🔍 Validate'; }
    }
  }

  async function saveTelegramApi() {
    const apiId = document.getElementById('s-telegram-api-id')?.value?.trim();
    const apiHash = document.getElementById('s-telegram-api-hash')?.value?.trim();
    const status = document.getElementById('tg-api-status');
    if (!apiId || !apiHash) {
      if (status) { status.textContent = '❌ Enter both API ID and Hash first'; status.style.color = 'var(--error)'; }
      return;
    }

    const btn = document.getElementById('save-tg-api-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

    try {
      await API.saveSettings({ telegram_api_id: apiId, telegram_api_hash: apiHash });
      current.telegram_api_id = apiId;
      current.telegram_api_hash = apiHash;
      store.set('settings', current);
      if (status) { status.textContent = '✅ Saved'; status.style.color = 'var(--success)'; }
      MegaDL.App?.toast('✅ Telegram credentials saved!', 'success');
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '💾 Save'; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     DEPENDENCIES DASHBOARD
     ══════════════════════════════════════════════════════════ */

  async function checkDependencies() {
    const list = document.getElementById('deps-list');
    if (!list) return;

    list.innerHTML = '<div class="empty-state sm"><div class="loading-spinner"></div><div class="empty-subtitle">Checking dependencies...</div></div>';

    try {
      const res = await API.checkDependencies();
      _renderDepsList(res.dependencies || {});
    } catch (err) {
      list.innerHTML = `<div class="empty-state sm"><div class="empty-subtitle">❌ ${escapeHTML(err.message)}</div></div>`;
    }
  }

  function _renderDepsList(deps) {
    const list = document.getElementById('deps-list');
    if (!list) return;

    const entries = Object.entries(deps);
    if (!entries.length) {
      list.innerHTML = '<div class="empty-state sm"><div class="empty-subtitle">No dependencies found</div></div>';
      return;
    }

    list.innerHTML = entries.map(([name, info]) => {
      const statusIcon = info.installed ? '✅' : '❌';
      const statusClass = info.installed ? 'chip-success' : 'chip-error';
      const versionText = info.version || 'not installed';
      const installBtn = !info.installed && info.type === 'pip'
        ? `<button class="btn btn-sm btn-primary dep-install-btn" data-dep="${escapeHTML(name)}">Install</button>`
        : '';
      return `
        <div class="dep-item" data-dep="${escapeHTML(name)}">
          <div class="dep-info">
            <div class="dep-name">${escapeHTML(name)}</div>
            <div class="dep-version">${escapeHTML(versionText)}</div>
          </div>
          <span class="chip ${statusClass}">${statusIcon} ${info.installed ? 'OK' : 'Missing'}</span>
          ${installBtn}
        </div>
      `;
    }).join('');

    // Wire install buttons
    list.querySelectorAll('.dep-install-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const dep = btn.dataset.dep;
        await _installDependency(dep, btn);
      });
    });
  }

  async function _installDependency(name, btn) {
    if (btn) { btn.disabled = true; btn.textContent = 'Installing...'; }

    try {
      const res = await API.installDependency(name);
      if (res.success) {
        MegaDL.App?.toast(`✅ ${name} installed successfully`, 'success');
        await checkDependencies(); // Refresh
      } else {
        const msg = res.instructions
          ? `Manual install needed: ${res.instructions}`
          : `Install failed: ${res.error || 'Unknown error'}`;
        MegaDL.App?.toast(`❌ ${msg}`, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
      }
    } catch (err) {
      MegaDL.App?.toast(`❌ ${err.message}`, 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
    }
  }

  /* ── Theme & Accent ─────────────────────────────────────── */

  function _applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme || 'dark');
  }

  function _applyAccent(color) {
    if (!color) return;
    document.documentElement.style.setProperty('--accent', color);
    document.documentElement.style.setProperty('--accent-dim',  `${color}25`);
    document.documentElement.style.setProperty('--accent-glow', `${color}55`);
  }

  /* ══════════════════════════════════════════════════════════
     BLUR SLIDER
     ══════════════════════════════════════════════════════════ */

  function _wireBlurSlider() {
    const slider = document.getElementById('s-blur-intensity');
    const valueDisplay = document.getElementById('blur-value');
    if (!slider || !valueDisplay) return;

    slider.addEventListener('input', () => {
      const val = parseInt(slider.value);
      valueDisplay.textContent = `${val}px`;
      _applyBlur(val);
      current.blurIntensity = val;
    });
  }

  function _applyBlur(val) {
    const px = `${val}px`;
    document.documentElement.style.setProperty('--blur-sm', val > 0 ? `blur(${Math.round(val/2)}px)` : 'blur(0px)');
    document.documentElement.style.setProperty('--blur-md', val > 0 ? `blur(${val}px)` : 'blur(0px)');
    document.documentElement.style.setProperty('--blur-lg', val > 0 ? `blur(${Math.round(val*2)}px)` : 'blur(0px)');
  }

  /* ══════════════════════════════════════════════════════════
     DYNAMIC BACKGROUND
     ══════════════════════════════════════════════════════════ */

  function _wireDynamicBg() {
    const toggle = document.getElementById('s-dynamic-bg');
    if (!toggle) return;
    toggle.addEventListener('change', () => {
      const enabled = toggle.checked;
      _applyDynamicBg(enabled);
      current.dynamicBg = enabled;
    });
  }

  function _applyDynamicBg(enabled) {
    const container = document.getElementById('dynamic-bg-container');
    if (!container) {
      if (!enabled) return;
      // Create container
      const bg = document.createElement('div');
      bg.id = 'dynamic-bg-container';
      bg.className = 'dynamic-bg';
      bg.innerHTML = '<div class="dynamic-bg-orb"></div><div class="dynamic-bg-orb"></div><div class="dynamic-bg-orb"></div>';
      document.body.prepend(bg);
      return;
    }
    container.classList.toggle('disabled', !enabled);
  }

  /* ══════════════════════════════════════════════════════════
     GLASS EFFECT
     ══════════════════════════════════════════════════════════ */

  function _wireGlassEffect() {
    const toggle = document.getElementById('s-glass-effect');
    if (!toggle) return;
    toggle.addEventListener('change', () => {
      const enabled = toggle.checked;
      _applyGlassEffect(enabled);
      current.glassEffect = enabled;
    });
  }

  function _applyGlassEffect(enabled) {
    document.querySelectorAll('.glass-card').forEach(el => {
      el.classList.toggle('no-glass', !enabled);
    });
    // Watch for new glass cards added to DOM
    if (!enabled) {
      const observer = new MutationObserver(() => {
        document.querySelectorAll('.glass-card:not(.no-glass)').forEach(el => {
          el.classList.add('no-glass');
        });
      });
      observer.observe(document.body, { childList: true, subtree: true });
      // Store observer reference
      window._glassObserver = observer;
    } else {
      const observer = window._glassObserver;
      if (observer) {
        observer.disconnect();
        window._glassObserver = null;
      }
    }
  }

  function getCurrent() { return { ...current }; }

  function refresh() {
    _wireTabs();
    const saved = store.get('settings', {});
    current = { ...current, ...saved };
    _applyToUI(current);
    _applyTheme(current.theme || 'dark');
  }

  function updateKeys(pairs) {
    Object.assign(current, pairs);
    store.set('settings', current);
  }

  /* ══════════════════════════════════════════════════════════
     YT-DLP UPDATE
     ══════════════════════════════════════════════════════════ */

  async function initYtdlpInfo() {
    const versionEl = document.getElementById('ytdlp-current-version');
    if (versionEl) versionEl.textContent = 'Checking...';
    try {
      const res = await API.ytdlpCheckUpdate();
      if (versionEl) versionEl.textContent = res.current || 'not installed';
    } catch {
      if (versionEl) versionEl.textContent = 'unknown';
    }
  }

  async function checkYtdlpUpdate() {
    const status = document.getElementById('ytdlp-update-status');
    const btn = document.getElementById('check-ytdlp-update-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Checking...'; }
    if (status) { status.textContent = '⏳ Checking for updates...'; }
    try {
      const res = await API.ytdlpCheckUpdate();
      if (status) {
        if (res.update_available) {
          status.innerHTML = '⬇️ Update available! Click "Update Now"';
          status.style.color = 'var(--warning)';
        } else {
          status.textContent = '✅ yt-dlp is up to date';
          status.style.color = 'var(--success)';
        }
      }
      const versionEl = document.getElementById('ytdlp-current-version');
      if (versionEl) versionEl.textContent = res.current || 'not installed';
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🔍 Check Update'; }
    }
  }

  async function updateYtdlp() {
    const status = document.getElementById('ytdlp-update-status');
    const btn = document.getElementById('update-ytdlp-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Updating...'; }
    if (status) { status.textContent = '⏳ Updating yt-dlp...'; }
    try {
      const res = await API.ytdlpUpdate();
      if (status) {
        if (res.success) {
          status.innerHTML = '✅ yt-dlp updated successfully!';
          status.style.color = 'var(--success)';
        } else {
          status.textContent = `❌ ${res.error || 'Update failed'}`;
          status.style.color = 'var(--error)';
        }
      }
      const versionEl = document.getElementById('ytdlp-current-version');
      if (versionEl) versionEl.textContent = res.version || 'unknown';
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '⬇ Update Now'; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     UNIVERSAL API KEY MANAGER
     ══════════════════════════════════════════════════════════ */

  function _wireApiKeyManager() {
    const providerSelect = document.getElementById('api-provider-select');
    const keyInput = document.getElementById('s-api-key-input');
    const validateBtn = document.getElementById('validate-api-key-btn');
    const status = document.getElementById('api-key-status');

    providerSelect?.addEventListener('change', async () => {
      const provider = providerSelect.value;
      if (!provider) {
        if (keyInput) keyInput.value = '';
        if (status) status.textContent = 'No key configured';
        return;
      }
      // Load existing key
      try {
        const res = await API.getApiKeys();
        const keys = res.keys || {};
        if (keys[provider]) {
          if (keyInput) keyInput.value = '';
          if (keyInput) keyInput.placeholder = keys[provider];
          if (status) status.textContent = `🔑 ${keys[provider]}`;
        } else {
          if (keyInput) keyInput.placeholder = 'Enter API key...';
          if (status) status.textContent = 'No key configured';
        }
      } catch {}
    });

    validateBtn?.addEventListener('click', validateApiKey);
  }

  async function validateApiKey() {
    const provider = document.getElementById('api-provider-select')?.value;
    const keyInput = document.getElementById('s-api-key-input');
    const status = document.getElementById('api-key-status');
    const btn = document.getElementById('validate-api-key-btn');

    if (!provider) {
      if (status) { status.textContent = '❌ Select a provider first'; status.style.color = 'var(--error)'; }
      return;
    }

    const apiKey = keyInput?.value?.trim();
    if (!apiKey) {
      if (status) { status.textContent = '❌ Enter an API key'; status.style.color = 'var(--error)'; }
      return;
    }

    if (btn) { btn.disabled = true; btn.textContent = '⏳ Validating...'; }
    if (status) { status.textContent = '⏳ Validating...'; status.style.color = 'var(--text-muted)'; }

    try {
      const data = await API.validateApiKey(provider, apiKey);
      if (data.valid) {
        if (status) { status.textContent = `✅ ${data.message || 'Valid!'}`; status.style.color = 'var(--success)'; }
        MegaDL.App?.toast(`✅ ${provider} API key is valid!`, 'success');
        if (keyInput) keyInput.value = '';
        if (keyInput) keyInput.placeholder = apiKey.substring(0, 6) + '...' + apiKey.slice(-4);
      } else {
        if (status) { status.textContent = `❌ ${data.error || 'Invalid key'}`; status.style.color = 'var(--error)'; }
        MegaDL.App?.toast(`❌ ${provider} key invalid`, 'error');
      }
    } catch (err) {
      if (status) { status.textContent = `❌ ${err.message}`; status.style.color = 'var(--error)'; }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🔍 Validate'; }
    }
  }

  return { init, saveSettings, getCurrent, refresh, updateKeys, checkDependencies, validateYoutubeKey, initYtdlpInfo, checkYtdlpUpdate, updateYtdlp };
})();
