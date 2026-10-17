import datetime
import logging
from typing import Any

from tortoise import Tortoise

from zxtg.models.group_console import GroupConsole
from zxtg.models.plugin_info import PluginInfo
from zxtg.models.switch import GroupPluginSwitch

logger = logging.getLogger("zxtg.services.group")


class GroupService:
    """Group service managing group profiles, levels, switches, and activity (FR-SVC-04, FR-SVC-08, FR-PLG-09, FR-AUTH-11)."""

    async def get_group(self, chat_id: str | int) -> GroupConsole | None:
        """Fetch group console record by native Telegram chat_id (FR-SVC-08)."""
        if not Tortoise._inited:
            return None
        return await GroupConsole.get_or_none(group_id=str(chat_id))

    async def get_or_create_group(
        self,
        chat_id: str | int,
        title: str = "",
        member_count: int = 0,
        level: int = 5,
        status: bool = True,
    ) -> tuple[GroupConsole, bool]:
        """Idempotently get or create group record.

        When newly created, initializes group plugin switches based on plugin default_status (FR-PLG-09).
        """
        gid = str(chat_id)
        group = await GroupConsole.get_or_none(group_id=gid)
        now = datetime.datetime.now(datetime.timezone.utc)
        if group is not None:
            updated = False
            if title and group.group_name != title:
                group.group_name = title
                updated = True
            if member_count > 0 and group.member_count != member_count:
                group.member_count = member_count
                if member_count > group.max_member_count:
                    group.max_member_count = member_count
                updated = True
            group.last_active = now
            fields_to_update = (
                ["group_name", "member_count", "max_member_count", "last_active", "updated_at"]
                if updated
                else ["last_active", "updated_at"]
            )
            await group.save(update_fields=fields_to_update)
            return group, False

        group = await GroupConsole.create(
            group_id=gid,
            group_name=title or "",
            member_count=member_count,
            max_member_count=member_count,
            level=level,
            status=status,
            last_active=now,
            platform="telegram",
        )

        # Initialize plugin switches for the new group according to default_status (FR-PLG-09)
        await self._init_group_switches(gid)
        return group, True

    async def _init_group_switches(self, group_id: str) -> None:
        """Populate default group plugin switches for registered plugins."""
        plugins = await PluginInfo.all()
        for p in plugins:
            existing = await GroupPluginSwitch.get_or_none(
                group_id=group_id, plugin_key=p.module
            )
            if existing is None:
                await GroupPluginSwitch.create(
                    group_id=group_id,
                    plugin_key=p.module,
                    status=p.default_status,
                )

    async def set_group_level(self, chat_id: str | int, level: int) -> GroupConsole | None:
        """Update group permission level (FR-AUTH-11)."""
        group = await self.get_group(chat_id)
        if group:
            group.level = level
            await group.save(update_fields=["level", "updated_at"])
        return group

    async def set_group_status(self, chat_id: str | int, status: bool) -> GroupConsole | None:
        """Enable or disable group entirely."""
        group = await self.get_group(chat_id)
        if group:
            group.status = status
            await group.save(update_fields=["status", "updated_at"])
        return group

    async def get_plugin_switch(self, chat_id: str | int, plugin_key: str) -> bool | None:
        """Get group plugin switch status. Returns None if not explicitly configured."""
        sw = await GroupPluginSwitch.get_or_none(group_id=str(chat_id), plugin_key=plugin_key)
        return sw.status if sw else None

    async def set_plugin_switch(
        self, chat_id: str | int, plugin_key: str, status: bool
    ) -> GroupPluginSwitch:
        """Set group plugin switch (FR-PLG-07)."""
        gid = str(chat_id)
        sw, created = await GroupPluginSwitch.get_or_create(
            group_id=gid,
            plugin_key=plugin_key,
            defaults={"status": status},
        )
        if not created and sw.status != status:
            sw.status = status
            await sw.save(update_fields=["status", "updated_at"])
        return sw


group_service = GroupService()
