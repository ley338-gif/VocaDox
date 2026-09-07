# 0038 — Mobile PWA: hand-written service worker, IndexedDB offline recording queue

## Status
Accepted (2026-09-07). Post-GA, roadmap item P2-3.

## Context

The roadmap asks for mobile recording as an installable PWA with an
offline queue. Three design questions: (1) how to make the app
installable and give it basic offline asset availability without adding
new build tooling, (2) how a finished recording that can't reach the
server (offline, or the phone put to sleep mid-upload) survives until it
can, and (3) where the PWA icons come from without a design tool in this
environment.

## Decision

**1. A hand-written `public/sw.js`, no `vite-plugin-pwa`/Workbox.** A
build-time precaching plugin would need to enumerate Vite's hashed
output files at build time and inject them into the service worker —
real value, but a new devDependency and a meaningfully more complex
build step for what this measure needs. Instead, `sw.js` uses a runtime,
opportunistic cache-as-you-go strategy: every same-origin GET response
(except `/api/`, `/health`, and the worker/manifest files themselves) is
cached as it's fetched, and served from cache on a subsequent offline
fetch, with a navigation-request fallback to the cached app shell.
Disclosed trade-off: a page/asset is only available offline once it has
been loaded online at least once in that browser — there is no
first-visit-offline guarantee. Acceptable for this measure; a real
precaching build is a reasonable future upgrade if that gap proves
painful in practice.

**2. Recordings that fail to upload due to a network-level failure are
queued in IndexedDB, not just left in the existing in-memory "upload-
failed, click retry" state.** The existing `recordingMachine.ts` already
had an `upload-failed` → `RETRY_UPLOAD` path (manual retry, lost on page
reload) — genuinely sufficient for "the server rejected this," but not
for "there was no server to talk to at all," which is the normal case
on a mobile PWA losing signal. A network-level failure is distinguished
from a server-rejected one by type: `fetch` throws a plain error before
a response exists (never becomes the app's `ApiError`, which is only
constructed from an actual HTTP response) — see `RecordingWorkspace.tsx
`'s `handleFinalize`. A new terminal `queued-offline` state (distinct
from `upload-failed`) reflects that the recording is now safely
persisted and needs no more user action; `useOfflineQueueSync` (mounted
once in `AppShell`) flushes the queue sequentially, oldest first, on
`online` events and once per app load, so a queued recording resumes
uploading automatically the next time connectivity returns — including
after the tab/app was fully closed and reopened, which the previous
in-memory-only retry state could never survive.

**3. IndexedDB is used directly, hand-wrapped, not through a library.**
`idb` (or similar) would be a reasonable dependency for a larger
IndexedDB surface; this feature needs exactly one object store with
put/getAll/delete, which a ~40-line wrapper (`app/recording/
offlineQueue.ts`) covers without a new dependency.

**4. PWA icons are generated with Pillow, an existing backend
dependency, not a new frontend one.** No image-editing tool exists in
this environment and no icon design asset was supplied; a two-line
Pillow script (`Image.new` + a centered "V" glyph in VocaDox's own
accent color, `#2563eb`) produces real, valid 192×192/512×512 PNGs.
These are placeholder brand icons, not a designed logo — replacing them
with real branding is a natural, low-risk follow-up whenever design
assets exist, requiring no code change (just replacing the PNG files).

## Consequences

- No new npm dependency (`package.json`/`package-lock.json` unchanged),
  no new backend dependency (Pillow was already installed).
- The offline queue's sequential, stop-on-first-failure flush means a
  weak-but-present connection that can upload the oldest queued
  recording but not a later one will still leave later ones queued
  until the next `online` event — a deliberate simplicity trade-off
  documented in `useOfflineQueueSync`'s own docstring, not a bug.
- `sw.js`'s cache-as-you-go strategy means a stale cached asset could in
  principle be served briefly after a deploy if the network fetch itself
  fails at exactly the wrong moment — acceptable for app-shell
  availability, and every `/api/` response (the data that actually
  matters for correctness) is explicitly never cached.
- The service worker and offline queue interact with genuinely large
  binary blobs (audio recordings) — IndexedDB, not `localStorage`
  (which has a much smaller quota and is synchronous/string-only), was
  the only viable native storage choice for this.
