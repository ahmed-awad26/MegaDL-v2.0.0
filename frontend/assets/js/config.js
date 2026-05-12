/**
 * MegaDL — config.js
 * Central configuration: backend URLs, constants, defaults
 */

window.MegaDL = window.MegaDL || {};

MegaDL.Config = {
  version: '2.0.0',

  /* ── Backend detection endpoints ── */
  pythonBackendUrl: 'http://localhost:5000',
  phpBackendPath:   'backend-php/api',

  /* ── Polling intervals ── */
  jobPollInterval:  3000,   // ms between job status polls (SSE is primary)
  statsPollInterval: 10000,  // ms between stats refresh

  /* ── Download defaults ── */
  defaults: {
    quality:        'best',
    format:         'mp4',
    mergeFormat:    'mp4',
    maxParallel:    3,
    retries:        3,
    fragRetries:    5,
    concurrentFrag: 4,
    timeout:        30,
    speedLimit:     0,
    subLang:        'en',
    autoRetry:      true,
    autoResume:     true,
    embedThumb:     true,
    embedMeta:      true,
    embedSubs:      false,
    sponsorblock:   false,
    verbose:        false,
    archiveMode:    true,
    debugMode:      false,
  },

  /* ── Supported sites (for UI badge display) ── */
  supportedSites: [
    'youtube.com', 'youtu.be',
    'tiktok.com',
    'instagram.com',
    'twitter.com', 'x.com',
    'facebook.com',
    'vimeo.com',
    'reddit.com',
    'soundcloud.com',
    'twitch.tv',
    'dailymotion.com',
    'mega.nz',
    'mediafire.com',
    'dropbox.com',
    'drive.google.com',
    'onedrive.live.com',
    'gofile.io',
    'pixeldrain.com',
  ],

  /* ── Blocked / suspicious URL patterns ── */
  blockedDomains: [
    'doubleclick.net',
    'adnxs.com',
    'propellerads.com',
    'ouo.io',
    'linkvertise.com',
    'bc.vc',
    'exe.io',
    'adf.ly',
    'shorte.st',
  ],

  /* ── File type icons map ── */
  fileIcons: {
    mp4:  '🎬', mkv: '🎬', webm: '🎬', avi: '🎬', mov: '🎬',
    mp3:  '🎵', m4a: '🎵', opus: '🎵', ogg: '🎵', wav: '🎵', flac: '🎵',
    jpg:  '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', webp: '🖼️',
    pdf:  '📄', txt: '📝', zip: '🗜️', tar: '🗜️', gz: '🗜️',
  },

  /* ── Quality display labels ── */
  qualityLabels: {
    best: '🎯 Best',
    2160: '4K · 2160p',
    1440: '2K · 1440p',
    1080: 'FHD · 1080p',
    720:  'HD · 720p',
    480:  'SD · 480p',
    360:  '360p',
    mp3:  '🎵 MP3 Audio',
    m4a:  '🎵 M4A Audio',
  },

  /* ── Local storage key prefix ── */
  storagePrefix: 'megadl_',
};
