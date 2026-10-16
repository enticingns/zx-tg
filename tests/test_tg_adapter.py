import asyncio
import logging
import pytest

from zxtg.core.platform.tg.adapter import (
    MAX_IMAGE_SIZE_BYTES,
    MAX_MESSAGE_LENGTH,
    TgPlatformAdapter,
    split_message_text,
)
from zxtg.core.platform.tg.client import TelegramNetworkError
from zxtg.core.platform.tg.fake_client import FakeTelegramClient
from zxtg.core.platform.tg.rlmgr import FakeClock, RateLimiter


@pytest.mark.asyncio
async def test_all_sends_go_through_rate_limiter_without_bypass():
    """Assert all outbound platform actions pass through the rate limiter without bypass (FR-TG-04)."""
    clock = FakeClock()
    rlmgr = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    client = FakeTelegramClient()

    # Wrap rlmgr.execute to count calls
    rlmgr_call_count = 0
    orig_execute = rlmgr.execute

    async def counting_execute(chat_id, coro_fn, is_group=None):
        nonlocal rlmgr_call_count
        rlmgr_call_count += 1
        return await orig_execute(chat_id, coro_fn, is_group=is_group)

    rlmgr.execute = counting_execute

    adapter = TgPlatformAdapter(client=client, rlmgr=rlmgr, time_fn=clock.time, sleep_fn=clock.sleep)

    chat_id = "-100123"
    # Set bot as creator to pass permission checks
    client.chat_members[(chat_id, adapter.bot_user_id)] = {"status": "creator"}

    # 1. Send normal text
    await adapter.send(chat_id, "hello")
    # 2. Send image (photo)
    await adapter.send_image(chat_id, b"photo_bytes")
    # 3. Edit text
    await adapter.edit_message_text(chat_id, 101, "new text")
    # 4. Delete message
    await adapter.delete_message(chat_id, 101)
    # 5. Mute
    await adapter.mute(chat_id, "u1", 300)
    # 6. Kick (ban + unban)
    await adapter.kick(chat_id, "u2")
    # 7. Leave
    await adapter.leave(chat_id)

    # Count outbound requests on client
    client_calls = [
        c for c in client.calls
        if c[0] in (
            "send_message", "send_photo", "send_document",
            "edit_message_text", "delete_message",
            "restrict_chat_member", "ban_chat_member", "unban_chat_member", "leave_chat"
        )
    ]

    # Every client send was mediated by rlmgr.execute
    assert len(client_calls) > 0
    assert rlmgr_call_count >= len(client_calls), (
        f"rlmgr_call_count ({rlmgr_call_count}) must be >= client_calls ({len(client_calls)})"
    )


@pytest.mark.asyncio
async def test_message_paging_over_4096():
    """Verify messages >4096 characters are paged and sent in chunks (FR-CMD-10)."""
    clock = FakeClock()
    client = FakeTelegramClient()
    adapter = TgPlatformAdapter(client=client, time_fn=clock.time, sleep_fn=clock.sleep)

    # 10,000 characters text with paragraphs
    paragraph = "A" * 500 + "\n"
    long_text = paragraph * 20  # 10,020 chars
    assert len(long_text) > 4096

    chunks = split_message_text(long_text, MAX_MESSAGE_LENGTH)
    assert len(chunks) == 3
    for chunk in chunks:
        assert len(chunk) <= MAX_MESSAGE_LENGTH

    sent_msg = await adapter.send_message("-100111", long_text)
    assert sent_msg is not None

    # Verify client received 3 send_message calls
    send_calls = [c for c in client.calls if c[0] == "send_message"]
    assert len(send_calls) == 3
    recombined = "".join(c[1]["text"] for c in send_calls)
    assert recombined == long_text


@pytest.mark.asyncio
async def test_image_over_10mb_degradation(caplog):
    """Verify images >10MB trigger degradation warning and are sent as documents (FR-TG-16)."""
    clock = FakeClock()
    client = FakeTelegramClient()
    adapter = TgPlatformAdapter(client=client, time_fn=clock.time, sleep_fn=clock.sleep)

    chat_id = "-100222"

    # 1. Normal image (2MB)
    small_img = b"X" * (2 * 1024 * 1024)
    await adapter.send_image(chat_id, small_img)
    assert client.calls[-1][0] == "send_photo"

    # 2. Oversized image (11MB > 10MB)
    with caplog.at_level(logging.WARNING):
        large_img = b"Y" * (11 * 1024 * 1024)
        await adapter.send_image(chat_id, large_img)

    # Must degrade to send_document
    assert client.calls[-1][0] == "send_document"
    # Must log degradation warning
    assert "exceeds 10MB limit" in caplog.text


