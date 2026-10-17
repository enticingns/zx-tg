from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from zxtg.core.event import UnifiedEvent


@dataclass(frozen=True)
class UserView:
    """Read-only view of a user's runtime state."""

    id: str
    level: int = 0
    gold: int = 0
    impression: float = 0.0


@dataclass(frozen=True)
class GroupView:
    """Read-only view of a group's runtime state."""

    id: str
    title: str = ""
    level: int = 0


@dataclass(frozen=True)
class PluginView:
    """Read-only view of current plugin info and effective configuration."""

    key: str
    name: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SentMessage:
    """Sent message handle with message_id for potential editing or recall."""

    message_id: int
    content: Any = None


class CallContext:
    """Immutable call snapshot and plugin execution context (FR-AUTH-10, Design §5.12)."""

    def __init__(
        self,
        event: UnifiedEvent,
        user: UserView,
        group: GroupView | None = None,
        plugin: PluginView | None = None,
        reply_fn: Callable[[Any], Coroutine[Any, Any, SentMessage]] | None = None,
        action_fn: Callable[[str, dict[str, Any]], Coroutine[Any, Any, Any]] | None = None,
    ) -> None:
        self._event = event
        self._user = user
        self._group = group
        self._plugin = plugin
        self._reply_fn = reply_fn
        self._action_fn = action_fn
        self._replies: list[SentMessage] = []

    @property
    def event(self) -> UnifiedEvent:
        return self._event

    @property
    def user(self) -> UserView:
        return self._user

    @property
    def group(self) -> GroupView | None:
        return self._group

    @property
    def plugin(self) -> PluginView | None:
        return self._plugin

    @property
    def replies(self) -> list[SentMessage]:
        return list(self._replies)

    def __repr__(self) -> str:
        return (
            f"CallContext(event={self._event!r}, "
            f"user={self._user!r}, "
            f"group={self._group!r}, "
            f"plugin={self._plugin!r})"
        )

    # ---- Whitelisted Plugin API (Design §5.12) ----

    async def config(self, key: str) -> Any:
        if self._plugin and key in self._plugin.config:
            return self._plugin.config[key]
        from zxtg.core.services.config_service import config_service

        group_id = self._group.id if self._group else None
        plugin_key = self._plugin.key if self._plugin else None
        return config_service.get(key, group_id=group_id, plugin_key=plugin_key)

    async def cache(self, key: str, ttl: int = 60) -> Any:
        raise NotImplementedError("cache service is not implemented in M0")

    async def reply(self, content: Any) -> SentMessage:
        if self._reply_fn:
            sent = await self._reply_fn(content)
        else:
            msg_id = (self._event.message_id or 0) + len(self._replies) + 1
            sent = SentMessage(message_id=msg_id, content=content)
        self._replies.append(sent)
        return sent

    async def reply_image(self, template: str, data: dict[str, Any]) -> SentMessage:
        raise NotImplementedError("reply_image is not implemented in M0")

    async def edit(self, msg: SentMessage, content: Any) -> None:
        raise NotImplementedError("edit is not implemented in M0")

    async def recall(self, msg: SentMessage, delay: int = 0) -> bool:
        if self._action_fn:
            res = await self._action_fn("recall", {"message_id": msg.message_id, "is_bot_message": True})
            return bool(res)
        return False

    async def keyboard(self, buttons: list[list[Any]]) -> None:
        raise NotImplementedError("keyboard is not implemented in M0")

    async def gold(self, delta: int, reason: str = "") -> bool:
        from zxtg.core.services.gold_service import gold_service

        success, _ = await gold_service.change_gold(self._user.id, delta, reason=reason)
        if success:
            current_gold = await gold_service.get_gold(self._user.id)
            self._user = UserView(
                id=self._user.id,
                level=self._user.level,
                gold=current_gold,
                impression=self._user.impression,
            )
        return success

    async def impression(self, delta: float, reason: str = "") -> bool:
        from zxtg.core.services.impression_service import impression_service

        success, _ = await impression_service.change_impression(self._user.id, delta, reason=reason)
        if success:
            current_imp = await impression_service.get_impression(self._user.id)
            self._user = UserView(
                id=self._user.id,
                level=self._user.level,
                gold=self._user.gold,
                impression=current_imp,
            )
        return success

    async def db(self) -> Any:
        from zxtg.core.services.dao import get_plugin_dao

        plugin_key = self._plugin.key if self._plugin else ""
        return get_plugin_dao(plugin_key)

    async def mute(self, user_id: str, duration: int) -> bool:
        if self._action_fn:
            res = await self._action_fn("mute", {"user_id": user_id, "duration": duration})
            return bool(res)
        return False

    async def unmute(self, user_id: str) -> bool:
        if self._action_fn:
            res = await self._action_fn("unmute", {"user_id": user_id})
            return bool(res)
        return False

    async def kick(self, user_id: str) -> bool:
        if self._action_fn:
            res = await self._action_fn("kick", {"user_id": user_id})
            return bool(res)
        return False

    async def ban(self, user_id: str) -> bool:
        if self._action_fn:
            res = await self._action_fn("ban", {"user_id": user_id})
            return bool(res)
        return False

    async def unban(self, user_id: str) -> bool:
        if self._action_fn:
            res = await self._action_fn("unban", {"user_id": user_id})
            return bool(res)
        return False

    async def leave(self) -> bool:
        if self._action_fn:
            res = await self._action_fn("leave", {})
            return bool(res)
        return False
