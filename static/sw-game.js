/**
 * Minimal service worker — caches bundled game shell assets for faster mobile reload.
 */
var CACHE = 'ano-game-shell-v2';
var ASSETS = [
    '/static/style.css',
    '/static/game-shell.js',
    '/static/province-base.js',
    '/static/manifest.webmanifest',
    '/static/images/titleimage.png',
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE).then(function (cache) {
            return cache.addAll(ASSETS).catch(function () {
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
    if (!ASSETS.some(function (a) {
        return url.indexOf(a) !== -1;
    })) {
        return;
    }
    event.respondWith(
        caches.match(event.request).then(function (cached) {
            return (
                cached ||
                fetch(event.request).then(function (res) {
                    if (res && res.ok) {
                        var copy = res.clone();
                        caches.open(CACHE).then(function (cache) {
                            cache.put(event.request, copy);
                        });
                    }
                    return res;
                })
            );
        })
    );
});
