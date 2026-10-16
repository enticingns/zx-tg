from collections.abc import Callable
import logging
import time
from typing import Any

from tortoise import Tortoise

from zxtg.core.event import ChatRef
from zxtg.core.platform.tg.protocol import TelegramClient
from zxtg.models.group_console import GroupConsole

logger = logging.getLogger("zxtg.platform.tg.cache")


class MemberCache:
    """In-memory cache for get_chat_member results with <=60s TTL (FR-TG-05)."""

    def __init__(
        self,
        time_fn: Callable[[], float] = time.monotonic,
        ttl: float = 60.0,
    ) -> None:
        self._time_fn = time_fn
        self._ttl = ttl
        self._cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

    def get(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        key = (str(chat_id), str(user_id))
        entry = self._cache.get(key)
        if entry is None:
            return None
        cached_time, member_data = entry
        if self._time_fn() - cached_time < self._ttl:
            return member_data
        del self._cache[key]
        return None

    def set(self, chat_id: int | str, user_id: int | str, member_data: dict[str, Any]) -> None:
        key = (str(chat_id), str(user_id))
        self._cache[key] = (self._time_fn(), member_data)

    async def get_or_fetch(
        self,
        client: TelegramClient,
        chat_id: int | str,
        user_id: int | str,
    ) -> dict[str, Any]:
        cached = self.get(chat_id, user_id)
        if cached is not None:
            return cached
        data = await client.get_chat_member(chat_id, user_id)
        self.set(chat_id, user_id, data)
        return data

    def clear(self) -> None:
        self._cache.clear()


class ChatCache:
    """Event-driven group synchronization and on-demand admin cache (FR-TG-06, FR-TG-07)."""

    def __init__(
        self,
        time_fn: Callable[[], float] = time.monotonic,
        ttl: float = 60.0,
    ) -> None:
        self._time_fn = time_fn
        self._ttl = ttl
        self._admin_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def sync_group_event(
        self,
        chat: ChatRef,
        client: TelegramClient | None = None,
    ) -> None:
        """Event-driven group info persistence with on-demand get_chat complement (FR-TG-06)."""
        if not Tortoise._inited:
            return
        if not chat or chat.type not in ("group", "supergroup"):
            return

        group_id = str(chat.id)
        group_record = await GroupConsole.get_or_none(group_id=group_id)

        title = chat.title
        if not title and client is not None:
            try:
                chat_info = await client.get_chat(chat.id)
                title = chat_info.get("title")
            except Exception as exc:
                logger.debug("Failed on-demand get_chat for group %s: %s", group_id, exc)

        if group_record is None:
            await GroupConsole.create(
                group_id=group_id,
                group_name=title or "",
            )
        elif title and group_record.group_name != title:
            group_record.group_name = title
            await group_record.save(update_fields=["group_name"])

    async def get_chat_administrators(
        self,
        client: TelegramClient,
        chat_id: int | str,
    ) -> list[dict[str, Any]]:
        """Fetch chat administrators on demand with TTL caching (FR-TG-07)."""
        cid = str(chat_id)
        entry = self._admin_cache.get(cid)
        if entry is not None:
            cached_time, admins = entry
            if self._time_fn() - cached_time < self._ttl:
                return admins

        admins = await client.get_chat_administrators(chat_id)
        self._admin_cache[cid] = (self._time_fn(), admins)
        return admins

    def clear(self) -> None:
        self._admin_cache.clear()


__all__ = ["MemberCache", "ChatCache"]
