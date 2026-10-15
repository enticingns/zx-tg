from zxtg.core.event import Actor, ChatRef, CommandRef, Role, UnifiedEvent


def test_role_level_mapping():
    """Verify Role enum has exact required levels (Design §4.2, §1.3)."""
    assert Role.OWNER.level == 100
    assert Role.ADMINISTRATOR.level == 10
    assert Role.MEMBER.level == 0
    assert Role.RESTRICTED.level == 0


def test_actor_display_fallback():
    """Actor.display must fallback to full_name when username is None or empty (FR-TG-08)."""
    # When username is provided
    actor_with_uname = Actor(id=1, username="alice_tg", full_name="Alice Smith")
    assert actor_with_uname.display == "alice_tg"

    # When username is None
    actor_no_uname = Actor(id=2, username=None, full_name="Bob Jones")
    assert actor_no_uname.display == "Bob Jones"

    # When username is empty string
    actor_empty_uname = Actor(id=3, username="", full_name="Charlie Brown")
    assert actor_empty_uname.display == "Charlie Brown"


def test_actor_is_bot_flag():
    actor = Actor(id=42, full_name="Botty", username="botty_bot", is_bot=True)
    assert actor.is_bot is True


def test_chat_ref():
    chat = ChatRef(id="-100123456", type="supergroup", title="Test Group")
    assert chat.id == "-100123456"
    assert chat.type == "supergroup"
    assert chat.title == "Test Group"


def test_command_ref():
    cmd = CommandRef(name="ping", args=["arg1", "arg2"], raw="/ping arg1 arg2")
    assert cmd.name == "ping"
    assert cmd.args == ["arg1", "arg2"]
    assert cmd.raw == "/ping arg1 arg2"


def test_unified_event_creation():
    actor = Actor(id=10, username="user1", full_name="User One")
    chat = ChatRef(id=100, type="group", title="General")
    event = UnifiedEvent(
        actor=actor,
        role=Role.MEMBER,
        chat=chat,
        kind="text",
        text="hello",
        message_id=55,
        raw={"update_id": 999},
    )
    assert event.actor == actor
    assert event.role == Role.MEMBER
    assert event.chat == chat
    assert event.kind == "text"
    assert event.text == "hello"
    assert event.message_id == 55
    assert event.raw == {"update_id": 999}
