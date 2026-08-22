{% load static %}
const CACHE_NAME = "nyansa-shell-v1";
const STATIC_URL = "{{ static_url }}";

const PRECACHE_URLS = [
    "{% static 'css/style.css' %}",
    "{% static 'js/navigation.js' %}",
    "{% static 'js/offline-queue.js' %}",
    "{% static 'js/low-data-mode.js' %}",
    "{% static 'images/logo.svg' %}",
    "{% static 'images/favicon.svg' %}",
    "{% static 'manifest.json' %}",
    "{% static 'offline.html' %}"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    return response;
                })
                .catch(() =>
                    caches.match(request).then(
                        (cached) => cached || caches.match("{% static 'offline.html' %}")
                    )
                )
        );
        return;
    }

    const url = new URL(request.url);
    if (url.pathname.startsWith(STATIC_URL)) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) {
                    return cached;
                }
                return fetch(request).then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    return response;
                });
            })
        );
    }
});
