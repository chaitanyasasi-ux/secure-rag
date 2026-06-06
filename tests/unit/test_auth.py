"""
Unit tests for Day 1 security primitives.

Run with:
    pytest tests/unit/test_auth.py -v
"""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from app.core.hashing import hash_password, verify_password
from app.core.roles import RoleLevel, role_can_access
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


# ── Password hashing ──────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = hash_password("SecurePass1!")
        assert h != "SecurePass1!"

    def test_verify_correct_password(self):
        h = hash_password("SecurePass1!")
        assert verify_password("SecurePass1!", h) is True

    def test_reject_wrong_password(self):
        h = hash_password("SecurePass1!")
        assert verify_password("WrongPass1!", h) is False

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt salts must differ between hashes."""
        h1 = hash_password("SecurePass1!")
        h2 = hash_password("SecurePass1!")
        assert h1 != h2


# ── JWT creation and decoding ─────────────────────────────────────────────────


def _make_token(**overrides):
    defaults = dict(
        user_id="user-123",
        role="manager",
        role_level=RoleLevel.MANAGER,
        department="engineering",
    )
    return create_access_token(**{**defaults, **overrides})


class TestJWT:
    def test_roundtrip(self):
        token = _make_token()
        payload = decode_access_token(token)
        assert payload.user_id == "user-123"
        assert payload.role == "manager"
        assert payload.role_level == RoleLevel.MANAGER
        assert payload.department == "engineering"

    def test_expired_token_raises(self):
        token = _make_token(expires_delta=timedelta(seconds=-1))
        with pytest.raises(TokenExpiredError):
            decode_access_token(token)

    def test_tampered_signature_raises(self):
        token = _make_token()
        # Flip a character in the signature segment
        parts = token.split(".")
        parts[2] = parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
        with pytest.raises(TokenInvalidError):
            decode_access_token(".".join(parts))

    def test_refresh_token_rejected_as_access(self):
        """A refresh token must not be accepted where an access token is expected."""
        refresh = create_refresh_token(user_id="user-123")
        with pytest.raises(TokenInvalidError, match="not an access token"):
            decode_access_token(refresh)

    def test_access_token_rejected_as_refresh(self):
        """An access token must not be accepted where a refresh token is expected."""
        access = _make_token()
        with pytest.raises(TokenInvalidError, match="not a refresh token"):
            decode_refresh_token(access)

    def test_payload_is_immutable(self):
        payload = decode_access_token(_make_token())
        with pytest.raises(Exception):
            payload.role = "admin"  # type: ignore[misc]

    def test_jti_is_unique_per_token(self):
        t1 = _make_token()
        t2 = _make_token()
        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)
        assert p1.jti != p2.jti


# ── RBAC role_can_access ──────────────────────────────────────────────────────


class TestRoleCanAccess:
    @pytest.mark.parametrize(
        "user_level,required_level,expected",
        [
            # Employee accessing employee content
            (RoleLevel.EMPLOYEE, RoleLevel.EMPLOYEE, True),
            # Employee blocked from manager content
            (RoleLevel.EMPLOYEE, RoleLevel.MANAGER, False),
            # Employee blocked from admin content
            (RoleLevel.EMPLOYEE, RoleLevel.ADMIN, False),
            # Manager accessing employee content (hierarchical access)
            (RoleLevel.MANAGER, RoleLevel.EMPLOYEE, True),
            # Manager accessing own-level content
            (RoleLevel.MANAGER, RoleLevel.MANAGER, True),
            # Manager blocked from admin content
            (RoleLevel.MANAGER, RoleLevel.ADMIN, False),
            # Admin accesses all levels
            (RoleLevel.ADMIN, RoleLevel.EMPLOYEE, True),
            (RoleLevel.ADMIN, RoleLevel.MANAGER, True),
            (RoleLevel.ADMIN, RoleLevel.ADMIN, True),
        ],
    )
    def test_role_matrix(
        self, user_level: RoleLevel, required_level: RoleLevel, expected: bool
    ):
        assert role_can_access(user_level, required_level) is expected
