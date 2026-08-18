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
}

SPEECH_WORKER_JOB_TYPES = [JobType.NORMALIZE, JobType.TRANSCRIBE]
DIARIZATION_WORKER_JOB_TYPES = [JobType.DIARIZE, JobType.ALIGN]


def queue_name_for(job_type: JobType) -> str:
    return QUEUE_NAMES[job_type]
