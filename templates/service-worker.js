{% load static %}
const CACHE_NAME = "nyansa-shell-v2";
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
        // Authenticated pages (dashboards, grades, quiz results, tutor sessions) are
        // never cached or replayed here - on a shared device, a stale cached page for
        // one user could otherwise be served to whoever is logged in next. Only the
        // generic, non-personalized offline shell is available when the network fails.
        event.respondWith(
            fetch(request).catch(() => caches.match("{% static 'offline.html' %}"))
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
