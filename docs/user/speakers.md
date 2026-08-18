# Speakers

## What a "detected speaker" is

When diarization runs, VocaDox's speech-detection system identifies
distinct voices in the recording and labels them generically —
`SPEAKER_00`, `SPEAKER_01`, and so on. **This is not identity
recognition.** VocaDox never attempts to recognize *who* a voice belongs
to (no voice biometrics, no matching against any database of known
people) — it only distinguishes "this is a different voice than that
one."

## Assigning a name

If you have speaker-assignment permission, you can give a detected
speaker a human-meaningful label two ways, from the Transcript tab's
speaker list:

- **Free-text label** — e.g. "Ärztin," "Patient," a first name — whatever
  makes sense for your workflow.
- **Link to a participant** — if you've already added participants to the
  conversation (Participants tab), you can associate a detected speaker
  with one of them.

This is always a manual, human decision — the system never guesses or
auto-assigns a real identity to a detected speaker.

## Multiple recordings, multiple speaker sets

Detected speakers are scoped to one diarization run on one conversation's
audio — reprocessing a conversation (a new diarization run) produces a
fresh, independent set of detected speakers; it does not carry over your
previous labels automatically in Phase 3.

## Overlapping speech

If two people spoke at the same time, VocaDox marks that part of the
transcript as **overlap** rather than guessing who "wins" — see
`docs/user/transcript-review.md` for what that flag means and
`docs/architecture/alignment.md` for how it's determined.
