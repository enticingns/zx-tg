from typing import Any

from zxtg.core.event import Actor, ChatRef, Role, UnifiedEvent


def map_telegram_role(status: str | None) -> Role:
    """Map Telegram ChatMemberStatus to internal unified Role (Design §4.2).

    creator            → OWNER (100)
    administrator      → ADMINISTRATOR (10)
    member/restricted  → MEMBER (0)
    """
    if not status:
        return Role.MEMBER
    status_lower = status.lower()
    if status_lower == "creator":
        return Role.OWNER
    if status_lower == "administrator":
        return Role.ADMINISTRATOR
    # member, restricted, left, kicked, etc. map to MEMBER (level 0)
    return Role.MEMBER


def extract_actor(user_dict: dict[str, Any] | None) -> Actor:
    """Extract Actor from Telegram User object with username fallback (FR-TG-08)."""
    if not user_dict:
        return Actor(id=0, username=None, full_name="Unknown", is_bot=False)

    user_id = user_dict.get("id", 0)
    username = user_dict.get("username") or None
    first_name = user_dict.get("first_name", "")
    last_name = user_dict.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() if last_name else first_name

    return Actor(
        id=user_id,
        username=username,
        full_name=full_name or "Unknown",
        is_bot=bool(user_dict.get("is_bot", False)),
    )


def extract_chat(chat_dict: dict[str, Any] | None) -> ChatRef | None:
    """Extract ChatRef from Telegram Chat object."""
    if not chat_dict:
        return None
    return ChatRef(
        id=chat_dict.get("id", 0),
        type=chat_dict.get("type", "private"),
        title=chat_dict.get("title"),
    )


def decode_update(update: dict[str, Any], role: Role | None = None) -> UnifiedEvent:
    """Decode raw Telegram update dict into UnifiedEvent (Design §2.3, §4.1).

    Supported update kinds:
    - message / edited_message -> kind="text"
    - callback_query           -> kind="callback"
    - new_chat_members         -> kind="join"
    - left_chat_member         -> kind="leave"
    - chat_member              -> kind="member_update"
    - chat_join_request        -> kind="join_request"
    """
    if "callback_query" in update:
        cq = update["callback_query"]
        actor = extract_actor(cq.get("from"))
        msg = cq.get("message") or {}
        chat = extract_chat(msg.get("chat"))
        return UnifiedEvent(
            actor=actor,
            chat=chat,
            kind="callback",
            text=cq.get("data", ""),
            role=role or Role.MEMBER,
            message_id=msg.get("message_id", 0),
            raw=update,
        )

    if "chat_join_request" in update:
        cjr = update["chat_join_request"]
        actor = extract_actor(cjr.get("from"))
        chat = extract_chat(cjr.get("chat"))
        return UnifiedEvent(
            actor=actor,
            chat=chat,
            kind="join_request",
            text=cjr.get("bio", ""),
            role=role or Role.MEMBER,
            message_id=0,
            raw=update,
        )

    if "chat_member" in update or "my_chat_member" in update:
        cm = update.get("chat_member") or update.get("my_chat_member") or {}
        actor = extract_actor(cm.get("from"))
        chat = extract_chat(cm.get("chat"))
        new_status = cm.get("new_chat_member", {}).get("status")
        derived_role = role or map_telegram_role(new_status)
        return UnifiedEvent(
            actor=actor,
            chat=chat,
            kind="member_update",
            text="",
            role=derived_role,
            message_id=0,
            raw=update,
        )

    # message or edited_message
    msg = update.get("message") or update.get("edited_message")
    if msg:
        chat = extract_chat(msg.get("chat"))

        # Check join event
        if "new_chat_members" in msg and msg["new_chat_members"]:
            new_member = msg["new_chat_members"][0]
            actor = extract_actor(new_member)
            return UnifiedEvent(
                actor=actor,
                chat=chat,
                kind="join",
                text="",
                role=role or Role.MEMBER,
                message_id=msg.get("message_id", 0),
                raw=update,
            )

        # Check leave event
        if "left_chat_member" in msg:
            actor = extract_actor(msg["left_chat_member"])
            return UnifiedEvent(
                actor=actor,
                chat=chat,
                kind="leave",
                text="",
                role=role or Role.MEMBER,
                message_id=msg.get("message_id", 0),
                raw=update,
            )

        # Regular text message
        actor = extract_actor(msg.get("from"))
        text = msg.get("text") or msg.get("caption") or ""
        return UnifiedEvent(
            actor=actor,
            chat=chat,
            kind="text",
            text=text,
            role=role or Role.MEMBER,
            message_id=msg.get("message_id", 0),
            raw=update,
        )

    # Fallback for unrecognized update payloads
    actor = Actor(id=0, username=None, full_name="Unknown", is_bot=False)
    return UnifiedEvent(actor=actor, kind="text", text="", role=role or Role.MEMBER, raw=update)
