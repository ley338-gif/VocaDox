"""Import every domain package's ORM models so they register on
`Base.metadata`. Imported by `alembic/env.py` (for autogenerate) and by
tests that build schema directly from metadata (e.g. via
`Base.metadata.create_all` against SQLite) — the single place that needs
to know every domain's models module exists.
"""

from __future__ import annotations

# Phase 8: model_profile_lifecycle_events FK-references model_profiles.id;
# evaluation_runs has no FKs into other domains' tables.
from app.analytics import models as _analytics_models  # noqa: F401
from app.audit import models as _audit_models  # noqa: F401

# conversations imports media (Conversation.media_assets uses a string
# forward-ref) so media must be registered too; order doesn't matter for
# SQLAlchemy's mapper configuration, but both must be imported before any
# query touches either relationship.
from app.conversations import models as _conversations_models  # noqa: F401,E402
from app.diarization import models as _diarization_models  # noqa: F401,E402

# Phase 5: documents FK-references conversations.id and document_revisions.id
# (circular by design — Document.current_revision_id -> DocumentRevision,
# DocumentRevision.document_id -> Document — both declared in the same
# module so SQLAlchemy resolves the forward reference without help).
from app.documents import models as _documents_models  # noqa: F401,E402
from app.evidence import models as _evidence_models  # noqa: F401,E402
from app.identity import models as _identity_models  # noqa: F401

# Phase 4: extracted_facts FK-references processing_runs.id and
# conversations.id; fact_evidence FK-references extracted_facts.id and
# transcript_segments.id; review_issues FK-references conversations.id.
# model_profiles has no FKs into the above but is imported here for
# consistency (single place that knows every domain's models module).
from app.intelligence import models as _intelligence_models  # noqa: F401,E402

# Phase 9: follow_up_tasks FK-references organizations.id, conversations.id,
# extracted_facts.id, users.id — imported after intelligence/conversations.
from app.longitudinal import models as _longitudinal_models  # noqa: F401,E402
from app.media import models as _media_models  # noqa: F401,E402
from app.organizations import models as _organizations_models  # noqa: F401

# Phase 3: processing_runs must be imported before transcription/diarization
# (both FK-reference processing_runs.id).
from app.processing import models as _processing_models  # noqa: F401,E402

# Phase 6: model_profiles/processing_profiles (ProcessingProfileVersion
# FK-references templates.id/template_versions.id/prompts.id/
# prompt_versions.id — actual import order doesn't affect SQLAlchemy FK
# resolution, both are imported here regardless).
from app.profiles import models as _profiles_models  # noqa: F401,E402
from app.review import models as _review_models  # noqa: F401,E402
from app.templates import models as _templates_models  # noqa: F401,E402
from app.transcription import models as _transcription_models  # noqa: F401,E402
