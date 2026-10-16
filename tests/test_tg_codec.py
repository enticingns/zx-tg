from zxtg.core.event import Actor, Role
from zxtg.core.platform.tg.codec import decode_update, map_telegram_role


def test_codec_6_kinds_of_updates():
    """Verify mapping of all 6 Telegram update kinds to UnifiedEvent (NEXT-TASK-M2 §1.3)."""
    # 1. message (text)
    upd_msg = {
        "update_id": 1,
        "message": {
            "message_id": 101,
            "from": {"id": 1001, "first_name": "Alice", "username": "alice_tg"},
            "chat": {"id": -1001234567, "type": "supergroup", "title": "Test Group"},
            "text": "Hello world",
        },
    }
    ev_msg = decode_update(upd_msg)
    assert ev_msg.kind == "text"
    assert ev_msg.text == "Hello world"
    assert ev_msg.message_id == 101
    assert ev_msg.actor.id == 1001
    assert ev_msg.actor.username == "alice_tg"
    assert ev_msg.chat.id == -1001234567
    assert ev_msg.chat.type == "supergroup"

    # 2. callback_query
    upd_cb = {
        "update_id": 2,
        "callback_query": {
            "id": "cb_123",
            "from": {"id": 1002, "first_name": "Bob"},
            "message": {
                "message_id": 102,
                "chat": {"id": -1001234567, "type": "supergroup"},
            },
            "data": "k=btn&a=click",
        },
    }
    ev_cb = decode_update(upd_cb)
    assert ev_cb.kind == "callback"
    assert ev_cb.text == "k=btn&a=click"
    assert ev_cb.message_id == 102
    assert ev_cb.actor.id == 1002

    # 3. new_chat_members (join)
    upd_join = {
        "update_id": 3,
        "message": {
            "message_id": 103,
            "chat": {"id": -1001234567, "type": "group"},
            "new_chat_members": [
                {"id": 1003, "first_name": "Charlie", "last_name": "Brown"}
            ],
        },
    }
    ev_join = decode_update(upd_join)
    assert ev_join.kind == "join"
    assert ev_join.actor.id == 1003
    assert ev_join.actor.full_name == "Charlie Brown"

    # 4. left_chat_member (leave)
    upd_leave = {
        "update_id": 4,
        "message": {
            "message_id": 104,
            "chat": {"id": -1001234567, "type": "group"},
            "left_chat_member": {"id": 1004, "first_name": "Dave"},
        },
    }
    ev_leave = decode_update(upd_leave)
    assert ev_leave.kind == "leave"
    assert ev_leave.actor.id == 1004

    # 5. chat_member / my_chat_member (member_update)
    upd_member = {
        "update_id": 5,
        "chat_member": {
            "chat": {"id": -1001234567, "type": "supergroup"},
            "from": {"id": 1005, "first_name": "Admin"},
            "old_chat_member": {"status": "member"},
            "new_chat_member": {"status": "administrator"},
        },
    }
    ev_member = decode_update(upd_member)
    assert ev_member.kind == "member_update"
    assert ev_member.role == Role.ADMINISTRATOR
    assert ev_member.role.level == 10

    # 6. chat_join_request (join_request)
    upd_join_req = {
        "update_id": 6,
        "chat_join_request": {
            "chat": {"id": -1001234567, "type": "supergroup"},
            "from": {"id": 1006, "first_name": "Eve"},
            "bio": "Please let me in",
        },
    }
    ev_join_req = decode_update(upd_join_req)
    assert ev_join_req.kind == "join_request"
    assert ev_join_req.text == "Please let me in"
    assert ev_join_req.actor.id == 1006


def test_role_mapping():
    """Verify Telegram status mapping to Role levels 100/10/0 (Design §4.2)."""
    assert map_telegram_role("creator") == Role.OWNER
    assert map_telegram_role("creator").level == 100

    assert map_telegram_role("administrator") == Role.ADMINISTRATOR
    assert map_telegram_role("administrator").level == 10

    assert map_telegram_role("member") == Role.MEMBER
    assert map_telegram_role("member").level == 0

    assert map_telegram_role("restricted") == Role.MEMBER
    assert map_telegram_role("restricted").level == 0

    assert map_telegram_role("left") == Role.MEMBER
    assert map_telegram_role("kicked") == Role.MEMBER
    assert map_telegram_role(None) == Role.MEMBER


def test_actor_username_fallback():
    """Verify Actor.username fallback to full_name when None or empty (FR-TG-08)."""
    # User without username
    upd_no_username = {
        "update_id": 10,
        "message": {
            "message_id": 201,
            "from": {"id": 2001, "first_name": "John", "last_name": "Doe"},
            "chat": {"id": 2001, "type": "private"},
            "text": "test",
        },
    }
    ev = decode_update(upd_no_username)
    assert ev.actor.username is None
    assert ev.actor.full_name == "John Doe"
    assert ev.actor.display == "John Doe"

    # User with username
    upd_with_username = {
        "update_id": 11,
        "message": {
            "message_id": 202,
            "from": {"id": 2002, "first_name": "Jane", "username": "jane_doe"},
            "chat": {"id": 2002, "type": "private"},
            "text": "test",
        },
    }
    ev2 = decode_update(upd_with_username)
    assert ev2.actor.username == "jane_doe"
    assert ev2.actor.full_name == "Jane"
    assert ev2.actor.display == "jane_doe"
