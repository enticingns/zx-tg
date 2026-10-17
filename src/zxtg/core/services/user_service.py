import logging
from typing import Any

from tortoise import Tortoise

from zxtg.models.user_console import UserConsole

logger = logging.getLogger("zxtg.services.user")


class UserService:
    """User service managing user profiles, levels, economy and display names (FR-SVC-01, FR-SVC-07, FR-TG-08)."""

    @staticmethod
    def get_display_name(
        username: str | None = None,
        full_name: str = "",
        user_id: str | int = "",
    ) -> str:
        """Return username if present, else fallback to full_name, else user_id (FR-TG-08)."""
        if username:
            return username
        if full_name:
            return full_name
        return str(user_id)

    async def get_user(self, user_id: str | int) -> UserConsole | None:
        """Fetch user record by native Telegram user_id (FR-SVC-07)."""
        if not Tortoise._inited:
            return None
        return await UserConsole.get_or_none(user_id=str(user_id))

    async def get_or_create_user(
        self,
        user_id: str | int,
        username: str | None = None,
        full_name: str = "",
        level: int = 0,
        gold: int = 100,
        impression: float = 0.0,
    ) -> tuple[UserConsole, bool]:
        """Idempotently get or create user record by native Telegram user_id."""
        uid = str(user_id)
        user = await UserConsole.get_or_none(user_id=uid)
        if user is not None:
            updated = False
            if username is not None and user.username != username:
                user.username = username
                updated = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True
            if updated:
                await user.save(update_fields=["username", "full_name", "updated_at"])
            return user, False

        user = await UserConsole.create(
            user_id=uid,
            username=username,
            full_name=full_name or "",
            level=level,
            gold=gold,
            impression=impression,
            platform="telegram",
        )
        return user, True

    async def get_level(self, user_id: str | int) -> int:
        """Read user permission level."""
        user = await self.get_user(user_id)
        return user.level if user else 0

    async def set_level(self, user_id: str | int, level: int) -> UserConsole | None:
        """Update user permission level."""
        user = await self.get_user(user_id)
        if user:
            user.level = level
            await user.save(update_fields=["level", "updated_at"])
        return user

    async def get_gold(self, user_id: str | int) -> int:
        """Read user gold balance."""
        user = await self.get_user(user_id)
        return user.gold if user else 0

    async def get_impression(self, user_id: str | int) -> float:
        """Read user impression balance."""
        user = await self.get_user(user_id)
        return user.impression if user else 0.0

    async def update_profile(
        self,
        user_id: str | int,
        username: str | None = None,
        full_name: str | None = None,
    ) -> UserConsole | None:
        """Update username and full_name."""
        user = await self.get_user(user_id)
        if user:
            fields = []
            if username is not None and user.username != username:
                user.username = username
                fields.append("username")
            if full_name is not None and user.full_name != full_name:
                user.full_name = full_name
                fields.append("full_name")
            if fields:
                fields.append("updated_at")
                await user.save(update_fields=fields)
        return user


user_service = UserService()
