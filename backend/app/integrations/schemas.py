"""Pydantic request/response schemas for the integrations domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# -- Service Accounts ---------------------------------------------------


class ServiceAccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    organization_id: uuid.UUID
    scopes: list[str] = Field(default_factory=list)
    owner_user_id: uuid.UUID | None = None


class ServiceAccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scopes: list[str] | None = None
    owner_user_id: uuid.UUID | None = None
    is_active: bool | None = None


class ServiceAccountResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    key_prefix: str
    scopes: list[str]
    is_active: bool
    owner_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    last_rotated_at: datetime | None
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class ServiceAccountCreatedResponse(ServiceAccountResponse):
    """Returned exactly once, at creation/rotation: the only time the raw
    API key is ever available. Never reconstructable afterward."""

    api_key: str


# -- Webhooks -------------------------------------------------------------


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    organization_id: uuid.UUID
    target_url: str = Field(max_length=2048)
    event_types: list[str] = Field(default_factory=list, min_length=1)


class WebhookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_url: str | None = Field(default=None, max_length=2048)
    event_types: list[str] | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    target_url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookCreatedResponse(WebhookResponse):
    """Returned once, at creation/secret-rotation: the only time the raw
    signing secret is available via the API."""

    secret: str


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    webhook_id: uuid.UUID
    event_type: str
    payload: dict[str, object]
    attempt_number: int
    status: str
    response_status_code: int | None
    error_message: str | None
    created_at: datetime
    delivered_at: datetime | None

    model_config = {"from_attributes": True}


class WebhookDeliveryListResponse(BaseModel):
    items: list[WebhookDeliveryResponse]
    total: int


class WebhookEventTypesResponse(BaseModel):
    event_types: list[str]


class AvailableScopesResponse(BaseModel):
    scopes: list[str]
