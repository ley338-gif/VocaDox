from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None

    model_config = {"from_attributes": True}


class OrganizationCreateRequest(BaseModel):
    """Phase 7 closes the pre-existing gap flagged in Phase 5/6's
    validation reports: "organization creation has no HTTP endpoint"."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=1024)


class OrganizationMembershipResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


class OrganizationMemberUserResponse(BaseModel):
    """Deliberately minimal -- backs the conversation-participant "pick a
    registered user" directory (`GET /organizations/{id}/member-users`,
    gated by `user:read-directory`). No e-mail, auth-provider, or group
    data: just enough to show a name + avatar and pass an id back."""

    id: uuid.UUID
    username: str
    display_name: str
    first_name: str | None
    last_name: str | None
    avatar_asset_key: str | None

    model_config = {"from_attributes": True}
