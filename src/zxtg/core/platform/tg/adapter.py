import asyncio
from collections.abc import Callable, Coroutine
import logging
import time
from typing import Any

from zxtg.core.context import CallContext, SentMessage, UserView
from zxtg.core.event import Role, UnifiedEvent
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.platform.base import PlatformAdapter
from zxtg.core.platform.tg.cache import ChatCache, MemberCache
from zxtg.core.platform.tg.client import HttpTelegramClient, TelegramClient, TelegramNetworkError
from zxtg.core.platform.tg.codec import decode_update, map_telegram_role
from zxtg.core.platform.tg.rlmgr import RateLimiter

logger = logging.getLogger("zxtg.platform.tg.adapter")

MAX_MESSAGE_LENGTH = 4096
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (FR-TG-16)


def split_message_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long text messages into segments <= max_length (FR-CMD-10)."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= max_length:
            current += line
        else:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line

    if current:
        chunks.append(current)
    return chunks


class TgPlatformAdapter(PlatformAdapter):
    """Telegram platform adapter handling polling, rate limits, and lifecycle (Design §2.1 L1)."""

    def __init__(
        self,
        token: str = "",
        client: TelegramClient | None = None,
        rlmgr: RateLimiter | None = None,
        member_cache: MemberCache | None = None,
        chat_cache: ChatCache | None = None,
        bot_user_id: int | str = 0,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep,
    ) -> None:
        self._token = token
        self.client: TelegramClient = client if client is not None else HttpTelegramClient(token=token)
        self.rlmgr: RateLimiter = rlmgr if rlmgr is not None else RateLimiter(time_fn=time_fn, sleep_fn=sleep_fn)
        self.member_cache: MemberCache = member_cache if member_cache is not None else MemberCache(time_fn=time_fn)
        self.chat_cache: ChatCache = chat_cache if chat_cache is not None else ChatCache(time_fn=time_fn)
        self.bot_user_id = bot_user_id
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn

        self._running = False
        self._poll_task: asyncio.Task[None] | None = None
        self._last_update_id: int | None = None

    async def start(self) -> None:
        """Start long polling loop in the background (FR-TG-01, FR-CORE-04)."""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("TgPlatformAdapter started with long polling")

    async def stop(self) -> None:
        """Gracefully stop polling and clean up client resources (FR-CORE-06)."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        logger.info("TgPlatformAdapter stopped gracefully")

    async def _poll_loop(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                offset = self._last_update_id + 1 if self._last_update_id is not None else None
                updates = await self.client.get_updates(offset=offset, timeout=30)
                backoff = 1.0  # Reset backoff on success

                for upd in updates:
                    upd_id = upd.get("update_id")
                    if upd_id is not None:
                        self._last_update_id = upd_id
                    try:
                        await self._process_update(upd)
                    except Exception as exc:
                        # Single handler exception must NOT crash the process (FR-CORE-05)
                        logger.exception("Error processing update %s: %s", upd_id, exc)

            except asyncio.CancelledError:
                break
            except (TelegramNetworkError, Exception) as exc:
                logger.warning("Polling error (reconnecting in %.1fs, cap 60s): %s", backoff, exc)
                await self._sleep_fn(backoff)
                backoff = min(60.0, backoff * 2.0)

    async def _process_update(self, raw_update: dict[str, Any]) -> None:
        event = decode_update(raw_update)
        if event.chat:
            await self.chat_cache.sync_group_event(event.chat, self.client)

        if event.chat and event.chat.type in ("group", "supergroup"):
            try:
                member_data = await self.member_cache.get_or_fetch(self.client, event.chat.id, event.actor.id)
                status = member_data.get("status")
                event.role = map_telegram_role(status)
            except Exception as exc:
                logger.debug("Failed to resolve member role for user %s: %s", event.actor.id, exc)

        async def _reply_callback(content: Any) -> SentMessage:
            target = event.chat.id if event.chat else event.actor.id
            return await self.send(target, content)

        async def _action_callback(action_name: str, kwargs: dict[str, Any]) -> Any:
            chat_id = event.chat.id if event.chat else event.actor.id
            return await self.dispatch_action(action_name, chat_id=chat_id, **kwargs)

        user_view = UserView(id=str(event.actor.id), level=event.role.level)
        ctx = CallContext(
            event=event,
            user=user_view,
            reply_fn=_reply_callback,
            action_fn=_action_callback,
        )
        await run_pipeline(ctx)

    async def handle_webhook_update(self, update: dict[str, Any]) -> None:
        """Reserved entrypoint for webhook delivery (FR-TG-01)."""
        await self._process_update(update)

    async def send(self, target: Any, content: Any) -> SentMessage:
        """Deliver content to platform destination through rate limiter (FR-TG-04)."""
        if isinstance(content, bytes):
            return await self.send_image(target, content)
        text_content = str(content)
        return await self.send_message(target, text_content)

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> SentMessage:
        """Send text message with >4096 paging and strict rate limiter enforcement (FR-CMD-10, FR-TG-04)."""
        segments = split_message_text(text, MAX_MESSAGE_LENGTH)
        last_msg_id = 0
        last_res: dict[str, Any] = {}

        for seg in segments:
            res = await self.rlmgr.execute(
                chat_id,
                lambda s=seg: self.client.send_message(
                    chat_id=chat_id,
                    text=s,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=reply_markup,
                ),
            )
            last_msg_id = res.get("message_id", 0)
            last_res = res

        return SentMessage(message_id=last_msg_id, content=last_res)

    async def send_image(
        self,
        chat_id: int | str,
        photo: bytes | str,
        caption: str | None = None,
    ) -> SentMessage:
        """Send image checking <=10MB limit; degrade to document when oversized (FR-TG-16, FR-TG-04)."""
        is_bytes = isinstance(photo, bytes)
        if is_bytes and len(photo) > MAX_IMAGE_SIZE_BYTES:
            logger.warning(
                "Image size %d exceeds 10MB limit in chat %s; degrading to document (FR-TG-16)",
                len(photo),
                chat_id,
            )
            res = await self.rlmgr.execute(
                chat_id,
                lambda: self.client.send_document(
                    chat_id=chat_id,
                    document=photo,
                    caption=caption,
                    filename="degraded_photo.bin",
                ),
            )
            return SentMessage(message_id=res.get("message_id", 0), content=res)

        res = await self.rlmgr.execute(
            chat_id,
            lambda: self.client.send_photo(chat_id=chat_id, photo=photo, caption=caption),
        )
        return SentMessage(message_id=res.get("message_id", 0), content=res)

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.rlmgr.execute(
            chat_id,
            lambda: self.client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            ),
        )

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        return await self.rlmgr.execute(
            chat_id,
            lambda: self.client.delete_message(chat_id=chat_id, message_id=message_id),
        )

    async def check_bot_permission(self, chat_id: int | str, permission: str) -> bool:
        """Check if bot has required permission in chat; log degradation warning on lack (FR-TG-13)."""
        if not str(chat_id).startswith("-"):
            return True

        bot_id = self.bot_user_id
        if not bot_id:
            return True

        try:
            member = await self.member_cache.get_or_fetch(self.client, chat_id, bot_id)
            status = member.get("status")
            if status == "creator":
                return True
            if status == "administrator":
                has_perm = bool(member.get(permission, False))
                if not has_perm:
                    logger.warning(
                        "Bot lacks required permission '%s' in chat %s; command degraded (FR-TG-13)",
                        permission,
                        chat_id,
                    )
                return has_perm
            logger.warning(
                "Bot is not administrator (status: %s) in chat %s; command degraded (FR-TG-13)",
                status,
                chat_id,
            )
            return False
        except Exception as exc:
            logger.warning("Failed to check bot permissions in chat %s: %s", chat_id, exc)
            return False

    async def mute(self, chat_id: int | str, user_id: int | str, duration: int) -> bool:
        """Mute a chat member; returns bool and warns if permission missing (FR-TG-12, FR-TG-13)."""
        if not await self.check_bot_permission(chat_id, "can_restrict_members"):
            return False
        try:
            until = int(self._time_fn() + duration)
            perms = {"can_send_messages": False}
            res = await self.rlmgr.execute(
                chat_id,
                lambda: self.client.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=perms,
                    until_date=until,
                ),
            )
            return bool(res)
        except Exception as exc:
            logger.warning("Failed mute for user %s in %s: %s", user_id, chat_id, exc)
            return False

    async def unmute(self, chat_id: int | str, user_id: int | str) -> bool:
        """Unmute a chat member (FR-TG-12)."""
        if not await self.check_bot_permission(chat_id, "can_restrict_members"):
            return False
        try:
            perms = {"can_send_messages": True, "can_send_media_messages": True, "can_send_other_messages": True}
            res = await self.rlmgr.execute(
                chat_id,
                lambda: self.client.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=perms,
                ),
            )
            return bool(res)
        except Exception as exc:
            logger.warning("Failed unmute for user %s in %s: %s", user_id, chat_id, exc)
            return False

    async def kick(self, chat_id: int | str, user_id: int | str) -> bool:
        """Kick a chat member (ban then unban); returns bool (FR-TG-12)."""
        if not await self.check_bot_permission(chat_id, "can_restrict_members"):
            return False
        try:
            await self.rlmgr.execute(
                chat_id,
                lambda: self.client.ban_chat_member(chat_id=chat_id, user_id=user_id),
            )
            await self.rlmgr.execute(
                chat_id,
                lambda: self.client.unban_chat_member(chat_id=chat_id, user_id=user_id),
            )
            return True
        except Exception as exc:
            logger.warning("Failed kick for user %s in %s: %s", user_id, chat_id, exc)
            return False

    async def ban(self, chat_id: int | str, user_id: int | str) -> bool:
        """Ban a chat member; returns bool (FR-TG-12)."""
        if not await self.check_bot_permission(chat_id, "can_restrict_members"):
            return False
        try:
            res = await self.rlmgr.execute(
                chat_id,
                lambda: self.client.ban_chat_member(chat_id=chat_id, user_id=user_id),
            )
            return bool(res)
        except Exception as exc:
            logger.warning("Failed ban for user %s in %s: %s", user_id, chat_id, exc)
            return False

    async def unban(self, chat_id: int | str, user_id: int | str) -> bool:
        """Unban a chat member; returns bool (FR-TG-12)."""
        if not await self.check_bot_permission(chat_id, "can_restrict_members"):
            return False
        try:
            res = await self.rlmgr.execute(
                chat_id,
                lambda: self.client.unban_chat_member(chat_id=chat_id, user_id=user_id),
            )
            return bool(res)
        except Exception as exc:
            logger.warning("Failed unban for user %s in %s: %s", user_id, chat_id, exc)
            return False

    async def leave(self, chat_id: int | str) -> bool:
        """Leave a chat; returns bool (FR-TG-12)."""
        try:
            res = await self.rlmgr.execute(chat_id, lambda: self.client.leave_chat(chat_id=chat_id))
            return bool(res)
        except Exception as exc:
            logger.warning("Failed leave for chat %s: %s", chat_id, exc)
            return False

    async def recall(
        self,
        chat_id: int | str,
        message_id: int,
        message_time: float | None = None,
        is_bot_message: bool = False,
    ) -> bool:
        """Recall message with permissions and 48-hour age check (FR-TG-15)."""
        if not is_bot_message:
            if message_time is not None and (self._time_fn() - message_time) > 48 * 3600:
                logger.warning(
                    "Cannot recall message %s in %s: exceeds 48-hour limit (FR-TG-15)",
                    message_id,
                    chat_id,
                )
                return False
            if not await self.check_bot_permission(chat_id, "can_delete_messages"):
                return False

        try:
            return await self.delete_message(chat_id, message_id)
        except Exception as exc:
            logger.warning("Failed recall for message %s in %s: %s", message_id, chat_id, exc)
            return False

    async def dispatch_action(self, action_name: str, chat_id: int | str, **kwargs: Any) -> Any:
        """Dispatch contextual action requests from plugins."""
        match action_name:
            case "mute":
                return await self.mute(chat_id, kwargs["user_id"], kwargs.get("duration", 300))
            case "unmute":
                return await self.unmute(chat_id, kwargs["user_id"])
            case "kick":
                return await self.kick(chat_id, kwargs["user_id"])
            case "ban":
                return await self.ban(chat_id, kwargs["user_id"])
            case "unban":
                return await self.unban(chat_id, kwargs["user_id"])
            case "leave":
                return await self.leave(chat_id)
            case "recall":
                return await self.recall(
                    chat_id,
                    kwargs["message_id"],
                    kwargs.get("message_time"),
                    kwargs.get("is_bot_message", False),
                )
            case _:
                logger.warning("Unknown platform action requested: %s", action_name)
                return False


__all__ = ["TgPlatformAdapter", "split_message_text", "MAX_MESSAGE_LENGTH", "MAX_IMAGE_SIZE_BYTES"]
