from typing import Any, Protocol, runtime_checkable


def mask_token(token: str) -> str:
    """Mask bot token to prevent leakage in logs and representations (NFR-09)."""
    if not token:
        return "***"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...***"


def sanitize_text(text: str, token: str) -> str:
    """Strip token occurrences from error messages or URLs."""
    if token and token in text:
        return text.replace(token, mask_token(token))
    return text


class TelegramAPIError(Exception):
    """Raised when Telegram Bot API returns ok: false."""

    def __init__(
        self,
        error_code: int,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.description = description
        self.parameters = parameters or {}
        super().__init__(f"Telegram API error {error_code}: {description}")


class TelegramRetryAfterError(TelegramAPIError):
    """Raised on HTTP 429 Too Many Requests containing retry_after duration."""

    def __init__(
        self,
        error_code: int,
        description: str,
        parameters: dict[str, Any] | None = None,
        retry_after: float = 1.0,
    ) -> None:
        super().__init__(error_code, description, parameters)
        self.retry_after = retry_after


class TelegramNetworkError(Exception):
    """Raised on connection drops, timeouts, or DNS failures."""


@runtime_checkable
class TelegramClient(Protocol):
    """Abstract protocol for Telegram Bot API clients."""

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool: ...

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool: ...

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
        scope: dict[str, Any] | None = None,
        language_code: str | None = None,
    ) -> bool: ...

    async def get_chat(self, chat_id: int | str) -> dict[str, Any]: ...

    async def get_chat_member(self, chat_id: int | str, user_id: int | str) -> dict[str, Any]: ...

    async def get_chat_administrators(self, chat_id: int | str) -> list[dict[str, Any]]: ...

    async def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        permissions: dict[str, Any],
        until_date: int | None = None,
    ) -> bool: ...

    async def ban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        until_date: int | None = None,
        revoke_messages: bool | None = None,
    ) -> bool: ...

    async def unban_chat_member(
        self,
        chat_id: int | str,
        user_id: int | str,
        only_if_banned: bool | None = None,
    ) -> bool: ...

    async def leave_chat(self, chat_id: int | str) -> bool: ...

    async def send_photo(
        self,
        chat_id: int | str,
        photo: bytes | str,
        caption: str | None = None,
    ) -> dict[str, Any]: ...

    async def send_document(
        self,
        chat_id: int | str,
        document: bytes | str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]: ...

    async def close(self) -> None: ...
