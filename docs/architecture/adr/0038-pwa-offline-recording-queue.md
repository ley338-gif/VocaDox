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
`online` events, once per app load and after a bounded exponential retry
delay, so a queued recording resumes uploading automatically the next
time connectivity returns — including after the tab/app was fully closed
and reopened, which the previous in-memory-only retry state could never
survive.

**3. IndexedDB is used directly, hand-wrapped, not through a library.**
`idb` (or similar) would be a reasonable dependency for a larger
IndexedDB surface; this feature needs exactly one object store with
put/getAll/delete, which a ~40-line wrapper (`app/recording/
offlineQueue.ts`) covers without a new dependency.

**Phase 14 security addendum: each queued recording is bound to the immutable
authenticated user ID at enqueue time.** Listing and automatic upload require an
exact match with the current login. Records written by an older application
version without an owner are quarantined instead of being attributed to whoever
logs in next on the same browser profile. This is an authorization boundary, not
encryption: managed-device storage encryption and separate OS/browser profiles
remain required for sensitive offline recordings.

**Phase 14 reliability addendum: queue state is durable and visible.** Database
version 2 records `pending`, `waiting-for-network`, `uploading` and `failed`
states together with attempt count, next retry and a non-sensitive error class.
An `uploading` entry found after an app restart is recovered as `pending`.
Transient network/408/425/429/5xx failures retry from five seconds up to a
five-minute cap; a permanent 4xx response becomes a user-visible failed item and
does not starve later recordings. The local key combines owner ID and the
server-authoritative idempotency key, so enqueueing the same take twice replaces
the local entry and server retries cannot create a second media asset. A
single-flight guard prevents overlapping background flushes.

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
- Upload is sequential. A transient failure stops that pass to protect a weak
  connection; a permanent rejection is marked failed and processing continues.
  Failed recordings remain local until the user explicitly retries or confirms
  deletion. Successful recordings are removed immediately after the server
  confirms the idempotent upload. Marker delivery remains best-effort and does
  not retain another full audio copy.
- `sw.js`'s cache-as-you-go strategy means a stale cached asset could in
  principle be served briefly after a deploy if the network fetch itself
  fails at exactly the wrong moment — acceptable for app-shell
  availability, and every `/api/` response (the data that actually
  matters for correctness) is explicitly never cached.
- The service worker and offline queue interact with genuinely large
  binary blobs (audio recordings) — IndexedDB, not `localStorage`
  (which has a much smaller quota and is synchronous/string-only), was
  the only viable native storage choice for this.
- A legacy unowned record is intentionally not uploaded or displayed. Phase 14
  does not silently delete it because an interrupted recording may be the only
  remaining copy; explicit recovery/retention handling remains follow-up scope.
