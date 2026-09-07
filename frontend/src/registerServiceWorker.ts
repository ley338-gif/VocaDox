/**
 * Post-GA P2-3: registers the app-shell service worker for PWA
 * installability + basic offline asset availability (see public/sw.js).
 * Feature-detected and silently skipped where unsupported — this is an
 * enhancement, never a requirement for the app to function online.
 */
export function registerServiceWorker(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Registration failing (unsupported context, blocked, etc.) must
      // never break the app itself — it simply runs without offline
      // asset caching / installability.
    });
  });
}
