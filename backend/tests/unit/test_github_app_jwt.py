"""Unit tests: GitHub App RS256 JWT signing."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.core.github_app_jwt import app_jwt_lifetime, jwt_is_expired, sign_app_jwt


@pytest.fixture
def rsa_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def pem(rsa_key: RSAPrivateKey) -> str:
    return rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _decode_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def test_sign_app_jwt_shape(pem: str):
    token = sign_app_jwt(app_id=12345, private_key_pem=pem)
    header_raw, payload_raw, signature = token.split(".")
    assert signature

    header = _decode_segment(header_raw)
    assert header["alg"] == "RS256"
    assert header["typ"] == "JWT"

    payload = _decode_segment(payload_raw)
    assert payload["iss"] == 12345
    assert isinstance(payload["iat"], int)
    assert payload["exp"] - payload["iat"] == 600


def test_sign_app_jwt_fixed_now(pem: str):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = sign_app_jwt(app_id=1, private_key_pem=pem, now=now)
    payload = _decode_segment(token.split(".")[1])
    assert payload["iat"] == int(now.timestamp())
    assert payload["exp"] == int(now.timestamp()) + 600


def test_sign_app_jwt_rejects_non_rsa_key():
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    with pytest.raises(ValueError, match="must be an RSA key"):
        sign_app_jwt(app_id=1, private_key_pem=pem)


def test_jwt_is_expired(pem: str):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = sign_app_jwt(app_id=1, private_key_pem=pem, now=now)
    assert jwt_is_expired(token, now=now) is False
    # Near exp (within leeway) counts as expired.
    near_exp = now.replace(year=2026, month=1, day=2)  # ~ 600s later + leeway
    assert jwt_is_expired(token, now=near_exp) is True


def test_jwt_is_expired_handles_garbage():
    assert jwt_is_expired("not-a-jwt") is True
    assert jwt_is_expired("a.b.c.d") is True


def test_app_jwt_lifetime():
    assert app_jwt_lifetime().total_seconds() == 600
