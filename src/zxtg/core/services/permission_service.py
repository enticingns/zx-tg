import logging
from typing import Any

from zxtg.core.event import Role
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import PluginManifest

logger = logging.getLogger("zxtg.services.permission")

ROLE_LEVEL_MAP = {
    "creator": 100,
    "owner": 100,
    "administrator": 10,
    "admin": 10,
    "member": 0,
    "restricted": 0,
    "left": 0,
    "kicked": 0,
}


class PermissionService:
    """Permission service for role-to-level mapping, group override, and authorization (FR-AUTH-08, FR-AUTH-11)."""

    @staticmethod
    def role_to_level(role: Role | str | None) -> int:
        """Map Telegram role to internal level (creator/OWNER=100, administrator=10, member/restricted=0)."""
        if role is None:
            return 0
        if isinstance(role, Role):
            return role.level
        return ROLE_LEVEL_MAP.get(str(role).lower().strip(), 0)

    def get_effective_level(
        self, role: Role | str | None = None, group: Any = None, user_level: int = 0
    ) -> int:
        """Compute effective level: role level -> group level override for regular members -> user level."""
        if user_level >= 100:
            return 100
        base_level = self.role_to_level(role)
        if base_level >= 10:
            return max(base_level, user_level)
        if group is not None:
            group_level = getattr(group, "level", None)
            if group_level is not None:
                return max(group_level, user_level)
        return max(base_level, user_level)

    def can_execute(
        self, user: Any, group: Any, manifest: PluginManifest, role: Role | str | None = None
    ) -> bool:
        """Check whether a user has permission to execute a plugin (FR-AUTH-11)."""
        allowed, _, _ = self.can_execute_detailed(user=user, group=group, manifest=manifest, role=role)
        return allowed

    def can_execute_detailed(
        self, user: Any, group: Any, manifest: PluginManifest, role: Role | str | None = None
    ) -> tuple[bool, str, str]:
        """Check execution permission returning (allowed, reason, tip)."""
        user_level = getattr(user, "level", 0) if user is not None else 0
        effective_level = self.get_effective_level(role=role, group=group, user_level=user_level)

        # Superuser bypass check (FR-AUTH-08)
        if effective_level >= 100 and not manifest.limit_superuser:
            return True, "", ""

        # Admin level requirement
        if manifest.admin_level is not None and effective_level < manifest.admin_level:
            return False, "管理员权限不足", f"需要管理权限等级 {manifest.admin_level}，当前等级 {effective_level}"

        # Plugin type restrictions
        pt = manifest.plugin_type
        if pt == PluginType.SUPERUSER and effective_level < 100:
            return False, "权限不足", f"需要超级用户权限 (等级 {manifest.level})，当前等级 {effective_level}"
        if pt in (PluginType.ADMIN, PluginType.SUPER_AND_ADMIN) and (effective_level < 10 or effective_level < manifest.level):
            return False, "权限不足", f"需要管理员权限 (等级 {manifest.level})，当前等级 {effective_level}"
        if pt == PluginType.NORMAL and group is not None and effective_level < manifest.level:
            return False, "权限不足", f"需要权限等级 {manifest.level}，当前等级 {effective_level}"

        return True, "", ""


permission_service = PermissionService()
