from app.models.user import RoleName

# Which roles can perform which actions.
ROLE_PERMISSIONS = {
    "create_group": {RoleName.super_admin, RoleName.admin},
    "delete_group": {RoleName.super_admin, RoleName.admin},
    "assign_group_member": {RoleName.super_admin, RoleName.admin, RoleName.pastor},
    "transfer_member": {RoleName.super_admin, RoleName.admin},
    "transfer_leader": {RoleName.super_admin, RoleName.admin},
    "invite_user": {RoleName.super_admin, RoleName.admin},
    "manage_roles": {RoleName.super_admin},
    "view_all_groups": {RoleName.super_admin, RoleName.admin, RoleName.pastor},
    "mark_attendance": {RoleName.super_admin, RoleName.admin, RoleName.pastor, RoleName.leader},
    "create_session": {RoleName.super_admin, RoleName.admin, RoleName.pastor, RoleName.leader},
}

def has_permission(user_roles: list[RoleName], permission: str) -> bool:
    """Check if any of the user's roles grant the specified permission."""
    allowed = ROLE_PERMISSIONS.get(permission, set())
    return bool(set(user_roles) & allowed)