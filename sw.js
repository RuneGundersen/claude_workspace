// OVMS Service Worker — offline caching & PWA support

const CACHE_NAME = 'ovms-v2';
const ASSETS = [
  './',
  './index.html',
  './style.css',
  './config.js',
  './ovms.js',
  './logger.js',
  './history.js',
  './notifications.js',
  './charts.js',
  './app.js',
  './manifest.json',
  './icons/icon.svg',
  'https://unpkg.com/mqtt/dist/mqtt.min.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(c => c.addAll(ASSETS.map(u => new Request(u, { cache: 'reload' }))))
      .catch(() => {}) // don't fail install if CDN assets are unavailable
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  // Network first for MQTT/broker, cache first for app shell
  const url = e.request.url;
  if (url.includes('hivemq') || url.includes('mqtt')) return;

  e.respondWith(
    caches.match(e.request).then(cached => {
      const network = fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
