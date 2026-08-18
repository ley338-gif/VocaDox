# Transcribing a conversation

## Starting transcription

Transcription never starts automatically when you upload or record audio
— open the conversation's **Transcript** tab and click **Transkription
starten**. This is deliberate: processing takes real compute time and
touches the conversation's audio, so it's always your explicit choice.

You'll see one of five real progress stages while it runs:

1. **Preparing audio** — normalizing the recording for the speech engine.
2. **Transcribing** — converting speech to text.
3. **Detecting speakers** — identifying who spoke when (if enabled).
4. **Aligning transcript** — combining the text and speaker timing into
   the final transcript.
5. **Ready** — done.

The page updates automatically; you don't need to refresh. Processing
runs in the background, so you can navigate away and come back later.

## Reading the transcript

Each row shows a timestamp, the speaker (see
`docs/user/speakers.md`), the text, and a confidence percentage.
Click a timestamp to jump the audio player to that moment.

A **⚠ prüfen** flag on a row means the automatic system wasn't confident
about that text or speaker attribution — see `docs/user/transcript-review.md`.

## If it fails

You'll see a plain message like "Transcription failed — Model
unavailable" with a **Retry** button, never a raw error code alone. If
retrying repeatedly doesn't help, contact your administrator — the
underlying speech/diarization model may need to be installed (see
`docs/admin/model-installation.md`).

## Reprocessing

If your organization later configures a different/updated model, an
administrator or a permitted user can trigger reprocessing. This creates
a new transcript version — your previous transcript and any corrections
made to it are preserved, not deleted.

## Exporting

Use the **.txt / .json / .md** links above the transcript to download it
as plain text, structured JSON, or Markdown, each with timestamps and
speaker labels. Exports never include AI-generated summaries — Phase 3
does not produce summaries at all (see project roadmap).

## Searching

The search box above the transcript filters rows by text — useful for
finding a specific moment in a long conversation. This is deliberately a
simple, in-transcript text search, not a semantic/AI search.
