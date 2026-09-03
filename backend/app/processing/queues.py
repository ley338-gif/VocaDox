"""Queue-name mapping for processing jobs, plus which worker topology
consumes which queue. Kept in one place so worker entrypoints and the API
enqueue path never disagree about a queue name.

Topology (spec: "worker-speech, worker-diarization... choose based on
clean evolution toward multiple GPU workers later"): two worker services
share one image/entrypoint (`app.workers.processing_worker`) but are given
different `--queues` so they can eventually get separate GPU allocations
in Compose without a code change — `worker-speech` handles
NORMALIZE+TRANSCRIBE, `worker-diarization` handles DIARIZE+ALIGN (ALIGN is
CPU-only and cheap; it rides along with the diarization worker since
ALIGN is only ever triggered once diarization's run exists, when
diarization was requested).
"""

from __future__ import annotations

from app.processing.models import JobType

QUEUE_NAMES: dict[JobType, str] = {
    JobType.NORMALIZE: "vocadox:processing:normalize",
    JobType.TRANSCRIBE: "vocadox:processing:transcribe",
    JobType.DIARIZE: "vocadox:processing:diarize",
    JobType.ALIGN: "vocadox:processing:align",
    JobType.EXTRACT: "vocadox:processing:extract",
}

SPEECH_WORKER_JOB_TYPES = [JobType.NORMALIZE, JobType.TRANSCRIBE]
DIARIZATION_WORKER_JOB_TYPES = [JobType.DIARIZE, JobType.ALIGN]
# Phase 4: a dedicated worker service (`worker-extraction`) — CPU/GPU
# needs for LLM inference are separate from speech/diarization's, and
# extraction is never chained automatically from ALIGN (explicit trigger
# only), so it gets its own queue/topology entry rather than riding along
# with an existing worker.
EXTRACTION_WORKER_JOB_TYPES = [JobType.EXTRACT]


def queue_name_for(job_type: JobType) -> str:
    return QUEUE_NAMES[job_type]
