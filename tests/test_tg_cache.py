import pytest
from tortoise import Tortoise

from zxtg.core.event import ChatRef
from zxtg.core.platform.tg.cache import ChatCache, MemberCache
from zxtg.core.platform.tg.fake_client import FakeTelegramClient
from zxtg.core.platform.tg.rlmgr import FakeClock
from zxtg.models.group_console import GroupConsole


@pytest.fixture(autouse=True)
async def init_test_db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["zxtg.models"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_get_chat_member_60s_cache_hit():
    """Verify get_chat_member is cached for <=60s and does not duplicate API calls (FR-TG-05)."""
    clock = FakeClock(start=100.0)
    cache = MemberCache(time_fn=clock.time, ttl=60.0)
    client = FakeTelegramClient()

    client.chat_members[("-1001", "u1")] = {
        "status": "administrator",
        "user": {"id": "u1", "first_name": "Admin1"},
    }

    # 1st call at t=100.0: cache miss, calls client
    m1 = await cache.get_or_fetch(client, "-1001", "u1")
    assert m1["status"] == "administrator"
    assert len([c for c in client.calls if c[0] == "get_chat_member"]) == 1

    # Advance clock to t=130.0 (30s later, within 60s TTL)
    clock.current_time = 130.0
    m2 = await cache.get_or_fetch(client, "-1001", "u1")
    assert m2["status"] == "administrator"
    # Call count MUST still be 1 (cache hit)
    assert len([c for c in client.calls if c[0] == "get_chat_member"]) == 1

    # Advance clock to t=165.0 (65s later, TTL expired)
    clock.current_time = 165.0
    m3 = await cache.get_or_fetch(client, "-1001", "u1")
    assert m3["status"] == "administrator"
    # Call count MUST now be 2 (re-fetched)
    assert len([c for c in client.calls if c[0] == "get_chat_member"]) == 2


@pytest.mark.asyncio
async def test_chat_cache_event_driven_sync_and_get_chat_complement():
    """Verify group info event-driven DB insert and on-demand get_chat complement (FR-TG-06)."""
    clock = FakeClock(start=200.0)
    cache = ChatCache(time_fn=clock.time)
    client = FakeTelegramClient()

    client.chats["-100222"] = {"id": "-100222", "title": "Fetched Group Title"}

    # Event with title already present
    chat_with_title = ChatRef(id="-100111", type="supergroup", title="Provided Title")
    await cache.sync_group_event(chat_with_title, client)

    rec1 = await GroupConsole.get_or_none(group_id="-100111")
    assert rec1 is not None
    assert rec1.group_name == "Provided Title"

    # Event without title: complement with get_chat
    chat_no_title = ChatRef(id="-100222", type="group", title=None)
    await cache.sync_group_event(chat_no_title, client)

    rec2 = await GroupConsole.get_or_none(group_id="-100222")
    assert rec2 is not None
    assert rec2.group_name == "Fetched Group Title"
    assert any(c[0] == "get_chat" for c in client.calls)


@pytest.mark.asyncio
async def test_chat_administrators_sync_on_demand_with_caching():
    """Verify on-demand get_chat_administrators and caching (FR-TG-07)."""
    clock = FakeClock(start=300.0)
    cache = ChatCache(time_fn=clock.time, ttl=60.0)
    client = FakeTelegramClient()

    client.chat_admins["-100333"] = [
        {"status": "creator", "user": {"id": "owner"}},
        {"status": "administrator", "user": {"id": "admin1"}},
    ]

    admins1 = await cache.get_chat_administrators(client, "-100333")
    assert len(admins1) == 2
    assert len([c for c in client.calls if c[0] == "get_chat_administrators"]) == 1

    # Within TTL: cache hit
    clock.current_time = 330.0
    admins2 = await cache.get_chat_administrators(client, "-100333")
    assert len(admins2) == 2
    assert len([c for c in client.calls if c[0] == "get_chat_administrators"]) == 1
