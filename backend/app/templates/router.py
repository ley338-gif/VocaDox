"""REST endpoints for the Template Engine / Prompt admin surface (spec
§42/§43). Global (platform-wide), NOT organization-scoped — matching
`docs/architecture/model-management-foundation.md`'s "one global provider
config for the whole deployment" precedent (per-organization templates are
explicitly out of scope, same as per-organization provider config).
Gated by `template:read`/`template:write` — never open to every user (spec:
"Template/profile management should require an appropriate admin-level
permission, not be open to every user")."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.deps import get_current_user, require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.templates.api_schemas import (
    PromptCreateRequest,
    PromptResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
    TemplateCreateRequest,
    TemplateResponse,
    TemplateVersionCreateRequest,
    TemplateVersionResponse,
)
from app.templates.models import (
    ImmutablePublishedVersionError,
    InvalidVersionTransitionError,
    Prompt,
    Template,
    TemplateVersion,
)
from app.templates.service import (
    create_draft_prompt_version,
    create_draft_version,
    create_prompt,
    create_template,
    get_prompt_by_key,
    get_template_by_key,
    list_prompt_versions,
    list_prompts,
    list_template_versions,
    list_templates,
    publish_prompt_version,
    publish_template_version,
)

router = APIRouter(prefix="/templates", tags=["templates"])
prompts_router = APIRouter(prefix="/prompts", tags=["templates"])

_require_template_read = require_permission("template:read")
_require_template_write = require_permission("template:write")


async def _get_template_or_404(db: AsyncSession, template_id: uuid.UUID) -> Template:
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template not found")
    return template


async def _get_version_or_404(
    db: AsyncSession, template_id: uuid.UUID, version_id: uuid.UUID
) -> TemplateVersion:
    version = await db.get(TemplateVersion, version_id)
    if version is None or version.template_id != template_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="template version not found"
        )
    return version


@router.get("", response_model=list[TemplateResponse])
async def list_templates_endpoint(
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> list[TemplateResponse]:
    return [TemplateResponse.model_validate(t) for t in await list_templates(db)]


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template_endpoint(
    payload: TemplateCreateRequest,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> TemplateResponse:
    if await get_template_by_key(db, payload.key) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"template key {payload.key!r} exists"
        )
    template = await create_template(
        db,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        extraction_categories=payload.extraction_categories,
        presentation=payload.presentation,
        review_rules=payload.review_rules,
        created_by=user,
    )
    await db.commit()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template_endpoint(
    template_id: uuid.UUID,
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> TemplateResponse:
    return TemplateResponse.model_validate(await _get_template_or_404(db, template_id))


@router.get("/{template_id}/versions", response_model=list[TemplateVersionResponse])
async def list_template_versions_endpoint(
    template_id: uuid.UUID,
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> list[TemplateVersionResponse]:
    await _get_template_or_404(db, template_id)
    return [
        TemplateVersionResponse.model_validate(v)
        for v in await list_template_versions(db, template_id)
    ]


@router.post(
    "/{template_id}/versions",
    response_model=TemplateVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_version_endpoint(
    template_id: uuid.UUID,
    payload: TemplateVersionCreateRequest,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> TemplateVersionResponse:
    """Always a brand-new DRAFT version — never mutates a published one
    (spec §42: "never mutate a published template in place")."""
    template = await _get_template_or_404(db, template_id)
    version = await create_draft_version(
        db,
        template=template,
        extraction_categories=payload.extraction_categories,
        presentation=payload.presentation,
        review_rules=payload.review_rules,
        created_by=user,
    )
    await db.commit()
    await db.refresh(version)
    return TemplateVersionResponse.model_validate(version)


@router.post(
    "/{template_id}/versions/{version_id}/publish", response_model=TemplateVersionResponse
)
async def publish_template_version_endpoint(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> TemplateVersionResponse:
    """Retires the previously-published version (never deletes/mutates its
    content) and re-points the template at the new one — every past
    `ProcessingRun`/`DocumentRevision` that recorded the old version's id
    keeps resolving to its exact, unchanged content."""
    template = await _get_template_or_404(db, template_id)
    version = await _get_version_or_404(db, template_id, version_id)
    try:
        published = await publish_template_version(
            db, template=template, version=version, published_by=user
        )
    except InvalidVersionTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ImmutablePublishedVersionError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(published)
    return TemplateVersionResponse.model_validate(published)


# -- Prompts (spec §43) ------------------------------------------------------


async def _get_prompt_or_404(db: AsyncSession, prompt_id: uuid.UUID) -> Prompt:
    prompt = await db.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prompt not found")
    return prompt


@prompts_router.get("", response_model=list[PromptResponse])
async def list_prompts_endpoint(
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> list[PromptResponse]:
    return [PromptResponse.model_validate(p) for p in await list_prompts(db)]


@prompts_router.post("", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt_endpoint(
    payload: PromptCreateRequest,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> PromptResponse:
    if await get_prompt_by_key(db, payload.key) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"prompt key {payload.key!r} exists"
        )
    prompt = await create_prompt(
        db,
        key=payload.key,
        name=payload.name,
        purpose=payload.purpose,
        system_prompt=payload.system_prompt,
        category_instructions=payload.category_instructions,
        created_by=user,
    )
    await db.commit()
    await db.refresh(prompt)
    return PromptResponse.model_validate(prompt)


@prompts_router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt_endpoint(
    prompt_id: uuid.UUID,
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> PromptResponse:
    return PromptResponse.model_validate(await _get_prompt_or_404(db, prompt_id))


@prompts_router.get("/{prompt_id}/versions", response_model=list[PromptVersionResponse])
async def list_prompt_versions_endpoint(
    prompt_id: uuid.UUID,
    _user: User = Depends(_require_template_read),
    db: AsyncSession = Depends(get_session),
) -> list[PromptVersionResponse]:
    await _get_prompt_or_404(db, prompt_id)
    return [
        PromptVersionResponse.model_validate(v) for v in await list_prompt_versions(db, prompt_id)
    ]


@prompts_router.post(
    "/{prompt_id}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt_version_endpoint(
    prompt_id: uuid.UUID,
    payload: PromptVersionCreateRequest,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> PromptVersionResponse:
    prompt = await _get_prompt_or_404(db, prompt_id)
    version = await create_draft_prompt_version(
        db,
        prompt=prompt,
        system_prompt=payload.system_prompt,
        category_instructions=payload.category_instructions,
        created_by=user,
    )
    await db.commit()
    await db.refresh(version)
    return PromptVersionResponse.model_validate(version)


@prompts_router.post(
    "/{prompt_id}/versions/{version_id}/publish", response_model=PromptVersionResponse
)
async def publish_prompt_version_endpoint(
    prompt_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(_require_template_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> PromptVersionResponse:
    from app.templates.models import PromptVersion

    prompt = await _get_prompt_or_404(db, prompt_id)
    version = await db.get(PromptVersion, version_id)
    if version is None or version.prompt_id != prompt_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt version not found"
        )
    try:
        published = await publish_prompt_version(
            db, prompt=prompt, version=version, published_by=user
        )
    except InvalidVersionTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(published)
    return PromptVersionResponse.model_validate(published)


_ = get_current_user  # re-exported import kept for parity with sibling routers
