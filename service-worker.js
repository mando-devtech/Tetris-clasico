'use strict';

const CACHE_NAME = 'tetris-clasico-v1';
const CACHE_PREFIX = 'tetris-clasico-';

const PRECACHE_URLS = [
  './',
  './index.html',
  './styles.css',
  './manifest.webmanifest',
  './js/constants.js',
  './js/audio.js',
  './js/engine.js',
  './js/renderer.js',
  './js/input.js',
  './js/main.js',
  './icons/icon.svg',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-512-maskable.png',
  './icons/apple-touch-icon.png'
];

if (typeof self !== 'undefined' && typeof self.addEventListener === 'function') {
  self.addEventListener('install', function (event) {
    event.waitUntil(
      caches.open(CACHE_NAME).then(function (cache) {
        return Promise.all(
          PRECACHE_URLS.map(function (url) {
            var request = new Request(url, { cache: 'reload' });
            return fetch(request)
              .then(function (response) {
                if (
                  response &&
                  response.ok &&
                  response.status === 200 &&
                  response.type === 'basic' &&
                  !response.redirected
                ) {
                  return cache.put(url, response);
                }
                if (response && response.body && typeof response.body.cancel === 'function') {
                  return Promise.resolve(response.body.cancel()).catch(function () {
                    return null;
                  });
                }
                return null;
              })
              .catch(function () {
                return null;
              });
          })
        );
      }).then(function () {
        return self.skipWaiting();
      })
    );
  });

  self.addEventListener('activate', function (event) {
    event.waitUntil(
      caches.keys().then(function (keys) {
        return Promise.all(
          keys.map(function (key) {
            if (key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME) {
              return caches.delete(key);
            }
            return Promise.resolve(false);
          })
        );
      }).then(function () {
        return self.clients.claim();
      })
    );
  });

  self.addEventListener('fetch', function (event) {
    var request = event.request;
    if (request.method !== 'GET') {
      return;
    }
    if (request.cache === 'only-if-cached' && request.mode !== 'same-origin') {
      return;
    }

    var url = new URL(request.url);
    if (url.origin !== self.location.origin) {
      return;
    }
    if (
      self.registration &&
      self.registration.scope &&
      url.href.indexOf(self.registration.scope) !== 0
    ) {
      return;
    }

    event.respondWith(
      caches.match(request, { cacheName: CACHE_NAME }).then(function (cached) {
        if (cached) {
          return cached;
        }

        return fetch(request)
          .then(function (response) {
            if (
              response &&
              response.ok &&
              response.status === 200 &&
              response.type === 'basic' &&
              !response.redirected
            ) {
              var responseToCache = response.clone();
              return caches.open(CACHE_NAME)
                .then(function (cache) {
                  return cache.put(request, responseToCache);
                })
                .catch(function () {
                  return null;
                })
                .then(function () {
                  return response;
                });
            }
            return response;
          })
          .catch(function () {
            if (request.mode === 'navigate') {
              return caches.match('./index.html', { cacheName: CACHE_NAME }).then(function (fallback) {
                if (fallback) {
                  return fallback;
                }
                return caches.match('./', { cacheName: CACHE_NAME }).then(function (rootFallback) {
                  return rootFallback || Response.error();
                });
              });
            }
            return Response.error();
          });
      })
    );
  });
}
