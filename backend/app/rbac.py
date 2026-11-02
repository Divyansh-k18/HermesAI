"""Role model and server-side permission checks.

Roles, from most to least privileged: owner, admin, member, viewer.
The frontend may hide controls based on role, but these checks are the only authority.
"""

ROLES: tuple[str, ...] = ("owner", "admin", "member", "viewer")

_PERMISSIONS: dict[str, frozenset[str]] = {
    "org:read": frozenset(ROLES),
    "members:read": frozenset(ROLES),
    "org:settings:write": frozenset({"owner", "admin"}),
    "members:invite": frozenset({"owner", "admin"}),
    "members:manage": frozenset({"owner", "admin"}),
    "audit:read": frozenset({"owner", "admin"}),
}


def can(role: str, permission: str) -> bool:
    allowed = _PERMISSIONS.get(permission)
    if allowed is None:
        raise ValueError(f"Unknown permission: {permission}")
    return role in allowed


def assignable_roles(actor_role: str) -> frozenset[str]:
    """Roles an actor may grant to someone else.

    Owners may grant any role. Admins may grant only member and viewer, so they cannot
    escalate privileges or create owners.
    """
    if actor_role == "owner":
        return frozenset(ROLES)
    if actor_role == "admin":
        return frozenset({"member", "viewer"})
    return frozenset()


def can_manage_target(actor_role: str, target_role: str) -> bool:
    """Whether an actor may change or remove a member who currently holds target_role."""
    if actor_role == "owner":
        return True
    if actor_role == "admin":
        return target_role in {"member", "viewer"}
    return False
