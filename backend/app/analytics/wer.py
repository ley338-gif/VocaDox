"""Word Error Rate (post-GA P0-3) -- a real, standard Levenshtein-distance
metric over whitespace-tokenized words, used to measure a custom-
vocabulary comparison's actual effect on transcription accuracy (see
`app.analytics.service.run_vocabulary_comparison`). Pure stdlib, no new
dependency.
"""

from __future__ import annotations


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER = (substitutions + deletions + insertions) / len(reference
    words), the standard ASR accuracy metric. Case-insensitive,
    whitespace-tokenized (matches how faster-whisper/most ASR evaluation
    tooling compares transcripts -- punctuation differences are not
    penalized, since neither provider is expected to punctuate
    identically to a human-corrected reference).
    """
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    # Standard edit-distance dynamic program, tracked per-word.
    rows, cols = len(ref_words) + 1, len(hyp_words) + 1
    dist = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dist[i][0] = i
    for j in range(cols):
        dist[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dist[i][j] = dist[i - 1][j - 1]
            else:
                dist[i][j] = 1 + min(
                    dist[i - 1][j],  # deletion
                    dist[i][j - 1],  # insertion
                    dist[i - 1][j - 1],  # substitution
                )
    return dist[-1][-1] / len(ref_words)
