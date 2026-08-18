# Synthetic test audio fixtures (Phase 3)

All audio in this directory is **synthetically generated**, never a real
recording of a real person — per the spec's "Test fixtures: synthetic
speech only, never real patient/meeting audio."

## Provenance

Generated locally via **Windows SAPI** (`System.Speech.Synthesis`, part
of Windows, no third-party TTS engine or model involved) using the
built-in **"Microsoft Hedda Desktop"** German voice, on 2026-08-18, via
the PowerShell script whose exact commands are reproduced below. This
voice ships with Windows itself — no separate license/provenance review
of a third-party TTS model was needed since no third-party model was
used.

```powershell
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice("Microsoft Hedda Desktop")
$synth.Rate = 0
$synth.SetOutputToWaveFile("german_speakerA_part1.wav")
$synth.Speak("Guten Tag, mein Name ist Anna. Ich moechte heute ueber das Projekt sprechen.")
$synth.Rate = 3   # faster rate = the only practical way to get a second, distinguishable "voice" from one installed German voice
$synth.SetOutputToWaveFile("german_speakerB_part1.wav")
$synth.Speak("Hallo Anna, das freut mich zu hoeren. Wie ist der aktuelle Stand?")
$synth.Rate = 0
$synth.SetOutputToWaveFile("german_speakerA_part2.wav")
$synth.Speak("Wir sind fast fertig. Die Dokumentation wird naechste Woche abgeschlossen.")
```

The three parts were then converted to 16kHz mono PCM and concatenated
with short silence gaps via `ffmpeg`, producing
`german_multispeaker_conversation.wav`.

## Known limitation: single physical voice

Only one German voice ships with this Windows installation
("Microsoft Hedda Desktop"). The "two speakers" in
`german_multispeaker_conversation.wav` are the **same underlying voice at
two different speaking rates**, not two genuinely distinct voices — a
real diarization evaluation against genuinely distinct voices would need
either a second installed voice or a different TTS source. This is
documented honestly in PHASE_3_VALIDATION_REPORT.md's diarization
evaluation section rather than presented as a stronger test than it is.

## ASCII umlaut substitution

The source text uses `oe`/`ae` instead of `ö`/`ä` (`moechte`, `naechste`)
— a PowerShell/SAPI text-encoding convenience, not a spelling test. SAPI
pronounces these acceptably close to the correct German pronunciation but
not identically. See `german_multispeaker_conversation.gold.txt` for the
exact gold-standard reference text actually spoken.

## Files

- `german_multispeaker_conversation.wav` — ~18.7s, 2 (voice-varied)
  speaker turns, 16kHz mono PCM. Primary STT+diarization+alignment
  fixture.
- `german_silence.wav` — 5s of pure digital silence, 16kHz mono PCM.
  Silence-handling fixture (spec: "don't invent placeholder speech for
  silence").
- `german_corrupted.wav` — 37 bytes of plain text, `.wav` extension but
  not a real audio file at all. Corrupted/invalid-input fixture.
