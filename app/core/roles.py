from enum import IntEnum


class RoleLevel(IntEnum):
    """
    Integer-backed enum so that role comparisons are arithmetic, not string-based.
    Higher value = broader access.  Used in RBAC vector filters on Day 3.

    RBAC rule:  user can read chunks where chunk.required_role_level <= user.role_level
    """

    EMPLOYEE = 1
    MANAGER = 2
    ADMIN = 3


# Human-readable name → level.  Used when decoding JWTs / seeding the DB.
ROLE_LEVEL_MAP: dict[str, RoleLevel] = {
    "employee": RoleLevel.EMPLOYEE,
    "manager": RoleLevel.MANAGER,
    "admin": RoleLevel.ADMIN,
}

# Inverse map for display / serialization
LEVEL_ROLE_MAP: dict[int, str] = {v.value: k for k, v in ROLE_LEVEL_MAP.items()}


def role_can_access(user_role_level: int, required_role_level: int) -> bool:
    """
    Central authorization predicate.  Used in retrieval filter construction AND
    in the permission dependency so the logic is never duplicated.
    """
    return user_role_level >= required_role_level
