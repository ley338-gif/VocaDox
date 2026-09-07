# 0036 — Tab/screen audio capture via `getDisplayMedia`, staying bot-free

## Status
Accepted (2026-09-07). Post-GA, roadmap item P2-2 (audio-capture half).

## Context

The roadmap explicitly asks for `getDisplayMedia({audio:true})` capture
in `useRecorder.ts`, with an equally explicit constraint: "Wir bleiben
bot-frei — kein Meeting-Bot, unter keinen Umständen" (we stay bot-free —
no meeting bot, under no circumstances). Competing products in this
space commonly ship a server-side "bot" that joins a Zoom/Teams/Meet
call as a participant to capture audio — which VocaDox's own air-gapped,
no-new-runtime-network-dependency posture (ADR-0007) and this
directive's own constraint both rule out. The question this ADR settles
is purely mechanical: how does the browser itself, with no bot and no
new network dependency, capture audio from a call already running in
one of the user's own tabs?

## Decision

**Client-side `getDisplayMedia`, entirely in the browser the user is
already using — VocaDox never connects to any meeting service.** The
user starts recording as normal, picks "Ton von Tab/Bildschirm" as the
audio source, and the browser's own native share-picker (not anything
VocaDox renders) lets them choose which tab/window/screen to capture
audio from. This is the same standing permission model
`getUserMedia`-based microphone capture already uses — an explicit,
per-recording, browser-mediated grant — extended to a second capture
source, not a new trust boundary.

**`video: true` is requested alongside `audio: true` and the video
track is stopped and discarded immediately, never recorded.** Chromium
browsers only reliably surface the "share tab audio" checkbox in the
share dialog when video is also requested — an audio-only
`getDisplayMedia({audio:true})` call, though technically valid per the
spec, doesn't consistently produce a usable audio-sharing UI in
practice. Requesting `video:true` and discarding the resulting track
(`stream.getVideoTracks().forEach(t => t.stop())`, before ever handing
the stream to `MediaRecorder`) gets the reliable checkbox without
VocaDox ever touching, storing, or transmitting any video — same
"microphone-only, never camera" posture the existing consent flow
already documents for `getUserMedia`.

**A share with no audio track is treated as a real, disclosed error, not
silently recorded as silence.** Some browsers/OS combinations let a user
complete the share picker without checking "share audio" (or the source
they picked has no audio to share at all) — `getDisplayMedia` then
returns a video-only (or empty-audio) stream. `useRecorder.ts` checks
`getAudioTracks().length === 0` right after the grant and surfaces a
specific, actionable error ("no audio was shared, enable the checkbox")
rather than proceeding to record silence and only discovering the
problem after the fact.

## Consequences

- No new dependency, no new backend endpoint, no new network call — the
  finalize/upload path is unchanged; the backend never learns or cares
  whether a recording's audio came from a microphone or a shared tab.
- Firefox's tab-audio-sharing support varies by version and platform;
  `isSystemAudioCaptureSupported()` feature-detects `getDisplayMedia`
  itself but cannot detect "and will this browser's picker actually
  offer audio" ahead of time — the empty-audio-track check at grant time
  is the actual safety net, not upfront detection.
- This measure captures audio only from a source the user's own browser
  is already sharing (their own tab, or their own screen, which may
  include the call's audio if the OS mixes it in) — it never reaches
  into a meeting service's API, and can never capture a call VocaDox's
  user isn't already a genuine participant in. This is the concrete
  mechanism that keeps the "bot-free, under no circumstances" constraint
  true by construction, not just by policy.