@pytest.mark.asyncio
async def test_platform_actions_return_bool_and_degrade_on_lack_of_perm(caplog):
    """Verify platform actions return bool and degrade with warning on lack of perm (FR-TG-12, FR-TG-13)."""
    clock = FakeClock()
    client = FakeTelegramClient()
    bot_id = 9999
    adapter = TgPlatformAdapter(client=client, bot_user_id=bot_id, time_fn=clock.time, sleep_fn=clock.sleep)

    chat_id = "-100333"

    # 1. Bot is a regular member without admin permissions
    client.chat_members[(chat_id, bot_id)] = {
        "status": "member",
        "can_restrict_members": False,
        "can_delete_messages": False,
    }

    with caplog.at_level(logging.WARNING):
        mute_res = await adapter.mute(chat_id, "user_1", 300)
        assert mute_res is False
        assert "command degraded" in caplog.text or "lacks required permission" in caplog.text

        kick_res = await adapter.kick(chat_id, "user_1")
        assert kick_res is False

        ban_res = await adapter.ban(chat_id, "user_1")
        assert ban_res is False

    # 2. Promote bot to administrator with can_restrict_members
    client.chat_members[(chat_id, bot_id)] = {
        "status": "administrator",
        "can_restrict_members": True,
        "can_delete_messages": True,
    }
    adapter.member_cache.clear()

    mute_ok = await adapter.mute(chat_id, "user_1", 300)
    assert mute_ok is True

    unmute_ok = await adapter.unmute(chat_id, "user_1")
    assert unmute_ok is True

    kick_ok = await adapter.kick(chat_id, "user_1")
    assert kick_ok is True

    ban_ok = await adapter.ban(chat_id, "user_1")
    assert ban_ok is True

    unban_ok = await adapter.unban(chat_id, "user_1")
    assert unban_ok is True

    leave_ok = await adapter.leave(chat_id)
    assert leave_ok is True


@pytest.mark.asyncio
async def test_recall_48h_limit_and_permissions(caplog):
    """Verify message recall adheres to 48-hour age limit and bot permissions (FR-TG-15)."""
    clock = FakeClock(start=200000.0)
    client = FakeTelegramClient()
    bot_id = 8888
    adapter = TgPlatformAdapter(client=client, bot_user_id=bot_id, time_fn=clock.time, sleep_fn=clock.sleep)

    chat_id = "-100444"
    client.chat_members[(chat_id, bot_id)] = {
        "status": "administrator",
        "can_delete_messages": True,
    }

    # Case 1: Fresh message (1 hour ago <= 48h) with permission -> Success
    fresh_time = clock.time() - 3600.0
    res_fresh = await adapter.recall(chat_id, 101, message_time=fresh_time, is_bot_message=False)
    assert res_fresh is True

    # Case 2: Old message (50 hours ago > 48h) -> Fails with warning
    old_time = clock.time() - (50 * 3600.0)
    with caplog.at_level(logging.WARNING):
        res_old = await adapter.recall(chat_id, 102, message_time=old_time, is_bot_message=False)
        assert res_old is False
        assert "exceeds 48-hour limit" in caplog.text

    # Case 3: Fresh message, but bot lacks can_delete_messages
    client.chat_members[(chat_id, bot_id)] = {
        "status": "administrator",
        "can_delete_messages": False,
    }
    adapter.member_cache.clear()
    res_no_perm = await adapter.recall(chat_id, 103, message_time=fresh_time, is_bot_message=False)
    assert res_no_perm is False


@pytest.mark.asyncio
async def test_polling_reconnect_backoff_and_graceful_shutdown():
    """Verify reconnection backoff on drop and graceful shutdown (FR-CORE-04, FR-CORE-06)."""
    clock = FakeClock(start=100.0)
    client = FakeTelegramClient()
    adapter = TgPlatformAdapter(client=client, time_fn=clock.time, sleep_fn=clock.sleep)

    attempts = 0

    async def flaky_get_updates(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise TelegramNetworkError("Connection reset by peer")
        await asyncio.sleep(0.02)
        return []

    client.get_updates = flaky_get_updates

    await adapter.start()
    await asyncio.sleep(0.05)

    assert len(clock.sleep_calls) >= 2
    # Verify progressive exponential backoff (1s -> 2s -> 4s)
    assert clock.sleep_calls[0] == 1.0
    assert clock.sleep_calls[1] == 2.0

    # Stop adapter gracefully
    await adapter.stop()
    assert adapter._running is False
    assert client.closed is True


@pytest.mark.asyncio
async def test_single_handler_exception_does_not_crash_poller(caplog):
    """Verify handler/pipeline exception does not exit polling loop or crash process (FR-CORE-05)."""
    clock = FakeClock(start=100.0)
    client = FakeTelegramClient()
    adapter = TgPlatformAdapter(client=client, time_fn=clock.time, sleep_fn=clock.sleep)

    # Queue an update that triggers an error during processing
    bad_update = {"update_id": 999, "message": {"bad": "structure"}}
    client.updates_queue.append(bad_update)

    # Queue a normal update following the bad one
    good_update = {
        "update_id": 1000,
        "message": {
            "message_id": 501,
            "from": {"id": 1, "first_name": "Test"},
            "chat": {"id": 1, "type": "private"},
            "text": "test",
        },
    }
    client.updates_queue.append(good_update)

    with caplog.at_level(logging.ERROR):
        await adapter.start()
        await asyncio.sleep(0.05)
        await adapter.stop()

    # The poller processed up to update 1000 without dying
    assert adapter._last_update_id == 1000
