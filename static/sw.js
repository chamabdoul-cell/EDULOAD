const CACHE = 'scholara-v4';
const SHELL = [
  '/', '/static/index.html', '/static/manifest.json',
  '/static/js/app.js', '/static/js/i18n.js', '/static/js/auth.js',
  '/static/js/api.js', '/static/js/download.js', '/static/js/search.js',
  '/static/js/collections.js', '/static/js/demo.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Never intercept API calls — always go to network
  if (url.pathname.startsWith('/api/')) return;
  // Mermaid CDN — never cache (large external resource)
  if (url.hostname.includes('cloudflare.com')) return;

  // Cache-first for static shell, network-first for everything else
  if (e.request.method !== 'GET') return;

  if (SHELL.includes(url.pathname) || url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }))
    );
  }
});
