"""Unit tests for Argon2id password hashing."""

from __future__ import annotations

import pytest
from app.identity.passwords import MIN_PASSWORD_LENGTH, hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    password = "correct horse battery staple"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password entirely", hashed) is False


def test_verify_rejects_garbage_hash() -> None:
    assert verify_password("anything", "not-a-real-argon2-hash") is False


def test_hash_is_salted_differently_each_time() -> None:
    password = "correct horse battery staple"
    assert hash_password(password) != hash_password(password)


def test_hash_password_rejects_short_password() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


def test_min_password_length_enforced_exactly() -> None:
    hash_password("x" * MIN_PASSWORD_LENGTH)  # boundary: should not raise
    with pytest.raises(ValueError):
        hash_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_needs_rehash_false_for_freshly_hashed_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert needs_rehash(hashed) is False
