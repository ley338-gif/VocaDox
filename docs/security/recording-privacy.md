# Recording privacy & consent (Phase 2)

## Consent notice — what it is and isn't

Before any browser recording starts, the frontend shows a configurable
consent notice (`Settings.recording_consent_notice`, default: "Confirm
that required consent/authorization for this recording has been
obtained.") with explicit Cancel/Start recording actions. Confirming this
notice is a UI gate, **not** a legal compliance mechanism — it does not by
itself satisfy any jurisdiction's recording-consent law (one-party vs.
two-party consent, healthcare-specific consent requirements, workplace
recording rules, etc.). Obtaining actual, valid consent from every
participant in a recorded conversation remains entirely the responsibility
of the deploying organization/operator, not something VocaDox verifies or
enforces.

## No auto-start

`getUserMedia` is never called until the user explicitly passes the
consent step *and* clicks "Start recording" a second, separate time
(`app.recording.useRecorder.requestPermission`, only reachable from a
button `onClick`). Verified directly against the pure state machine:
`frontend/src/recording/recordingMachine.test.ts`, "never auto-starts
recording."

## Participant data minimization

`ConversationParticipant.display_name` is a free-form label — the product
never requires a real name ("Person A", "Arzt", "Patient" are all valid).
`participant_type` is a small closed enum (UNKNOWN/STAFF/PATIENT/CLIENT/
GUEST/OTHER); `external_reference` is generic and optional, never a
required or type-specific field like `patient_id`.

## No automatic speaker identification

Phase 2 has no diarization or speaker-identification code at all (out of
scope by explicit instruction). `ConversationMarker`/
`ConversationParticipant` are both manually created by a human user; there
is no code path that infers or assigns a participant to an audio segment
automatically. When diarization ships in a later phase, mapping detected
speaker clusters to `ConversationParticipant`s is expected to require
human review before being treated as fact — not implemented or assumed
here.

## Mic/device error handling

`useRecorder` distinguishes permission-denied (`PERMISSION_DENIED`,
recoverable via a "Try again" action) from a mid-recording device/
`MediaRecorder` failure (`RECORDER_ERROR`/`DEVICE_DISCONNECTED`, both stop
the recording and surface an error banner rather than silently losing or
corrupting the take) — see `frontend/src/recording/recordingMachine.ts`
and its test coverage.

## Known limitation: browser/tab crash during an active recording

If the browser or tab crashes, or the device loses power, while a
recording is actively in progress (not yet stopped), that take is lost —
see [ADR-0012](../architecture/adr/0012-chunked-upload-decision.md) for
why Phase 2 accepted this trade-off rather than implementing full
server-side chunked capture. `docs/user/recording.md` states this
plainly to end users.
