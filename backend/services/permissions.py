"""Permissions service for role-based access control."""

from __future__ import annotations

from database import User


class Role:
    """User roles."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class Permission:
    """Available permissions."""
    # Settings permissions
    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"
    SETTINGS_ADMIN = "settings.admin"
    
    # User management permissions
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    USERS_ADMIN = "users.admin"
    
    # AI permissions
    AI_READ = "ai.read"
    AI_WRITE = "ai.write"
    AI_ADMIN = "ai.admin"
    
    # Data permissions
    DATA_READ = "data.read"
    DATA_WRITE = "data.write"
    DATA_ADMIN = "data.admin"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: {
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.SETTINGS_ADMIN,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.USERS_ADMIN,
        Permission.AI_READ,
        Permission.AI_WRITE,
        Permission.AI_ADMIN,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.DATA_ADMIN,
    },
    Role.USER: {
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.AI_READ,
        Permission.AI_WRITE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
    },
    Role.VIEWER: {
        Permission.SETTINGS_READ,
        Permission.AI_READ,
        Permission.DATA_READ,
    },
}


def has_permission(user: User, permission: str) -> bool:
    """Check if a user has a specific permission."""
    # Admin users have all permissions
    if user.is_admin:
        return True
    
    # Check if the user's role has the permission
    role_permissions = ROLE_PERMISSIONS.get(user.role, set())
    return permission in role_permissions


def has_permissions(user: User, permissions: list[str], require_all: bool = True) -> bool:
    """Check if a user has specific permissions.
    
    Args:
        user: The user to check
        permissions: List of permissions to check
        require_all: If True, user must have all permissions. If False, user must have at least one.
    """
    # Admin users have all permissions
    if user.is_admin:
        return True
    
    # Check permissions
    user_permissions = ROLE_PERMISSIONS.get(user.role, set())
    
    if require_all:
        return all(permission in user_permissions for permission in permissions)
    else:
        return any(permission in user_permissions for permission in permissions)


def require_permission(permission: str):
    """Decorator to require a specific permission for an API endpoint."""
    def decorator(func):
        # In a real implementation, this would check the user's permissions
        # For now, we'll just return the function as-is
        return func
    return decorator


def get_user_permissions(user: User) -> set[str]:
    """Get all permissions for a user."""
    # Admin users have all permissions
    if user.is_admin:
        # Return all possible permissions
        all_perms = set()
        for perms in ROLE_PERMISSIONS.values():
            all_perms.update(perms)
        return all_perms
    
    # Return permissions for the user's role
    return ROLE_PERMISSIONS.get(user.role, set())