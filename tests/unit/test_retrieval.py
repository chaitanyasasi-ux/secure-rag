"""
Unit tests for RBAC retrieval security.

These tests verify that the role_can_access function correctly
determines which documents each role can see.

The actual Qdrant filter uses the same arithmetic:
    required_role_level <= user_role_level

So testing role_can_access covers the security logic completely.
"""
from __future__ import annotations

import pytest
from app.core.roles import RoleLevel, role_can_access


class TestRBACRetrievalSecurity:

    # ── Employee access ───────────────────────────────────────────────────────

    def test_employee_can_see_employee_docs(self):
        assert role_can_access(RoleLevel.EMPLOYEE, 1) is True

    def test_employee_cannot_see_manager_docs(self):
        assert role_can_access(RoleLevel.EMPLOYEE, 2) is False

    def test_employee_cannot_see_admin_docs(self):
        assert role_can_access(RoleLevel.EMPLOYEE, 3) is False

    # ── Manager access ────────────────────────────────────────────────────────

    def test_manager_can_see_employee_docs(self):
        assert role_can_access(RoleLevel.MANAGER, 1) is True

    def test_manager_can_see_manager_docs(self):
        assert role_can_access(RoleLevel.MANAGER, 2) is True

    def test_manager_cannot_see_admin_docs(self):
        assert role_can_access(RoleLevel.MANAGER, 3) is False

    # ── Admin access ──────────────────────────────────────────────────────────

    def test_admin_can_see_employee_docs(self):
        assert role_can_access(RoleLevel.ADMIN, 1) is True

    def test_admin_can_see_manager_docs(self):
        assert role_can_access(RoleLevel.ADMIN, 2) is True

    def test_admin_can_see_admin_docs(self):
        assert role_can_access(RoleLevel.ADMIN, 3) is True

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_boundary_exact_match(self):
        """User with exactly the required level should have access."""
        assert role_can_access(2, 2) is True

    def test_boundary_one_below(self):
        """User one level below required should be denied."""
        assert role_can_access(1, 2) is False

    def test_higher_level_always_passes(self):
        """Higher role level always passes lower required level."""
        assert role_can_access(3, 1) is True
        assert role_can_access(3, 2) is True
        assert role_can_access(3, 3) is True