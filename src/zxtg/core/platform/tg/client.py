import logging
from typing import Any

import httpx

from zxtg.core.platform.tg.fake_client import FakeTelegramClient
from zxtg.core.platform.tg.protocol import (
    TelegramAPIError,
    TelegramClient,
    TelegramNetworkError,
    TelegramRetryAfterError,
    mask_token,
    sanitize_text,
)

logger = logging.getLogger("zxtg.platform.tg.client")


class HttpTelegramClient:
    """Thin Telegram Bot API client using httpx.AsyncClient (Design §2.1 L1)."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.telegram.org",
        timeout: float = 35.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def __repr__(self) -> str:
        return f"<HttpTelegramClient token={mask_token(self._token)} base_url={self._base_url}>"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _post(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}/bot{self._token}/{method}"
        client = self._get_client()

        filtered_data = {k: v for k, v in (payload or {}).items() if v is not None}
        try:
            resp = await client.post(
                url,
                json=filtered_data if not files else None,
                data=filtered_data if files else None,
                files=files,
            )
        except Exception as exc:
            msg = sanitize_text(str(exc), self._token)
            raise TelegramNetworkError(f"Network error in {method}: {msg}") from None

        try:
            data = resp.json()
        except Exception:
            raise TelegramAPIError(resp.status_code, f"Non-JSON response: {resp.status_code}")

        if not data.get("ok"):
            err_code = data.get("error_code", resp.status_code)
            desc = sanitize_text(data.get("description", "Unknown error"), self._token)
            params = data.get("parameters", {})
            if err_code == 429 or "retry_after" in params:
                retry_after = float(params.get("retry_after", 1.0))
                raise TelegramRetryAfterError(err_code, desc, params, retry_after=retry_after)
            raise TelegramAPIError(err_code, desc, params)

        return data.get("result")

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._post("getUpdates", {
            "offset": offset,
            "limit": limit,
            "timeout": timeout,
            "allowed_updates": allowed_updates,
        })

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._post("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        })

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._post("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        })

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        res = await self._post("deleteMessage", {
            "chat_id": chat_id,
            "message_id": message_id,
        })
        return bool(res)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        res = await self._post("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        })
        return bool(res)

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
        scope: dict[str, Any] | None = None,
        language_code: str | None = None,
    ) -> bool:
        res = await self._post("setMyCommands", {
            "commands": commands,
            "scope": scope,
            "language_code": language_code,
        })
        return bool(res)

    async def get_chat(self, chat_id: int | str) -> dict[str, Any]:
        return await self._post("getChat", {"chat_id": chat_id})

    async def get_chat_member(self, chat_id: int | str, user_id: int | str) -> dict[str, Any]:
        return await self._post("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    async def get_chat_administrators(self, chat_id: int | str) -> list[dict[str, Any]]:
        return await self._post("getChatAdministrators", {"chat_id": chat_id})

    async def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        permissions: dict[str, Any],
        until_date: int | None = None,
    ) -> bool:
        res = await self._post("restrictChatMember", {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": permissions,
            "until_date": until_date,
        })
        return bool(res)

    async def ban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        until_date: int | None = None,
        revoke_messages: bool | None = None,
    ) -> bool:
        res = await self._post("banChatMember", {
            "chat_id": chat_id,
            "user_id": user_id,
            "until_date": until_date,
            "revoke_messages": revoke_messages,
        })
        return bool(res)

    async def unban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        only_if_banned: bool | None = None,
    ) -> bool:
        res = await self._post("unbanChatMember", {
            "chat_id": chat_id,
            "user_id": user_id,
            "only_if_banned": only_if_banned,
        })
        return bool(res)

    async def leave_chat(self, chat_id: int | str) -> bool:
        res = await self._post("leaveChat", {"chat_id": chat_id})
        return bool(res)

    async def send_photo(
        self,
        chat_id: int | str,
        photo: bytes | str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(photo, bytes):
            files = {"photo": ("photo.jpg", photo, "image/jpeg")}
            payload = {"chat_id": chat_id, "caption": caption}
            return await self._post("sendPhoto", payload=payload, files=files)
        return await self._post("sendPhoto", {"chat_id": chat_id, "photo": photo, "caption": caption})

    async def send_document(
        self,
        chat_id: int | str,
        document: bytes | str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(document, bytes):
            fname = filename or "document.bin"
            files = {"document": (fname, document, "application/octet-stream")}
            payload = {"chat_id": chat_id, "caption": caption}
            return await self._post("sendDocument", payload=payload, files=files)
        return await self._post("sendDocument", {"chat_id": chat_id, "document": document, "caption": caption})

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = [
    "TelegramClient",
    "HttpTelegramClient",
    "FakeTelegramClient",
    "TelegramAPIError",
    "TelegramRetryAfterError",
    "TelegramNetworkError",
    "mask_token",
    "sanitize_text",
]
