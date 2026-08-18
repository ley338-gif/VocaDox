# Reviewing and correcting a transcript

## Why some rows are flagged

VocaDox flags a transcript row with **⚠ prüfen** ("needs review") when
the automatic system has a mechanical reason to be unsure, not a clinical
or content judgement:

- **Low ASR confidence** — the speech engine itself wasn't confident about
  the words.
- **No diarization coverage** — no speaker information exists for that
  span (`UNASSIGNED`).
- **Ambiguous speaker attribution** — a speaker was assigned, but the
  temporal evidence was weak (`AMBIGUOUS`).
- **Overlapping speech** — more than one person was talking at the same
  time (`OVERLAP`).

None of these flags represent an AI opinion about what's clinically or
practically important — they're honest signals about transcription/
diarization quality, described in
`docs/architecture/alignment.md`.

## Correcting text

If you have correction permission, click a transcript row's text to edit
it. Saving:

- Never deletes or overwrites what the speech engine originally produced
  — you'll always be able to see **"Original: ..."** underneath your
  correction.
- Records who made the correction and when (visible to auditors).
- Marks the row's review status as **Corrected**.

This matters because future evaluation of the speech engine's accuracy
depends on knowing exactly what it originally produced, independent of
any human edits.

## Speaker names

Detected speakers show as "SPEAKER_00", "SPEAKER_01", etc. by default —
these are anonymous machine-detected voice clusters, not identified
people. If you have speaker-assignment permission, rename a speaker (a
free-text label, or link it to a conversation participant) in the
speaker list above the transcript — see `docs/user/speakers.md`.

## What review does NOT do (yet)

Phase 3 has no clinical-importance scoring, no approval workflow, and no
document generation from the transcript. Marking a row reviewed/corrected
here only affects the transcript itself.
