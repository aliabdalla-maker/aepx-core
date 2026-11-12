/* AEP-X shell worker: never cache API responses, credentials or workspace files. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;
  // Network only: no sensitive workspace persistence in service-worker caches.
});
