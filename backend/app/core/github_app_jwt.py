"""RS256 JWT signing for GitHub App server-to-server authentication.

GitHub Apps authenticate as the *application* by signing a JWT with the app's
private key (RS256). That JWT is then exchanged for an installation access
token that carries the app's permissions (issues, PRs, contents, ...).

Per GitHub's docs the JWT must:
- use `alg: RS256`
- contain `iat` (not in the future) and `exp` (<= iat + 10 minutes)
- contain `iss` = the numeric GitHub App id
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_ALG = "RS256"
_MAX_JWT_LIFETIME_SECONDS = 600  # GitHub caps app JWTs at 10 minutes
_LEEWAY_SECONDS = 30


def sign_app_jwt(
    app_id: int,
    private_key_pem: str,
    *,
    now: datetime | None = None,
) -> str:
    """Sign and return a GitHub App JWT for the given app id and PEM key.

    `now` is injectable for tests. `private_key_pem` must be the PEM contents.
    """
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("GitHub App private key must be an RSA key")
    current = now or datetime.now(UTC)
    iat = int(current.timestamp())
    payload: dict[str, Any] = {
        "iat": iat,
        "exp": iat + _MAX_JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    header: dict[str, Any] = {"alg": _ALG, "typ": "JWT"}

    signing_input = f"{_b64url(header)}.{_b64url(payload)}"
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url_bytes(signature)}"


def jwt_is_expired(app_jwt: str, *, now: datetime | None = None) -> bool:
    """Return True when the given app JWT has expired (or is near exp)."""
    try:
        payload_segment = app_jwt.split(".")[1]
        payload = json.loads(_unb64url(payload_segment))
    except (IndexError, ValueError, json.JSONDecodeError):
        return True
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return True
    current = now or datetime.now(UTC)
    return current.timestamp() >= exp - _LEEWAY_SECONDS


def _b64url(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url_bytes(raw)


def _b64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def app_jwt_lifetime() -> timedelta:
    return timedelta(seconds=_MAX_JWT_LIFETIME_SECONDS)
