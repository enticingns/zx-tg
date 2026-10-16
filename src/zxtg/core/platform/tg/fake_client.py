from typing import Any


class FakeTelegramClient:
    """In-memory fake Telegram Bot API client for zero-network testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent_messages: list[dict[str, Any]] = []
        self.set_commands_calls: list[dict[str, Any]] = []
        self.chat_members: dict[tuple[int | str, int | str], dict[str, Any]] = {}
        self.chat_admins: dict[int | str, list[dict[str, Any]]] = {}
        self.chats: dict[int | str, dict[str, Any]] = {}
        self.updates_queue: list[dict[str, Any]] = []
        self.mock_errors: dict[str, Exception] = {}
        self.msg_id_counter: int = 100
        self.closed: bool = False

    def record_call(self, method: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((method, kwargs))
        if method in self.mock_errors:
            err = self.mock_errors[method]
            raise err

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.record_call("get_updates", {"offset": offset, "limit": limit, "timeout": timeout})
        res: list[dict[str, Any]] = []
        while self.updates_queue and len(res) < limit:
            res.append(self.updates_queue.pop(0))
        if not res and timeout > 0:
            import asyncio
            await asyncio.sleep(0.02)
        return res

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.msg_id_counter += 1
        payload = {
            "message_id": self.msg_id_counter,
            "chat": {"id": chat_id},
            "text": text,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        }
        self.record_call("send_message", payload)
        self.sent_messages.append(payload)
        return payload

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        }
        self.record_call("edit_message_text", payload)
        return payload

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        self.record_call("delete_message", {"chat_id": chat_id, "message_id": message_id})
        return True

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        self.record_call("answer_callback_query", {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        })
        return True

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
        scope: dict[str, Any] | None = None,
        language_code: str | None = None,
    ) -> bool:
        payload = {
            "commands": commands,
            "scope": scope,
            "language_code": language_code,
        }
        self.record_call("set_my_commands", payload)
        self.set_commands_calls.append(payload)
        return True

    async def get_chat(self, chat_id: int | str) -> dict[str, Any]:
        self.record_call("get_chat", {"chat_id": chat_id})
        return self.chats.get(chat_id, {"id": chat_id, "type": "group", "title": f"Chat {chat_id}"})

    async def get_chat_member(self, chat_id: int | str, user_id: int | str) -> dict[str, Any]:
        self.record_call("get_chat_member", {"chat_id": chat_id, "user_id": user_id})
        key = (chat_id, user_id)
        if key in self.chat_members:
            return self.chat_members[key]
        return {
            "status": "member",
            "user": {"id": user_id, "first_name": f"User {user_id}", "is_bot": False},
        }

    async def get_chat_administrators(self, chat_id: int | str) -> list[dict[str, Any]]:
        self.record_call("get_chat_administrators", {"chat_id": chat_id})
        return self.chat_admins.get(chat_id, [])

    async def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        permissions: dict[str, Any],
        until_date: int | None = None,
    ) -> bool:
        self.record_call("restrict_chat_member", {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": permissions,
            "until_date": until_date,
        })
        return True

    async def ban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        until_date: int | None = None,
        revoke_messages: bool | None = None,
    ) -> bool:
        self.record_call("ban_chat_member", {
            "chat_id": chat_id,
            "user_id": user_id,
            "until_date": until_date,
            "revoke_messages": revoke_messages,
        })
        return True

    async def unban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        only_if_banned: bool | None = None,
    ) -> bool:
        self.record_call("unban_chat_member", {
            "chat_id": chat_id,
            "user_id": user_id,
            "only_if_banned": only_if_banned,
        })
        return True

    async def leave_chat(self, chat_id: int | str) -> bool:
        self.record_call("leave_chat", {"chat_id": chat_id})
        return True

    async def send_photo(
        self,
        chat_id: int | str,
        photo: bytes | str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        self.msg_id_counter += 1
        payload = {
            "message_id": self.msg_id_counter,
            "chat": {"id": chat_id},
            "photo": photo,
            "caption": caption,
        }
        self.record_call("send_photo", payload)
        self.sent_messages.append(payload)
        return payload

    async def send_document(
        self,
        chat_id: int | str,
        document: bytes | str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        self.msg_id_counter += 1
        payload = {
            "message_id": self.msg_id_counter,
            "chat": {"id": chat_id},
            "document": document,
            "caption": caption,
            "filename": filename,
        }
        self.record_call("send_document", payload)
        self.sent_messages.append(payload)
        return payload

    async def close(self) -> None:
        self.closed = True
