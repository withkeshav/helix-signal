"""Fernet encryption for secret-typed settings (WO-BE-4)."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

FERNET_PREFIX = "fernet:v1:"


def _derive_fernet_key(raw: str) -> bytes:
    """Accept url-safe Fernet key, hex, or arbitrary passphrase."""
    stripped = raw.strip()
    if not stripped:
        raise ValueError("empty key")
    try:
        Fernet(stripped.encode("ascii"))
        return stripped.encode("ascii")
    except Exception:
        pass
    try:
        if len(stripped) == 64 and all(c in "0123456789abcdefABCDEF" for c in stripped):
            material = bytes.fromhex(stripped)
        else:
            material = base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4))
        return base64.urlsafe_b64encode(material[:32].ljust(32, b"\0"))
    except Exception:
        digest = hashlib.sha256(stripped.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet | None:
    raw = os.getenv("SETTINGS_ENCRYPTION_KEY", "").strip()
    if not raw:
        master = os.getenv("HELIX_MASTER_SECRET", "").strip()
        if master:
            salt = b"helix-settings-v1"
            derived = hashlib.pbkdf2_hmac("sha256", master.encode("utf-8"), salt, 100_000, dklen=32)
            raw = base64.urlsafe_b64encode(derived).decode("ascii")
        else:
            return None
    try:
        return Fernet(_derive_fernet_key(raw))
    except Exception:
        return None


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(FERNET_PREFIX))


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    fernet = get_fernet()
    if fernet is None:
        return plaintext
    token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{FERNET_PREFIX}{token}"


def decrypt_secret(stored: str) -> str:
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored
    fernet = get_fernet()
    if fernet is None:
        return ""
    try:
        return fernet.decrypt(stored[len(FERNET_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
