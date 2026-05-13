/**
 * MegaDL — utils.js
 * Utility functions: formatting, security, DOM helpers, storage
 */

MegaDL.Utils = (() => {
  const cfg = MegaDL.Config;

  /* ── Storage helpers ─────────────────────────────────────── */
  const store = {
    get(key, fallback = null) {
      try {
        const v = localStorage.getItem(cfg.storagePrefix + key);
        return v !== null ? JSON.parse(v) : fallback;
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(cfg.storagePrefix + key, JSON.stringify(value)); }
      catch (e) { console.warn('Storage write failed:', e); }
    },
    remove(key) {
      localStorage.removeItem(cfg.storagePrefix + key);
    },
    clear() {
      Object.keys(localStorage)
        .filter(k => k.startsWith(cfg.storagePrefix))
        .forEach(k => localStorage.removeItem(k));
    },
  };

  /* ── Formatters ──────────────────────────────────────────── */

  function formatBytes(bytes, decimals = 1) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
  }

  function formatSpeed(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec <= 0) return '—';
    return formatBytes(bytesPerSec) + '/s';
  }

  function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
  }

  function formatETA(seconds) {
    if (!seconds || seconds <= 0 || seconds === Infinity) return '—';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds/60)}m ${Math.round(seconds%60)}s`;
    return `${Math.floor(seconds/3600)}h ${Math.floor((seconds%3600)/60)}m`;
  }

  function formatDate(ts) {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function formatRelativeTime(ts) {
    if (!ts) return '—';
    const diff = Date.now() - new Date(ts).getTime();
    const mins  = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days  = Math.floor(diff / 86400000);
    if (mins < 1)   return 'just now';
    if (mins < 60)  return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  }

  function formatNumber(n) {
    if (!n) return '—';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
    return String(n);
  }

  /* ── URL helpers ─────────────────────────────────────────── */

  function parseUrls(raw) {
    if (!raw) return [];
    // Split by newline, comma, or space — deduplicate, filter empties
    return [...new Set(
      raw.split(/[\n,\s]+/)
        .map(u => u.trim())
        .filter(u => u.length > 5 && (u.startsWith('http') || u.startsWith('ftp')))
    )];
  }

  function sanitizeUrl(url) {
    if (!url) return null;
    url = url.trim();
    // Block known ad/redirect domains
    try {
      const { hostname } = new URL(url);
      const blocked = cfg.blockedDomains.some(d => hostname.endsWith(d));
      if (blocked) return null;
    } catch { return null; }
    // Allow only http/https/ftp
    if (!/^(https?|ftp):\/\//i.test(url)) return null;
    // Basic path traversal guard
    if (/\.\.\/|\.\.\\/.test(url)) return null;
    return url;
  }

  function getDomainLabel(url) {
    try {
      const { hostname } = new URL(url);
      return hostname.replace('www.', '');
    } catch { return url.slice(0, 30); }
  }

  function getSiteIcon(url) {
    try {
      const { hostname } = new URL(url);
      const h = hostname.replace('www.', '');
      const icons = {
        'youtube.com': '▶️', 'youtu.be': '▶️',
        'tiktok.com': '🎵',
        'instagram.com': '📸',
        'twitter.com': '🐦', 'x.com': '🐦',
        'facebook.com': '👥',
        'vimeo.com': '🎞️',
        'soundcloud.com': '🎧',
        'twitch.tv': '🎮',
        'reddit.com': '🤖',
        'mega.nz': '☁️',
        'mediafire.com': '🔥',
        'dropbox.com': '📦',
        'drive.google.com': '🟡',
      };
      return Object.entries(icons).find(([k]) => h.includes(k))?.[1] || '🌐';
    } catch { return '🌐'; }
  }

  function getFileIcon(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    return cfg.fileIcons[ext] || '📄';
  }

  /* ── DOM helpers ─────────────────────────────────────────── */

  const $ = id => document.getElementById(id);

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return [...root.querySelectorAll(selector)];
  }

  function el(tag, attrs = {}, ...children) {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'class') e.className = v;
      else if (k === 'html') e.innerHTML = v;
      else if (k === 'text') e.textContent = v;
      else e.setAttribute(k, v);
    });
    children.forEach(c => {
      if (typeof c === 'string') e.appendChild(document.createTextNode(c));
      else if (c) e.appendChild(c);
    });
    return e;
  }

  function setHTML(selector, html) {
    const node = typeof selector === 'string' ? document.getElementById(selector) : selector;
    if (node) node.innerHTML = html;
  }

  function setText(selector, text) {
    const node = typeof selector === 'string' ? document.getElementById(selector) : selector;
    if (node) node.textContent = text;
  }

  function show(el, display = 'flex') {
    const node = typeof el === 'string' ? document.getElementById(el) : el;
    if (node) node.style.display = display;
  }

  function hide(el) {
    const node = typeof el === 'string' ? document.getElementById(el) : el;
    if (node) node.style.display = 'none';
  }

  function toggle(el, condition, display = 'flex') {
    condition ? show(el, display) : hide(el);
  }

  /* ── Ripple effect ───────────────────────────────────────── */

  function addRipple(element) {
    element.addEventListener('pointerdown', e => {
      const rect = element.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 2;
      const x = e.clientX - rect.left - size / 2;
      const y = e.clientY - rect.top - size / 2;
      const ripple = document.createElement('span');
      ripple.className = 'ripple-wave';
      ripple.style.cssText = `width:${size}px;height:${size}px;left:${x}px;top:${y}px`;
      element.classList.add('ripple-container');
      element.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove());
    });
  }

  /* ── Haptic feedback ─────────────────────────────────────── */

  function haptic(type = 'light') {
    if (!store.get('haptic', true)) return;
    if (!navigator.vibrate) return;
    const patterns = { light: [10], medium: [25], heavy: [50], success: [10, 50, 10], error: [50, 30, 50] };
    navigator.vibrate(patterns[type] || patterns.light);
  }

  /* ── Clipboard ───────────────────────────────────────────── */

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    }
  }

  async function readClipboard() {
    try {
      return await navigator.clipboard.readText();
    } catch { return null; }
  }

  /* ── Safe filename ───────────────────────────────────────── */

  function safeFilename(name) {
    return (name || 'download')
      .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
      .replace(/\s+/g, '_')
      .replace(/_{2,}/g, '_')
      .slice(0, 200);
  }

  /* ── Debounce / Throttle ─────────────────────────────────── */

  function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function throttle(fn, limit = 200) {
    let last = 0;
    return (...args) => {
      const now = Date.now();
      if (now - last >= limit) { last = now; fn(...args); }
    };
  }

  /* ── UUID ────────────────────────────────────────────────── */

  function uuid() {
    return crypto.randomUUID?.() ||
      'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
      });
  }

  /* ── Speed color class ───────────────────────────────────── */

  function speedClass(bytesPerSec) {
    if (bytesPerSec > 5 * 1024 * 1024) return 'speed-fast';
    if (bytesPerSec > 500 * 1024)      return 'speed-medium';
    return 'speed-slow';
  }

  /* ── Progress ring SVG ───────────────────────────────────── */

  function buildProgressRing(percent, size = 36, color = 'var(--accent)') {
    const r = (size - 4) / 2;
    const circumference = 2 * Math.PI * r;
    const offset = circumference - (percent / 100) * circumference;
    return `
      <div class="progress-ring" style="width:${size}px;height:${size}px">
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
          <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none"
            stroke="rgba(255,255,255,0.08)" stroke-width="3"/>
          <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none"
            stroke="${color}" stroke-width="3" stroke-linecap="round"
            stroke-dasharray="${circumference}"
            stroke-dashoffset="${offset}"
            class="progress-ring-circle"
            style="transform:rotate(-90deg);transform-origin:center"/>
        </svg>
        <span class="progress-ring-text">${Math.round(percent)}%</span>
      </div>
    `;
  }

  /* ── Input sanitizer (XSS guard) ────────────────────────── */

  function escapeHTML(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /* ── Build yt-dlp command preview ────────────────────────── */

  function buildYtdlpCommand(url, opts = {}) {
    const parts = ['yt-dlp'];

    // Quality/format selection
    if (opts.quality === 'mp3') {
      parts.push('-x', '--audio-format mp3');
    } else if (opts.quality === 'm4a') {
      parts.push('-x', '--audio-format m4a');
    } else if (opts.quality && opts.quality !== 'best') {
      parts.push(`-f "bestvideo[height<=${opts.quality}]+bestaudio/best[height<=${opts.quality}]"`);
    } else {
      parts.push('-f "bestvideo+bestaudio/best"');
    }

    // Merge format
    if (opts.mergeFormat && opts.quality !== 'mp3' && opts.quality !== 'm4a') {
      parts.push(`--merge-output-format ${opts.mergeFormat || 'mp4'}`);
    }

    // Concurrent fragments
    if (opts.concurrentFrag > 1) {
      parts.push(`--concurrent-fragments ${opts.concurrentFrag}`);
    }

    // Retries
    if (opts.retries) parts.push(`--retries ${opts.retries}`);
    if (opts.fragRetries) parts.push(`--fragment-retries ${opts.fragRetries}`);

    // Speed limit
    if (opts.speedLimit && opts.speedLimit > 0) {
      parts.push(`--limit-rate ${opts.speedLimit}K`);
    }

    // Proxy
    if (opts.proxy) parts.push(`--proxy ${opts.proxy}`);

    // Media embedding
    if (opts.embedThumb) parts.push('--embed-thumbnail');
    if (opts.embedMeta)  parts.push('--add-metadata');
    if (opts.embedSubs)  parts.push(`--embed-subs --sub-langs ${opts.subLang || 'en'}`);

    // SponsorBlock
    if (opts.sponsorblock) parts.push('--sponsorblock-mark all');

    // Cookies
    if (opts.cookies) parts.push('--cookies cookies.txt');

    // Archive
    if (opts.archiveMode) parts.push('--download-archive downloads/archive.txt');

    // Verbose
    if (opts.verbose) parts.push('--verbose');

    // Custom args
    if (opts.customArgs) parts.push(opts.customArgs.trim());

    // Output template
    parts.push('-o "%(title)s.%(ext)s"');

    // URL (last)
    parts.push(`"${url}"`);

    return parts.join(' \\\n  ');
  }

  /* ─── Public API ─────────────────────────────────────────── */
  return {
    store,
    formatBytes, formatSpeed, formatDuration, formatETA,
    formatDate, formatRelativeTime, formatNumber,
    parseUrls, sanitizeUrl, getDomainLabel, getSiteIcon, getFileIcon,
    $, qs, qsa, el, setHTML, setText, show, hide, toggle,
    addRipple, haptic,
    copyToClipboard, readClipboard,
    safeFilename, debounce, throttle, uuid,
    speedClass, buildProgressRing, escapeHTML,
    buildYtdlpCommand,
  };
})();
