"""FHIR R4 `DocumentReference` export (post-GA P3-1) — VocaDox's one
real Fachsystem integration, replacing the four previously-documented-
only adapters (see docs/architecture/future-considerations.md's Phase 10
notes and ADR-0039 for why FHIR `DocumentReference` was chosen over GDT).

Pure local export, no network call, no FHIR server/client library
dependency (ADR-0007: air-gapped) — this hand-builds a FHIR R4
`DocumentReference` resource dict following the base specification's
stable, well-documented shape (`resourceType`/`status`/`docStatus`/
`type`/`subject`/`content[].attachment`/`context.period` are all base R4
elements, unchanged across FHIR versions the way profile-specific
extensions are not). Not validated against the official FHIR JSON
Schema/StructureDefinition — no such library is a dependency here; this
is a disclosed limitation, see ADR-0039.

No real patient identity is ever claimed: `subject.display` is free text
only (never a resolvable `Patient` resource reference/id) — VocaDox
never requires or stores a real patient identifier
(`app.conversations.models.ConversationParticipant`'s `display_name` is
explicitly "a free-form label ... real names are never required"), so
claiming a resolvable Patient reference in an exported FHIR resource
would be inventing data VocaDox was never given.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any

from app.documents.models import DocumentRevisionStatus

# FHIR DocumentReference.docStatus is one of preliminary | final | amended
# | entered-in-error. VocaDox's own workflow (spec §27) only ever reaches
# APPROVED via an explicit human action (app.documents.service.
# approve_document) — every earlier status is honestly still
# "preliminary" from an external system's point of view, never
# "final" until a human has actually approved it.
_DOC_STATUS_MAP: dict[str, str] = {
    DocumentRevisionStatus.DRAFT.value: "preliminary",
    DocumentRevisionStatus.REVIEW_REQUIRED.value: "preliminary",
    DocumentRevisionStatus.READY_FOR_APPROVAL.value: "preliminary",
    DocumentRevisionStatus.APPROVED.value: "final",
}

# Not a registered FHIR extension (no such registry submission has been
# made) -- a placeholder URI following FHIR's own "use a URI you control"
# extension convention, disclosed as such rather than presented as an
# officially recognized extension.
_REVISION_NUMBER_EXTENSION_URL = "https://vocadox.example/fhir/StructureDefinition/revision-number"


def render_fhir_document_reference(
    *,
    document_id: uuid.UUID,
    conversation_title: str,
    subject_display: str | None,
    revision_number: int,
    revision_status: str,
    rendered_text: str,
    generated_at: datetime,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    external_reference: str | None = None,
    external_reference_type: str | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "id": str(document_id),
        "status": "current",
        "docStatus": _DOC_STATUS_MAP.get(revision_status, "preliminary"),
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "34133-9",
                    "display": "Summary of episode note",
                }
            ]
        },
        "date": generated_at.isoformat(),
        "description": conversation_title,
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain; charset=utf-8",
                    "data": base64.b64encode(rendered_text.encode("utf-8")).decode("ascii"),
                    "title": f"{conversation_title} (Revision {revision_number})",
                }
            }
        ],
        "extension": [
            {"url": _REVISION_NUMBER_EXTENSION_URL, "valueInteger": revision_number}
        ],
    }
    if subject_display:
        resource["subject"] = {"display": subject_display}
    if started_at is not None:
        period: dict[str, str] = {"start": started_at.isoformat()}
        if ended_at is not None:
            period["end"] = ended_at.isoformat()
        resource["context"] = {"period": period}
    if external_reference:
        resource["identifier"] = [
            {
                "type": {"text": external_reference_type or "external-reference"},
                "value": external_reference,
            }
        ]
    return resource
