"""At-rest encryption for per-tenant integration secrets (Meta access tokens, etc.).

Uses Fernet (AES-128-CBC + HMAC-SHA256) via `cryptography` (already present
transitively through python-jose[cryptography]; pinned explicitly in requirements).
Keys come from `settings.meta_enc_keys` — a comma-separated list of urlsafe-base64
32-byte Fernet keys. The FIRST key encrypts; ALL are tried on decrypt (MultiFernet),
so a key is rotated by PREPENDING a new one and retiring the old later.

Inert until configured: with no key set, encrypt/decrypt raise `SecretVaultNotConfigured`
so the integration is safe-by-default (mirrors core/storage.py's _require_configured).
Never log the plaintext or the key.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings


class SecretVaultNotConfigured(RuntimeError):
    """Raised when encrypt/decrypt is attempted with no META_ENC_KEYS configured."""


class SecretDecryptError(RuntimeError):
    """Raised when a ciphertext cannot be decrypted with any current key."""


@lru_cache(maxsize=1)
def _vault() -> MultiFernet | None:
    raw = (get_settings().meta_enc_keys or "").strip()
    if not raw:
        return None
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    # Fernet validates the key shape (urlsafe-base64, 32 bytes) on construction.
    return MultiFernet([Fernet(k) for k in keys])


def is_configured() -> bool:
    return _vault() is not None


def encrypt_secret(plaintext: str) -> str:
    vault = _vault()
    if vault is None:
        raise SecretVaultNotConfigured("META_ENC_KEYS is not configured.")
    return vault.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    vault = _vault()
    if vault is None:
        raise SecretVaultNotConfigured("META_ENC_KEYS is not configured.")
    try:
        return vault.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # unknown/rotated-out key, or tampered ciphertext
        raise SecretDecryptError("Could not decrypt secret with the current keys.") from exc


def generate_key() -> str:
    """Ops helper: mint a fresh urlsafe-base64 Fernet key for META_ENC_KEYS."""
    return Fernet.generate_key().decode()
