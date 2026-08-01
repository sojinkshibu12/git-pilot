"""Domain-agnostic security primitives.

- Constant-time comparisons
- Crypto random generation (secrets module)
- OAuth state generation / validation
- PKCE verifier / challenge generation (S256)
- Password hashing (Argon2id)
- AES-256-GCM authenticated encryption (token vault)

Never reuse primitives from the client side. These are backend-only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

_S256_ALG = "S256"
_PLAIN_ALG = "plain"

# Token vault encryption uses AES-256-GCM (RFC 8452 recommendation for OAuth bearer tokens).
_VAULT_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12
_TAG_BYTES = 16


# --------------------------------------------------------------------------- #
# Constant time
# --------------------------------------------------------------------------- #
def constant_time_eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def constant_time_bytes_eq(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


# --------------------------------------------------------------------------- #
# OAuth state
# --------------------------------------------------------------------------- #
def generate_state() -> str:
    """Cryptographically secure random state, URL-safe, 32 bytes entropy."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


def generate_verifier() -> str:
    """PKCE verifier per RFC 7636 §4.1: 43–128 unreserved chars."""
    return secrets.token_urlsafe(64)[:64]


def compute_challenge(verifier: str, method: str = _S256_ALG) -> str:
    """RFC 7636 §4.2 code_challenge from the code_verifier."""
    if method == _S256_ALG:
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    if method == _PLAIN_ALG:
        return verifier
    raise ValueError(f"Unsupported PKCE method: {method}")


@dataclass(frozen=True)
class PKCEPair:
    verifier: str
    challenge: str
    method: str = _S256_ALG

    @classmethod
    def generate(cls) -> PKCEPair:
        verifier = generate_verifier()
        return cls(verifier=verifier, challenge=compute_challenge(verifier))


# --------------------------------------------------------------------------- #
# Password hashing — Argon2id
# --------------------------------------------------------------------------- #
def hash_password(password: str, settings: Settings) -> str:
    from argon2 import PasswordHasher

    ph = PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
        hash_len=32,
    )
    return ph.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError

    ph = PasswordHasher()
    try:
        return ph.verify(encoded, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


# --------------------------------------------------------------------------- #
# AES-256-GCM token vault
# --------------------------------------------------------------------------- #
class TokenVault:
    """Authenticated-encryption vault for GitHub credentials.

    Format:  `v1.<nonce_b64>.<ciphertext+tag_b64>`
    Each ciphertext embeds its 128-bit auth tag (AESGCM appends it).
    """

    _VERSION = 1

    def __init__(self, key_hex: str) -> None:
        key = bytes.fromhex(key_hex)
        if len(key) != _VAULT_KEY_BYTES:
            raise ValueError(f"Encryption key must be {_VAULT_KEY_BYTES} bytes (32) hex-encoded")
        self._cipher = AESGCM(key)

    @classmethod
    def generate_key(cls) -> str:
        return secrets.token_hex(_VAULT_KEY_BYTES)

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode(), associated_data=None)
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode()
        return f"v{self._VERSION}.{payload}"

    def decrypt(self, blob: str) -> str:
        version, _, payload = blob.partition(".")
        if version != f"v{self._VERSION}":
            raise ValueError("Unsupported token vault version")
        raw = base64.urlsafe_b64decode(payload.encode())
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return self._cipher.decrypt(nonce, ciphertext, associated_data=None).decode()

    def rekey(self, old_key_hex: str) -> None:
        """Rewrite stored ciphertext with a new key (key rotation)."""
        raise NotImplementedError("Run as a background job that re-encrypts each row.")


# --------------------------------------------------------------------------- #
# Session binding / HMAC helpers
# --------------------------------------------------------------------------- #
def generate_session_id() -> str:
    return secrets.token_urlsafe(48)


def generate_hmac(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def secure_compare_bytes(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


def ephemeral_pepper(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def random_bytes(n: int = 32) -> bytes:
    return os.urandom(n)


# Keep the module importable without a configured vault instance.
_vault: TokenVault | None = None


def configure_vault(settings: Settings) -> TokenVault:
    global _vault
    _vault = TokenVault(settings.TOKEN_ENCRYPTION_KEY)
    return _vault


def get_vault() -> TokenVault:
    if _vault is None:
        raise RuntimeError("Token vault not configured. Call configure_vault(settings) at startup.")
    return _vault
