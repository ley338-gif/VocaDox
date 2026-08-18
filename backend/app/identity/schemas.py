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
