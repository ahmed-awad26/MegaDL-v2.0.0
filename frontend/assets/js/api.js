/**
 * MegaDL — api.js
 * Smart Backend Switcher: Auto-detects Python/Flask vs PHP backend.
 * Provides unified API interface regardless of which backend is active.
 */

MegaDL.API = (() => {
  const { Config, Utils } = MegaDL;
  const { store } = Utils;

  /* ── Backend state ───────────────────────────────────────── */
  let activeBackend = null; // 'python' | 'php' | null
  let pythonBaseUrl = Config.pythonBackendUrl;
  let phpBasePath   = Config.phpBackendPath;
  let detectPromise = null;

  /* ── Backend Detection ───────────────────────────────────── */

  async function detectBackend() {
    if (detectPromise) return detectPromise;

    detectPromise = (async () => {
      // Try Python/Flask first
      try {
        const res = await fetch(`${pythonBaseUrl}/api/ping`, {
          signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.ok) {
            activeBackend = 'python';
            store.set('last_backend', 'python');
            return 'python';
          }
        }
      } catch { /* fall through */ }

      // Try PHP backend
      try {
        const res = await fetch(`${phpBasePath}/ping.php`, {
          signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.ok) {
            activeBackend = 'php';
            store.set('last_backend', 'php');
            return 'php';
          }
        }
      } catch { /* fall through */ }

      // Use cached last working backend
      const cached = store.get('last_backend');
      if (cached) {
        activeBackend = cached;
        return cached;
      }

      activeBackend = null;
      return null;
    })();

    return detectPromise;
  }

  function getBackend() { return activeBackend; }

  function resetDetection() {
    detectPromise = null;
    activeBackend = null;
  }

  /* ── Core fetch wrapper ──────────────────────────────────── */

  async function apiFetch(path, options = {}) {
    if (!activeBackend) await detectBackend();

    const base = activeBackend === 'python'
      ? `${pythonBaseUrl}${path}`
      : `${phpBasePath}${path}.php`;

    const defaults = {
      headers: { 'Content-Type': 'application/json', 'X-MegaDL-Client': '1' },
      signal: AbortSignal.timeout(options.timeout || 30000),
    };

    const fetchOpts = { ...defaults, ...options };
    if (fetchOpts.body && typeof fetchOpts.body === 'object') {
      fetchOpts.body = JSON.stringify(fetchOpts.body);
    }

    const res = await fetch(base, fetchOpts);
    const contentType = res.headers.get('Content-Type') || '';

    if (!res.ok) {
      const errBody = contentType.includes('json')
        ? await res.json().catch(() => ({}))
        : { error: await res.text().catch(() => 'Request failed') };
      throw new APIError(errBody.error || `HTTP ${res.status}`, res.status, errBody);
    }

    if (contentType.includes('json')) return res.json();
    return res.text();
  }

  /* ── Custom Error ────────────────────────────────────────── */

  class APIError extends Error {
    constructor(message, status, data = {}) {
      super(message);
      this.name  = 'APIError';
      this.status = status;
      this.data  = data;
    }
  }

  /* ══════════════════════════════════════════════════════════
     API METHODS
     ══════════════════════════════════════════════════════════ */

  /* ── Ping / Health ───────────────────────────────────────── */

  async function ping() {
    return apiFetch('/api/ping');
  }

  /* ── Video Info Extraction ───────────────────────────────── */

  async function fetchInfo(url, opts = {}) {
    Utils.sanitizeUrl(url); // throws if blocked
    return apiFetch('/api/info', {
      method: 'POST',
      body: { url, opts },
      timeout: 45000,
    });
  }

  /* ── Start Download ──────────────────────────────────────── */

  async function startDownload(url, opts = {}) {
    const safeUrl = Utils.sanitizeUrl(url);
    if (!safeUrl) throw new Error('URL blocked or invalid');
    return apiFetch('/api/download', {
      method: 'POST',
      body: { url: safeUrl, ...opts },
    });
  }

  /* ── Batch Download ──────────────────────────────────────── */

  async function startBatch(urls, opts = {}) {
    const safeUrls = urls
      .map(u => Utils.sanitizeUrl(u))
      .filter(Boolean);
    if (!safeUrls.length) throw new Error('No valid URLs');
    return apiFetch('/api/batch', {
      method: 'POST',
      body: { urls: safeUrls, ...opts },
    });
  }

  /* ── Jobs ────────────────────────────────────────────────── */

  async function getJobs(filter = {}) {
    const params = new URLSearchParams(filter).toString();
    return apiFetch(`/api/jobs${params ? '?' + params : ''}`);
  }

  async function getJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}`);
  }

  async function pauseJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}/pause`, { method: 'POST' });
  }

  async function resumeJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}/resume`, { method: 'POST' });
  }

  async function cancelJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
  }

  async function retryJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
  }

  async function deleteJob(jobId) {
    return apiFetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
  }

  /* ── Bulk job control ────────────────────────────────────── */

  async function pauseAll()  { return apiFetch('/api/jobs/pause-all',  { method: 'POST' }); }
  async function resumeAll() { return apiFetch('/api/jobs/resume-all', { method: 'POST' }); }
  async function cancelAll() { return apiFetch('/api/jobs/cancel-all', { method: 'POST' }); }

  /* ── History ─────────────────────────────────────────────── */

  async function getHistory(limit = 100) {
    return apiFetch(`/api/history?limit=${limit}`);
  }

  async function clearHistory() {
    return apiFetch('/api/history', { method: 'DELETE' });
  }

  /* ── Archive ─────────────────────────────────────────────── */

  async function getArchive() {
    return apiFetch('/api/archive');
  }

  async function clearArchive() {
    return apiFetch('/api/archive', { method: 'DELETE' });
  }

  /* ── Favorites ───────────────────────────────────────────── */

  async function getFavorites() {
    return apiFetch('/api/favorites');
  }

  async function addFavorite(jobId) {
    return apiFetch('/api/favorites', { method: 'POST', body: { job_id: jobId } });
  }

  async function removeFavorite(jobId) {
    return apiFetch(`/api/favorites/${jobId}`, { method: 'DELETE' });
  }

  /* ── Files ───────────────────────────────────────────────── */

  async function listFiles(path = '') {
    return apiFetch(`/api/files?path=${encodeURIComponent(path)}`);
  }

  async function deleteFile(path) {
    return apiFetch('/api/files/delete', { method: 'POST', body: { path } });
  }

  async function renameFile(oldPath, newName) {
    return apiFetch('/api/files/rename', {
      method: 'POST',
      body: { path: oldPath, name: newName },
    });
  }

  /* ── Settings ────────────────────────────────────────────── */

  async function getSettings() {
    return apiFetch('/api/settings');
  }

  async function saveSettings(settings) {
    return apiFetch('/api/settings', {
      method: 'POST',
      body: settings,
    });
  }

  /* ── Logs ────────────────────────────────────────────────── */

  async function getLogs(filter = {}) {
    const params = new URLSearchParams(filter).toString();
    return apiFetch(`/api/logs${params ? '?' + params : ''}`);
  }

  async function clearLogs() {
    return apiFetch('/api/logs', { method: 'DELETE' });
  }

  /* ── Telegram ───────────────────────────────────────────── */

  async function tgStatus() {
    return apiFetch('/api/tg/status');
  }

  async function tgSendCode(phone) {
    return apiFetch('/api/tg/send-code', { method: 'POST', body: { phone } });
  }

  async function tgSignIn(phone, code, password = '') {
    return apiFetch('/api/tg/sign-in', { method: 'POST', body: { phone, code, password } });
  }

  async function tgSignInPassword(password) {
    return apiFetch('/api/tg/sign-in-password', { method: 'POST', body: { password } });
  }

  async function tgLogout() {
    return apiFetch('/api/tg/logout', { method: 'POST' });
  }

  async function tgDialogs() {
    return apiFetch('/api/tg/dialogs');
  }

  async function tgMessages(dialogId, limit = 100, offsetId = 0, mediaOnly = '0') {
    const params = new URLSearchParams({ dialog_id: dialogId, limit, offset_id: offsetId, media_only: mediaOnly });
    return apiFetch(`/api/tg/messages?${params}`);
  }

  async function tgDownload(dialogId, msgIds, mode = 'account', botToken = '', dlFolder = '') {
    return apiFetch('/api/tg/download', {
      method: 'POST',
      body: { dialog_id: dialogId, msg_ids: msgIds, mode, bot_token: botToken, dl_folder: dlFolder },
      timeout: 60000,
    });
  }

  async function tgBotDownload(botToken, dlFolder = '') {
    return apiFetch('/api/tg/bot-download', {
      method: 'POST',
      body: { bot_token: botToken, dl_folder: dlFolder },
      timeout: 120000,
    });
  }

  /* ── Dependencies / Doctor ────────────────────────────────── */

  async function checkDependencies() {
    return apiFetch('/api/dependencies/check', { timeout: 15000 });
  }

  async function installDependency(name) {
    return apiFetch('/api/dependencies/install', {
      method: 'POST',
      body: { name },
      timeout: 120000,
    });
  }

  /* ── Failed Links ──────────────────────────────────────────── */

  async function getFailedLinks(jobId = '') {
    const params = jobId ? `?job_id=${encodeURIComponent(jobId)}` : '';
    return apiFetch(`/api/failed-links${params}`);
  }

  async function clearFailedLinks(jobId = '') {
    return apiFetch('/api/failed-links', {
      method: 'DELETE',
      body: { job_id: jobId },
    });
  }

  /* ── YouTube API key validation ───────────────────────────── */

  async function validateYoutubeKey(apiKey) {
    return apiFetch('/api/settings/validate-youtube-key', {
      method: 'POST',
      body: { api_key: apiKey },
      timeout: 10000,
    });
  }

  /* ── Diagnostics ─────────────────────────────────────────── */

  async function runDiagnostics() {
    return apiFetch('/api/diagnostics', { timeout: 20000 });
  }

  /* ── Stats ───────────────────────────────────────────────── */

  async function getStats() {
    return apiFetch('/api/stats');
  }

  /* ── Job logs (live) ─────────────────────────────────────── */

  async function getJobLogs(jobId) {
    return apiFetch(`/api/jobs/${jobId}/logs`);
  }

  /* ── Download URL for completed file ─────────────────────── */

  function getDownloadUrl(jobId) {
    if (activeBackend === 'python') {
      return `${pythonBaseUrl}/api/jobs/${jobId}/download`;
    }
    return `${phpBasePath}/files/download.php?job_id=${jobId}`;
  }

  /* ── Telegram credential validation ──────────────────────── */

  /* ── Stream URL for media player ─────────────────────────── */

  function getStreamUrl(filePath) {
    if (activeBackend === 'python') {
      return `${pythonBaseUrl}/api/files/stream/${encodeURIComponent(filePath)}`;
    }
    return getDownloadUrl(filePath);
  }

  /* ── YouTube channel playlists ───────────────────────────── */

  async function getChannelPlaylists(url) {
    return apiFetch('/api/youtube/playlists', {
      method: 'POST',
      body: { url },
      timeout: 20000,
    });
  }

  async function tgValidateCredentials(apiId, apiHash) {
    return apiFetch('/api/tg/validate-credentials', {
      method: 'POST',
      body: { api_id: apiId, api_hash: apiHash },
      timeout: 15000,
    });
  }

  /* ── yt-dlp update ────────────────────────────────────────── */

  /* ── Telegram history ─────────────────────────────────────── */

  async function tgHistory(limit = 50) {
    return apiFetch(`/api/tg/history?limit=${limit}`, { timeout: 10000 });
  }

  async function tgCurrentFile() {
    return apiFetch('/api/tg/current-file', { timeout: 5000 });
  }

  async function tgScanChat(dialogId, mediaTypes, limitPerType = {}) {
    return apiFetch('/api/tg/scan-chat', {
      method: 'POST',
      body: { dialog_id: dialogId, media_types: mediaTypes, limit_per_type: limitPerType },
      timeout: 120000,
    });
  }

  async function tgBotScores() {
    return apiFetch('/api/tg/bot-scores', { timeout: 10000 });
  }

  async function tgCredsStatus() {
    return apiFetch('/api/tg/creds-status', { timeout: 5000 });
  }

  /* ── Telegram Bot Pool ─────────────────────────────────────── */

  async function tgBotPoolList() {
    return apiFetch('/api/tg/bot-pool', { timeout: 5000 });
  }

  async function tgBotPoolAdd(token) {
    return apiFetch('/api/tg/bot-pool/add', {
      method: 'POST',
      body: { token },
      timeout: 10000,
    });
  }

  async function tgBotPoolRemove(token) {
    return apiFetch('/api/tg/bot-pool/remove', {
      method: 'POST',
      body: { token },
      timeout: 10000,
    });
  }

  async function tgBotPoolStatus() {
    return apiFetch('/api/tg/bot-pool/status', { timeout: 15000 });
  }

  async function tgBotPoolDownloadAll(botToken, dlFolder = '') {
    return apiFetch('/api/tg/bot-pool/download-all', {
      method: 'POST',
      body: { bot_token: botToken, dl_folder: dlFolder },
      timeout: 120000,
    });
  }

  /* ── YouTube features ──────────────────────────────────────── */

  async function ytUncategorized(channelUrl) {
    return apiFetch(`/api/ytdlp/uncategorized?channel_url=${encodeURIComponent(channelUrl)}`, { timeout: 60000 });
  }

  async function ytChannelUploads(channelId, limit = 200) {
    return apiFetch(`/api/ytdlp/channel-uploads?channel_id=${channelId}&limit=${limit}`, { timeout: 60000 });
  }

  async function ytLatestReport() {
    return apiFetch('/api/ytdlp/latest-report', { timeout: 10000 });
  }

  async function ytLatestReportSave(channelId, videoId, uploadDate) {
    return apiFetch('/api/ytdlp/latest-report/save', {
      method: 'POST',
      body: { channel_id: channelId, video_id: videoId, upload_date: uploadDate },
      timeout: 10000,
    });
  }

  async function ytdlpCheckUpdate() {
    return apiFetch('/api/ytdlp/check-update', { timeout: 30000 });
  }

  async function ytdlpUpdate() {
    return apiFetch('/api/ytdlp/update', { method: 'POST', timeout: 120000 });
  }

  /* ── URL Cleaning & File Hosting ───────────────────────── */

  async function urlClean(urls, resolveShort = true) {
    if (typeof urls === 'string') urls = [urls];
    return apiFetch('/api/url/clean', {
      method: 'POST',
      body: { urls, resolve_short: resolveShort },
      timeout: 30000,
    });
  }

  async function urlInfo(urls) {
    if (typeof urls === 'string') urls = [urls];
    return apiFetch('/api/url/info', {
      method: 'POST',
      body: { urls },
      timeout: 10000,
    });
  }

  async function urlPreview(url) {
    return apiFetch('/api/url/preview', {
      method: 'POST',
      body: { url },
      timeout: 15000,
    });
  }

  async function urlPreviewContent(url) {
    return apiFetch('/api/url/preview-content', {
      method: 'POST',
      body: { url },
      timeout: 20000,
    });
  }

  async function filehostDownload(url) {
    return apiFetch('/api/filehost/download', {
      method: 'POST',
      body: { url },
      timeout: 10000,
    });
  }

  /* ── Expose ──────────────────────────────────────────────── */
  return {
    detectBackend, getBackend, resetDetection,
    ping,
    fetchInfo,
    startDownload, startBatch,
    getJobs, getJob,
    pauseJob, resumeJob, cancelJob, retryJob,
    pauseAll, resumeAll, cancelAll,
    getHistory, clearHistory,
    getArchive, clearArchive,
    getFavorites, addFavorite, removeFavorite,
    listFiles, deleteFile, renameFile,
    getSettings, saveSettings,
    getLogs, clearLogs,
    runDiagnostics,
    getStats,
    getJobLogs,
    getDownloadUrl, getStreamUrl,
    getChannelPlaylists,
    tgValidateCredentials,
    validateYoutubeKey,
    checkDependencies, installDependency,
    tgStatus, tgSendCode, tgSignIn, tgSignInPassword, tgLogout,
    tgDialogs, tgMessages, tgDownload, tgBotDownload,
    tgHistory, tgCurrentFile,
    tgScanChat, tgBotScores, tgCredsStatus,
    tgBotPoolList, tgBotPoolAdd, tgBotPoolRemove, tgBotPoolStatus, tgBotPoolDownloadAll,
    ytUncategorized, ytChannelUploads, ytLatestReport, ytLatestReportSave,
    getFailedLinks, clearFailedLinks,
    ytdlpCheckUpdate, ytdlpUpdate,
    urlClean, urlInfo, urlPreview, urlPreviewContent, filehostDownload,
    APIError,
  };
})();



async function openDownloadedFile(jobId) {
    try {
        const res = await fetch(`/api/jobs/${jobId}/download`);
        const data = await res.json();

        if (data.ok && data.file && data.file.path) {
            alert("File saved to:\n" + data.file.path);
            return;
        }

        window.location.href = `/api/jobs/${jobId}/download`;
    } catch (e) {
        console.error(e);
        window.location.href = `/api/jobs/${jobId}/download`;
    }
}
