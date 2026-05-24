/**
 * Minimal service worker — offline shell only (never cache-bust CSS/JS here).
 * CSS/JS must always hit the network so deploys reach players immediately.
 */
var CACHE = 'ano-game-shell-v3';
var OFFLINE_ASSETS = [
    '/static/manifest.webmanifest',
    '/static/images/titleimage.png',
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE).then(function (cache) {
            return cache.addAll(OFFLINE_ASSETS).catch(function () {
                return undefined;
            });
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.filter(function (k) {
                    return k.startsWith('ano-game-shell-') && k !== CACHE;
                }).map(function (k) {
                    return caches.delete(k);
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', function (event) {
    var url = event.request.url;
    if (!OFFLINE_ASSETS.some(function (a) {
        return url.indexOf(a) !== -1;
    })) {
        return;
    }
    event.respondWith(
        fetch(event.request).catch(function () {
            return caches.match(event.request);
        })
    );
});
