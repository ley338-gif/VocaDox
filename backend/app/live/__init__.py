"""Post-GA P2-1: live transcript + live draft during recording.

Deliberately ephemeral — everything here lives only in the `CacheBackend`
(Valkey in production, TTL-bound) and is discarded once the real
processing pipeline runs. A live-preview transcript/draft is NEVER
persisted as a real `Transcript`/`ExtractedFact`/`Document` row and NEVER
carries evidence links — it is explicitly provisional, replaced wholesale
by the authoritative final pass (`app.processing.orchestrator`) once
recording stops and the normal upload finishes. See app.live.service's
module docstring for why.
"""
