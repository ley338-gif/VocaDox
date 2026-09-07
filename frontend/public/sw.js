/**
 * Post-GA P2-3: minimal service worker for PWA installability and basic
 * offline asset availability. Deliberately NOT a full precaching build
 * (no build-time asset manifest, no Workbox) — see docs/architecture/adr/
 * 0038-pwa-offline-recording-queue.md for why a runtime, opportunistic
 * cache-as-you-go strategy was chosen instead: it needs no new build
 * tooling and stays simple enough to reason about, at the disclosed cost
 * that a page/asset is only available offline AFTER it has been loaded
 * online at least once in this browser.
 *
 * Never caches `/api/`, `/health`, or the service worker/manifest itself
 * — API responses must always be fresh (or fail honestly when offline;
 * the app's own upload retry/offline-queue logic handles that, this
 * worker must not silently serve stale API data).
 */

const CACHE_NAME = "vocadox-shell-v1";
const NEVER_CACHE_PREFIXES = ["/api/", "/health", "/sw.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function isNeverCached(url) {
  return NEVER_CACHE_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.method !== "GET") return;
  if (isNeverCached(url)) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // Navigation requests (loading a page) fall back to the cached
          // app shell so the SPA router can still render offline; other
          // asset requests with nothing cached simply fail, same as
          // without a service worker at all.
          if (event.request.mode === "navigate") {
            return caches.match("/");
          }
          return Promise.reject(new Error("offline and not cached"));
        })
      )
  );
});
