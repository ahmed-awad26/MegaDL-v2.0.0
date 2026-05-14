/**
 * MegaDL — service-worker.js
 * Offline-first PWA: caches app shell, handles fetch strategy.
 */

const CACHE_NAME    = 'megadl-v2.0.0';
const DYNAMIC_CACHE = 'megadl-dynamic-v2.0.0';

/* ── App Shell assets to precache ────────────────────────── */
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/assets/css/main.css',
  '/assets/css/animations.css',
  '/assets/css/components.css',
  '/assets/css/pages.css',
  '/assets/js/config.js',
  '/assets/js/utils.js',
  '/assets/js/api.js',
  '/assets/js/router.js',
  '/assets/js/jobs.js',
  '/assets/js/downloader.js',
  '/assets/js/settings.js',
  '/assets/js/files.js',
  '/assets/js/telegram.js',
  '/assets/js/website.js',
  '/assets/js/app.js',
  'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap',
];

/* ── Install: precache app shell ────────────────────────── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_URLS.map(url => new Request(url, { cache: 'reload' })))
        .catch(err => console.warn('[SW] Precache partial fail:', err));
    }).then(() => self.skipWaiting())
  );
});

/* ── Activate: clean old caches ─────────────────────────── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== DYNAMIC_CACHE)
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch strategy: Network-first for API, Cache-first for assets ── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Always network-first for API calls
  if (url.pathname.startsWith('/api/') || url.port === '5000') {
    event.respondWith(networkFirst(request));
    return;
  }

  // Cache-first for static assets
  if (request.method === 'GET') {
    event.respondWith(cacheFirst(request));
  }
});

/* ── Cache-first strategy ────────────────────────────────── */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('<div style="font-family:sans-serif;padding:20px;text-align:center"><h2>MegaDL</h2><p>Offline — cached content only</p></div>',
      { headers: { 'Content-Type': 'text/html' } });
  }
}

/* ── Network-first strategy ──────────────────────────────── */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: 'offline', ok: false }),
      { headers: { 'Content-Type': 'application/json' }, status: 503 });
  }
}

/* ── Background sync for queued downloads ────────────────── */
self.addEventListener('sync', event => {
  if (event.tag === 'sync-downloads') {
    event.waitUntil(syncPendingDownloads());
  }
});

async function syncPendingDownloads() {
  // This would pull from IndexedDB and retry pending downloads
  console.log('[SW] Background sync: checking pending downloads');
}

/* ── Push notifications ──────────────────────────────────── */
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || 'MegaDL', {
      body: data.body || 'Download update',
      icon: '/assets/icons/icon-192.png',
      badge: '/assets/icons/icon-72.png',
      data: data,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/'));
});
