"""Side-effect-only module: forces `huggingface_hub` into offline-only
mode (`HF_HUB_OFFLINE=1`) as early as possible in a worker process's
lifetime — before `huggingface_hub` (or anything that imports it, like
`pyannote.audio`) has a chance to be imported anywhere else in the
process.

Why this needs to be its own module rather than an inline
`os.environ[...] = "1"` call inside `app.workers.runner`: it lets
`app.workers.runner` import it as the literal first line of the file
(`from app.workers import _offline_env`) without tripping ruff's
"module level import not at top of file" rule, which a bare executable
statement before other imports would.

Why this needs to exist at all: `huggingface_hub.constants.HF_HUB_OFFLINE`
is read from `os.environ` exactly once, at that module's own first
import, and cached as a plain Python `bool` — every later read anywhere
in `huggingface_hub`/`pyannote.audio` sees that cached value, not a fresh
`os.environ` lookup. Setting the env var later (e.g. right before
`Pipeline.from_pretrained` inside
`app.providers.diarization.PyannoteDiarizationProvider._ensure_loaded`,
which is called lazily on first use, long after process startup) is
therefore a silent no-op. Found by real testing during Phase 3.1's
offline-runtime validation: with the env var set only at
`_ensure_loaded` time, a worker with both of the diarization pipeline's
dependent sub-models already fully cached locally still made a real,
live `HEAD https://huggingface.co/pyannote/segmentation-3.0/...` request
at inference time — silent network access in what should be a fully
offline runtime path, exactly what the spec forbids.

`setdefault` (not a plain assignment) so an operator can still explicitly
force ONLINE mode for local development/debugging by setting
`HF_HUB_OFFLINE=0` in the environment before starting the process.
"""

from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
