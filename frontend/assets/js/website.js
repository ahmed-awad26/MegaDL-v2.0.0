/**
 * MegaDL — website.js
 * Website Downloader: mirror complete websites via wget and download as zip.
 * Ported from https://github.com/AhmadIbrahiim/Website-downloader
 */

MegaDL.WebsiteDownloader = (() => {
  const { API, Utils } = MegaDL;
  const { $, show, hide, store } = Utils;

  let activeJobId = null;
  let checkInterval = null;
  let knownLogLines = 0;

  function init() {
    $('#website-url-btn')?.addEventListener('click', startDownload);
    $('#website-url-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') startDownload();
    });
    $('#website-refresh-btn')?.addEventListener('click', checkHealth);
    checkHealth();
  }

  async function checkHealth() {
    try {
      const res = await API.websiteCheck();
      const statusEl = $('#website-status');
      if (res.wget_available) {
        statusEl.innerHTML = '✅ wget available';
        statusEl.style.color = 'var(--success)';
        $('#website-url-btn').disabled = false;
      } else {
        statusEl.innerHTML = '❌ wget not found. Install: <code>apt install wget</code>';
        statusEl.style.color = 'var(--error)';
        $('#website-url-btn').disabled = true;
      }
    } catch {
      $('#website-status').textContent = '⚠ Could not check wget';
    }
  }

  async function startDownload() {
    const input = $('#website-url-input');
    const status = $('#website-dl-status');
    const log = $('#website-log');
    const btn = $('#website-url-btn');
    const progressBar = $('#website-progress-bar');

    let url = input?.value?.trim();
    if (!url) {
      if (status) status.textContent = '❌ Enter a URL first';
      return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://' + url;
      input.value = url;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Downloading...';
    if (status) status.textContent = '⏳ Starting download...';
    if (log) log.innerHTML = '';
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0 files'; }
    knownLogLines = 0;
    show('website-progress-container');

    try {
      const res = await API.websiteDownload(url);
      if (!res.ok) {
        if (status) status.textContent = `❌ ${res.error || 'Failed to start'}`;
        btn.disabled = false;
        btn.textContent = '⬇ Download Website';
        return;
      }
      activeJobId = res.job_id;
      if (status) status.textContent = '⏳ Downloading...';
      pollStatus(activeJobId);
    } catch (err) {
      if (status) status.textContent = `❌ ${err.message}`;
      btn.disabled = false;
      btn.textContent = '⬇ Download Website';
    }
  }

  function pollStatus(jobId) {
    if (checkInterval) clearInterval(checkInterval);
    checkInterval = setInterval(async () => {
      try {
        const res = await API.websiteStatus(jobId);
        if (!res.ok) {
          stopPolling();
          return;
        }
        const job = res.job;
        const status = $('#website-dl-status');
        const log = $('#website-log');
        const progressBar = $('#website-progress-bar');
        const btn = $('#website-url-btn');
        const dlLink = $('#website-download-link');

        switch (job.state) {
          case 'running':
            if (status) status.textContent = '⏳ Downloading website...';
            if (progressBar) {
              const pct = Math.min(job.progress || 0, 100);
              progressBar.style.width = pct + '%';
              progressBar.textContent = (job.progress || 0) + ' files';
            }
            break;
          case 'done':
            if (status) {
              status.innerHTML = '✅ Download complete!';
              status.style.color = 'var(--success)';
            }
            if (progressBar) {
              progressBar.style.width = '100%';
              progressBar.textContent = 'Done!';
            }
            if (dlLink) {
              dlLink.href = res.download_url;
              dlLink.style.display = 'inline-block';
              dlLink.textContent = '📦 Download ZIP';
            }
            btn.disabled = false;
            btn.textContent = '⬇ Download Website';
            MegaDL.App?.toast('✅ Website download complete!', 'success');
            stopPolling();
            break;
          case 'error':
            if (status) {
              status.textContent = `❌ ${job.error || 'Download failed'}`;
              status.style.color = 'var(--error)';
            }
            btn.disabled = false;
            btn.textContent = '⬇ Download Website';
            stopPolling();
            break;
        }

        // Fetch and show logs
        fetchLogs(jobId);
      } catch {
        // silently retry
      }
    }, 1500);
  }

  async function fetchLogs(jobId) {
    try {
      const res = await API.websiteLog(jobId);
      if (!res.ok) return;
      const log = $('#website-log');
      if (!log) return;
      const logs = res.logs || [];
      for (let i = knownLogLines; i < logs.length; i++) {
        const entry = logs[i];
        const text = entry.message || entry.text || '';
        if (text) {
          const line = document.createElement('div');
          line.className = 'log-line';
          line.textContent = text;
          log.appendChild(line);
        }
      }
      knownLogLines = logs.length;
      log.scrollTop = log.scrollHeight;
    } catch {
      // ignore
    }
  }

  function stopPolling() {
    if (checkInterval) {
      clearInterval(checkInterval);
      checkInterval = null;
    }
  }

  return { init, checkHealth };
})();
