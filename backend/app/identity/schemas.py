"""Pydantic request/response schemas for the identity API."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Post-GA: closed set validated at the API boundary -- the DB column
# (User.gender) is a plain nullable string precisely so a future option
# never needs a migration, but every value that actually reaches it goes
# through this Literal first. `None` ("keine Angabe"/unspecified) is
# always valid and is the default for every user until an admin sets it.
GenderOption = Literal["male", "female", "diverse"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(BaseModel):
    """CSRF token is returned in the body (in addition to a JS-readable
    cookie) so a same-origin SPA can attach it to the `X-CSRF-Token` header
    on subsequent mutating requests (double-submit-cookie pattern)."""

    user_id: uuid.UUID
    username: str
    display_name: str
    csrf_token: str


class GroupSummary(BaseModel):
    """Minimal team identity for a picker — never the full admin group
    listing (`GET /admin/groups`, group:manage-gated). A regular user only
    needs to know their OWN team memberships to pick one when creating a
    conversation (app.conversations.authz's team-scoped visibility)."""

    id: uuid.UUID
    name: str


class CurrentUserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    permissions: list[str]
    groups: list[GroupSummary]


class CsrfTokenResponse(BaseModel):
    """Returned by `GET /auth/csrf` so a page that still has a valid
    session cookie (but lost its in-memory CSRF token to a full page
    reload — see `frontend/src/auth/AuthContext.tsx`) can recover it
    without forcing the user to log in again. Not a new secret: it's the
    same token already bound to the caller's own session and already
    returned once by `POST /auth/login`; this just re-reads it, gated by
    the same session-cookie authentication as every other identity
    endpoint."""

    csrf_token: str


# -- Phase 7: Admin Portal (Users/Groups/Roles) -----------------------------


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    auth_provider: str
    is_active: bool
    first_name: str | None = None
    last_name: str | None = None
    gender: GenderOption | None = None
    avatar_asset_key: str | None = None
    model_config = {"from_attributes": True}


class UserDetailResponse(UserSummaryResponse):
    group_ids: list[uuid.UUID]
    organization_ids: list[uuid.UUID]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=512)
    display_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    gender: GenderOption | None = None
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    organization_ids: list[uuid.UUID] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    is_active: bool | None = None
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    gender: GenderOption | None = None
    avatar_asset_key: str | None = Field(default=None, max_length=512)
    group_ids: list[uuid.UUID] | None = None
    organization_ids: list[uuid.UUID] | None = None


class SetPasswordRequest(BaseModel):
    """Admin-initiated reset, `POST /admin/users/{id}/set-password` --
    deliberately its own request/endpoint, never folded into
    `UserUpdateRequest`, so a password change always gets its own
    dedicated audit event and is never silently bundled into an unrelated
    profile-field PATCH. The client is expected to enforce a matching
    "repeat password" confirmation itself before ever sending this
    request -- there is nothing here to confirm server-side, since only
    one password value is transmitted."""

    new_password: str = Field(min_length=12, max_length=512)


class AvatarUploadResponse(BaseModel):
    asset_key: str


class GroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    organization_id: uuid.UUID | None
    model_config = {"from_attributes": True}


class GroupDetailResponse(GroupResponse):
    role_ids: list[uuid.UUID]
    member_ids: list[uuid.UUID]


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    organization_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    role_ids: list[uuid.UUID] | None = None


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    model_config = {"from_attributes": True}
