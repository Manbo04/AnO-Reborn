/**
 * Minimal service worker — caches shell CSS/JS for faster mobile reload.
 */
var CACHE = 'ano-game-shell-v1';
var ASSETS = [
    '/static/css/tokens.css',
    '/static/css/game-shell.css',
    '/static/css/province-base.css',
    '/static/game-shell.js',
    '/static/manifest.webmanifest',
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE).then(function (cache) {
            return cache.addAll(ASSETS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
    var url = event.request.url;
    if (ASSETS.some(function (a) { return url.indexOf(a) !== -1; })) {
        event.respondWith(
            caches.match(event.request).then(function (cached) {
                return cached || fetch(event.request);
            })
        );
    }
});
