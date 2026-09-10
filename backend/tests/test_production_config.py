"""Fail-closed production configuration guardrails."""

from __future__ import annotations

import pytest
from app.platform.config import Settings
from pydantic import ValidationError

SAFE_DATABASE_URL = (
    "postgresql+asyncpg://vocadox:4af15f8e69d34aaf9d12f6074b812e21@postgres:5432/vocadox"
)


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": SAFE_DATABASE_URL,
        "session_cookie_secure": True,
        "cors_allow_origins": [],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_safe_production_configuration_is_accepted() -> None:
    settings = production_settings(cors_allow_origins=["https://vocadox.example"])

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE must be true"),
        (
            {
                "database_url": (
                    "postgresql+asyncpg://vocadox:changeme@postgres:5432/vocadox"
                )
            },
            "known development/default value",
        ),
        (
            {"database_url": "postgresql+asyncpg://vocadox@postgres:5432/vocadox"},
            "must contain a database password",
        ),
        (
            {"database_url": "postgresql+asyncpg://vocadox:too-short@postgres:5432/vocadox"},
            "must be at least 16 characters",
        ),
        ({"database_url": "sqlite+aiosqlite:///prod.db"}, "must use postgresql\\+asyncpg"),
        ({"database_echo": True}, "DATABASE_ECHO must be false"),
        ({"cors_allow_origins": ["*"]}, "must not contain wildcards"),
        (
            {"cors_allow_origins": ["http://vocadox.example"]},
            "must be an HTTPS origin",
        ),
        (
            {"cors_allow_origins": ["https://vocadox.example/path"]},
            "must be an HTTPS origin",
        ),
    ],
)
def test_unsafe_production_configuration_is_rejected(
    overrides: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        production_settings(**overrides)


def test_development_convenience_values_remain_available() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        database_url="postgresql+asyncpg://vocadox:changeme@localhost:5432/vocadox",
        session_cookie_secure=False,
        cors_allow_origins=["http://localhost:5173"],
    )

    assert settings.session_cookie_secure is False


def test_production_validation_error_does_not_echo_secrets() -> None:
    secret = "4af15f8e69d34aaf9d12f6074b812e21"

    with pytest.raises(ValidationError) as raised:
        production_settings(session_cookie_secure=False)

    assert secret not in str(raised.value)
