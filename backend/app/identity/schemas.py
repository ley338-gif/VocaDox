"""Pydantic request/response schemas for the identity API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


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


class CurrentUserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    permissions: list[str]
