"""The one genuinely unauthenticated, public REST surface in this
codebase (post-GA P3-2) — a time-limited recap share link. Deliberately
kept in its own router/module, never merged into `app.recap.router`
(every other endpoint there requires a session), so "this route needs no
auth" is a structural, file-level fact, not something to notice line by
line.

Authorization here is entirely the possession of an unguessable token
(`app.recap.service.create_share_link`) — there is no session, no CSRF
check (nothing state-changing happens beyond an access counter; a read
here never requires the double-submit protection CSRF exists to
prevent), and no organization/permission check, matching how the token
itself already encodes "whoever holds this link is allowed to read this
one recap".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.session import get_session
from app.recap.api_schemas import PublicRecapResponse
from app.recap.models import Recap, RecapRevision
from app.recap.service import get_valid_share_link, record_share_link_access

router = APIRouter(prefix="/public/recap", tags=["recap-public"])


@router.get("/{token}", response_model=PublicRecapResponse)
async def get_public_recap_endpoint(
    token: str, response: Response, db: AsyncSession = Depends(get_session)
) -> PublicRecapResponse:
    """404 for "doesn't exist", "expired", and "revoked" alike -- never
    distinguishes them, so a guessed/expired token can't be used to learn
    anything about whether it was ever real (same posture
    authorize_conversation_access already uses for org/team boundaries).
    Also 404s if the recap is somehow no longer approved (e.g. a new
    DRAFT revision superseded the one that was shared) -- the link never
    serves stale or unapproved content."""
    link = await get_valid_share_link(db, token=token)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found")

    result = await db.execute(select(Recap).where(Recap.conversation_id == link.conversation_id))
    recap = result.scalar_one_or_none()
    if recap is None or recap.current_revision_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found")
    revision = await db.get(RecapRevision, recap.current_revision_id)
    if revision is None or revision.status != "approved":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found")

    await record_share_link_access(db, link)
    await db.commit()

    # The URL is a bearer credential and the body can contain health data.
    # Neither a browser cache nor an intermediary may retain it, and a
    # token-bearing page URL must not become a Referer on later navigation.
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"

    return PublicRecapResponse(
        content=revision.content,
        revision_number=revision.revision_number,
        approved_at=revision.approved_at,
        expires_at=link.expires_at,
    )
