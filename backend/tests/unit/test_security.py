"""Unit tests: security primitives (PKCE, state, vault, passwords, timing)."""

from __future__ import annotations

import re

import pytest
from cryptography.exceptions import InvalidTag

from app.core.security import (
    PKCEPair,
    TokenVault,
    compute_challenge,
    constant_time_eq,
    generate_state,
    generate_verifier,
    hash_password,
    verify_password,
)


class TestStateGeneration:
    def test_generates_urlsafe_token(self) -> None:
        state = generate_state()
        assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", state)
        assert len(state) >= 43

    def test_unique(self) -> None:
        assert len({generate_state() for _ in range(100)}) == 100

    def test_constant_time_compare(self) -> None:
        assert constant_time_eq("abc", "abc")
        assert not constant_time_eq("abc", "abd")
        assert not constant_time_eq("abc", "abcde")


class TestPKCE:
    def test_verifier_meets_rfc7636(self) -> None:
        for _ in range(50):
            v = generate_verifier()
            assert 43 <= len(v) <= 128
            assert re.fullmatch(r"[A-Za-z0-9._~-]+", v)

    def test_challenge_is_sha256_base64url(self) -> None:
        v = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        ch = compute_challenge(v, "S256")
        assert ch == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    def test_challenge_length(self) -> None:
        v = generate_verifier()
        assert len(compute_challenge(v, "S256")) == 43

    def test_pair_generation(self) -> None:
        pair = PKCEPair.generate()
        assert compute_challenge(pair.verifier, "S256") == pair.challenge
        assert pair.method == "S256"

    def test_deterministic(self) -> None:
        v = generate_verifier()
        assert compute_challenge(v, "S256") == compute_challenge(v, "S256")

    def test_unsupported_method(self) -> None:
        with pytest.raises(ValueError):
            compute_challenge("verifier", "HS256")


class TestTokenVault:
    def _vault(self) -> TokenVault:
        return TokenVault("b" * 64)

    def test_roundtrip(self) -> None:
        vault = self._vault()
        blob = vault.encrypt("gho_my_access_token")
        assert blob.startswith("v1.")
        assert blob != "gho_my_access_token"
        assert vault.decrypt(blob) == "gho_my_access_token"

    def test_tamper_detected(self) -> None:
        vault = self._vault()
        blob = vault.encrypt("secret")
        corrupted = blob[:-4] + ("AB==" if not blob.endswith("AB==") else "CD==")
        with pytest.raises(InvalidTag):
            vault.decrypt(corrupted)

    def test_unique_ciphertexts(self) -> None:
        vault = self._vault()
        a = vault.encrypt("same")
        b = vault.encrypt("same")
        assert a != b
        assert vault.decrypt(a) == vault.decrypt(b) == "same"

    def test_wrong_key_fails(self) -> None:
        a = self._vault()
        b = TokenVault("c" * 64)
        blob = a.encrypt("secret")
        with pytest.raises(InvalidTag):
            b.decrypt(blob)

    def test_rejects_short_key(self) -> None:
        with pytest.raises(ValueError):
            TokenVault("abc")


class TestPasswords:
    def test_hash_verify_roundtrip(self, settings) -> None:
        encoded = hash_password("correct horse battery staple", settings)
        assert encoded.startswith("$argon2")
        assert verify_password("correct horse battery staple", encoded)
        assert not verify_password("wrong password", encoded)

    def test_hash_is_salted(self, settings) -> None:
        a = hash_password("same password", settings)
        b = hash_password("same password", settings)
        assert a != b
