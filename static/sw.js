// Only public static assets are cached. Never cache forms, sessions, CNIC or dashboard.
const CACHE = 'asasa-shell-ui-21';
const ASSETS = ['/static/style.css?v=ui-21','/static/app.js?v=ui-21','/static/icon-192.png','/static/icon-512.png','/static/offline.html'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('asasa-shell-') && k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (ASSETS.includes(url.pathname + url.search)) event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
  else if (event.request.mode === 'navigate') event.respondWith(fetch(event.request).catch(() => caches.match('/static/offline.html')));
});
