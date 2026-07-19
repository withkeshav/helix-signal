"""Tests for secret settings encryption (WO-BE-4)."""

from __future__ import annotations

import base64
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from sqlalchemy import select

from providers.settings import Setting, get_secret, get_setting, set_setting
from providers.settings_crypto import FERNET_PREFIX, decrypt_secret, encrypt_secret, is_encrypted


@pytest.fixture()
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", key)
    return key


def test_encrypt_decrypt_round_trip(encryption_key: str) -> None:
    ciphertext = encrypt_secret("sk-live-test")
    assert ciphertext.startswith(FERNET_PREFIX)
    assert decrypt_secret(ciphertext) == "sk-live-test"


def test_set_setting_stores_ciphertext(db_session, encryption_key: str) -> None:
    set_setting("secret_ollama_api_key", "sk-round-trip", db_session)
    row = db_session.execute(
        select(Setting).where(Setting.key == "secret_ollama_api_key")
    ).scalars().first()
    assert row is not None
    assert row.value.startswith(FERNET_PREFIX)
    assert "sk-round-trip" not in row.value
    assert get_secret("secret_ollama_api_key", db_session) == "sk-round-trip"


def test_get_setting_masks_secret(db_session, encryption_key: str) -> None:
    set_setting("secret_ollama_api_key", "sk-masked", db_session)
    assert get_setting("secret_ollama_api_key", db_session) == "configured"


def test_lazy_plaintext_migration(db_session, encryption_key: str) -> None:
    existing = db_session.execute(
        select(Setting).where(Setting.key == "secret_ollama_api_key")
    ).scalars().first()
    if existing:
        existing.value = "sk-plaintext"
    else:
        db_session.add(Setting(key="secret_ollama_api_key", value="sk-plaintext"))
    db_session.commit()
    assert get_secret("secret_ollama_api_key", db_session) == "sk-plaintext"
    row = db_session.execute(
        select(Setting).where(Setting.key == "secret_ollama_api_key")
    ).scalars().one()
    assert is_encrypted(row.value)


def test_plaintext_without_encryption_key(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("HELIX_MASTER_SECRET", raising=False)
    set_setting("secret_ollama_api_key", "sk-dev-plain", db_session)
    row = db_session.execute(
        select(Setting).where(Setting.key == "secret_ollama_api_key")
    ).scalars().one()
    assert row.value == "sk-dev-plain"
    assert get_secret("secret_ollama_api_key", db_session) == "sk-dev-plain"
