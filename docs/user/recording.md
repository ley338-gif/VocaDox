# Recording a conversation in the browser

## Browser support

Recording needs `getUserMedia` + `MediaRecorder`, both feature-detected
before anything else happens. Tested against current **Chrome/Edge** and
**Firefox** (both record `audio/webm;codecs=opus`). Safari's
`MediaRecorder` support is inconsistent across versions — if it's not
reliably supported in your browser, you'll see an explicit "Recording
isn't supported in this browser" message with a suggestion to use
**Upload audio** instead, rather than a broken or mislabeled recording.

## Steps

1. **New conversation → Start recording**, fill in the title/type/
   organization, then continue.
2. **Consent step**: confirm the consent notice. This does **not** by
   itself make the recording legally compliant — see
   `docs/security/recording-privacy.md`. You must have actually obtained
   whatever consent your organization/jurisdiction requires before
   proceeding.
3. Your browser will ask for microphone permission. If you deny it, you
   can retry from the same screen.
4. **Record** starts capture. You'll see elapsed time and a live level
   meter. Use **Pause**/**Resume** as needed, and **Marker** to bookmark a
   moment (e.g. "medication discussion starts here") — markers are
   timestamped automatically.
5. **Stop** ends the recording. You can **Discard** it (nothing is kept)
   or **Upload** it to finalize.
6. Once uploaded, the conversation's Audio tab shows a full player with
   your markers overlaid on the seek bar.

## Live transcript & live draft (preview only)

While actively recording, a **Live-Transkript** panel appears once
enough audio has been captured, updating roughly every 10 seconds — and,
once there's enough content, a short **Live-Entwurf** (a few provisional
bullet points). Both are clearly labeled provisional/unconfirmed for a
reason:

- The live transcript is re-generated from the recording-so-far each
  update, not perfectly incremental — wording right at the edge of the
  most recent update can shift slightly as more audio is added.
- **Neither the live transcript nor the live draft is saved anywhere.**
  Once you upload the recording, both are discarded and replaced by the
  real, reviewable transcript and document your organization's normal
  processing pipeline produces — the same one that's always run after
  a recording is uploaded.
- If the live preview stops updating (a network hiccup, a backend
  restart), your recording itself is unaffected — it's still being
  captured normally in your browser, and will upload and process
  normally when you stop and click Upload.

## If something goes wrong

- **Upload fails** (network issue): you can **Retry** without re-recording
  — the retry is safe even if the first attempt partially succeeded, it
  will not create a duplicate.
- **Navigating away mid-recording**: your browser will warn you before
  leaving the page while a recording is in progress or waiting to be
  uploaded.
- **Browser/tab crash while actively recording**: that take is lost —
  there is no crash recovery for an in-progress recording in this release.
  Click Stop as soon as it's safe to do so if you're worried about this.
- **Microphone disconnected mid-recording**: the recording stops
  automatically and you're offered the same Discard/Upload choice as a
  normal Stop.
