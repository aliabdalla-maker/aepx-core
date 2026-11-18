// Offline shell only: static assets are cached; API responses are never cached (security data must be live).
// Paths are relative to the registration scope so the console also works under a sub-path.
const CACHE = "aav-shell-v2";
const BASE = new URL(self.registration.scope).pathname.replace(/\/$/, "");
self.addEventListener("install", () => { self.skipWaiting(); });
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) =>
  Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !url.pathname.startsWith(BASE + "/")
      || url.pathname.startsWith(BASE + "/api/")) return;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok && (url.pathname.startsWith(BASE + "/_next/static/") || url.pathname.startsWith(BASE + "/icons/"))) {
      const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy));
    }
    return r;
  }).catch(() => caches.match(e.request).then((m) => m || caches.match(BASE + "/"))));
});
