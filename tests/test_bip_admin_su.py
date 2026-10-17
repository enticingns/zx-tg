import asyncio
import datetime
import os
from pathlib import Path
import sys
import pytest
from tortoise import Tortoise

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zxtg.core.context import CallContext, GroupView, PluginView, SentMessage, UserView
from zxtg.core.event import Actor, ChatRef, CommandRef, Role, UnifiedEvent
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.guards import ALLOW, DENY
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.kernel.registry import registry
from zxtg.core.services.db import close_db, init_db
from zxtg.core.services.group_service import group_service
from zxtg.core.services.user_service import user_service

import plugins.admin.plugin as admin_plugin
import plugins.info.plugin as info_plugin
import plugins.superuser.plugin as superuser_plugin


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    registry.clear()
    await registry.startup()
    yield
    await close_db()


def make_context(
    text: str,
    user_id: str = "1001",
    username: str | None = None,
    full_name: str = "",
    level: int = 0,
    gold: int = 200,
    impression: float = 10.0,
    chat_id: str | None = "-1009999",
    chat_type: str = "supergroup",
    chat_title: str = "Test Chat",
    action_fn=None,
) -> tuple[CallContext, list[str]]:
    replies: list[str] = []

    async def _reply_fn(content: any) -> SentMessage:
        text_content = str(content)
        replies.append(text_content)
        return SentMessage(message_id=len(replies), content=text_content)

    actor = Actor(id=int(user_id), username=username, full_name=full_name)
    chat = ChatRef(id=int(chat_id) if chat_id else int(user_id), type=chat_type, title=chat_title) if chat_id else None
    if level >= 100:
        role = Role.OWNER
    elif level >= 10:
        role = Role.ADMINISTRATOR
    else:
        role = Role.MEMBER
    event = UnifiedEvent(actor=actor, chat=chat, text=text, role=role)

    user_view = UserView(id=user_id, level=level, gold=gold, impression=impression)
    group_view = GroupView(id=chat_id, title=chat_title, level=5) if chat_id else None

    ctx = CallContext(
        event=event,
        user=user_view,
        group=group_view,
        reply_fn=_reply_fn,
        action_fn=action_fn,
    )
    return ctx, replies


# ==============================================================================
# 4. plugins/admin/ Tests (FR-BIP-04)
# ==============================================================================


@pytest.mark.asyncio
async def test_admin_permission_denied_for_normal_user():
    """Normal user (level 0) calling admin command is blocked by GuardLevel."""
    ctx, replies = make_context("禁言 5001 300", user_id="4001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == DENY(reason="管理员权限不足", tip="需要管理权限等级 10，当前等级 5")
    assert len(replies) == 0


@pytest.mark.asyncio
async def test_admin_platform_false_reported_explicitly():
    """When platform returns False, admin must report failure with readable tip, not pretend success."""

    async def fake_action_returning_false(action_name: str, kwargs: dict) -> bool:
        return False  # Inject platform failure (e.g. lack of bot privileges)

    ctx, replies = make_context(
        "禁言 5002 300",
        user_id="4002",
        level=10,
        action_fn=fake_action_returning_false,
    )
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]
    assert "禁言失败" in content
    assert "权限不足" in content
    assert "已成功禁言" not in content


@pytest.mark.asyncio
async def test_admin_platform_actions_success():
    """When platform returns True, admin actions report success."""

    async def fake_action_returning_true(action_name: str, kwargs: dict) -> bool:
        return True

    for cmd_str, expected in [
        ("禁言 5003 60", "已成功禁言用户 5003"),
        ("解禁 5003", "已成功解除用户 5003 的禁言"),
        ("踢出 5003", "已成功将用户 5003 移出群聊"),
        ("封禁 5003", "已成功将用户 5003 封禁"),
        ("解封 5003", "已成功解除用户 5003 的封禁"),
    ]:
        ctx, replies = make_context(cmd_str, user_id="4003", level=10, action_fn=fake_action_returning_true)
        verdict = await run_pipeline(ctx)
        assert verdict == ALLOW
        assert len(replies) == 1
        assert expected in replies[0]


@pytest.mark.asyncio
async def test_admin_set_and_revoke_admin():
    """Admin can set and revoke user administrator permissions with notifications."""
    await user_service.get_or_create_user(user_id="5005", username="target_user", level=0)

    # Promote to admin
    ctx_set, rep_set = make_context("设置管理 5005", user_id="4004", level=10)
    await run_pipeline(ctx_set)
    assert len(rep_set) == 1
    assert "管理员变更通知" in rep_set[0]
    assert "设置为群管理员" in rep_set[0]
    lvl = await user_service.get_level("5005")
    assert lvl == 10

    # Demote from admin
    ctx_rev, rep_rev = make_context("撤销管理 5005", user_id="4004", level=10)
    await run_pipeline(ctx_rev)
    assert len(rep_rev) == 1
    assert "管理员变更通知" in rep_rev[0]
    assert "撤销用户 5005 的群管理员权限" in rep_rev[0]
    lvl = await user_service.get_level("5005")
    assert lvl == 0


# ==============================================================================
# 5. plugins/info/ Tests (FR-BIP-05)
# ==============================================================================


@pytest.mark.asyncio
async def test_info_user_username_fallback_to_full_name():
    """When username is None, info command displays full_name (FR-TG-08)."""
    await user_service.get_or_create_user(
        user_id="6001",
        username=None,
        full_name="Alice Smith",
        gold=350,
        impression=12.5,
    )

    ctx, replies = make_context("个人信息 6001", user_id="6001", username=None, full_name="Alice Smith", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]
    assert "Alice Smith" in content
    assert "None" not in content
    assert "350" in content
    assert "12.5" in content


@pytest.mark.asyncio
async def test_info_user_fallback_to_user_id():
    """When both username and full_name are empty/None, info command displays user_id (FR-TG-08)."""
    await user_service.get_or_create_user(
        user_id="6002",
        username=None,
        full_name="",
        gold=100,
        impression=0.0,
    )

    ctx, replies = make_context("个人信息 6002", user_id="6002", username=None, full_name="", level=0)
    await run_pipeline(ctx)
    assert len(replies) == 1
    content = replies[0]
    assert "6002" in content


@pytest.mark.asyncio
async def test_info_user_shows_username_when_present():
    """When username is present, info command prioritizes displaying username."""
    await user_service.get_or_create_user(
        user_id="6003",
        username="charlie_tg",
        full_name="Charlie Brown",
    )

    ctx, replies = make_context("个人信息 6003", user_id="6003", username="charlie_tg", full_name="Charlie Brown", level=0)
    await run_pipeline(ctx)
    assert len(replies) == 1
    assert "charlie_tg" in replies[0]


@pytest.mark.asyncio
async def test_info_group_info_success_and_private_rejected():
    """Group info displays group stats in groups and rejects in private chats."""
    # In group
    await group_service.get_or_create_group(chat_id="-1007777", title="Dev Chat", member_count=42)
    ctx_grp, rep_grp = make_context("群信息", user_id="6004", chat_id="-1007777", chat_title="Dev Chat")
    await run_pipeline(ctx_grp)
    assert len(rep_grp) == 1
    assert "Dev Chat" in rep_grp[0]
    assert "-1007777" in rep_grp[0]
    assert "42" in rep_grp[0]

    # In private chat
    ctx_priv, rep_priv = make_context("群信息", user_id="6004", chat_id=None, chat_type="private")
    await run_pipeline(ctx_priv)
    assert len(rep_priv) == 1
    assert "仅在群聊中可用" in rep_priv[0]


@pytest.mark.asyncio
async def test_info_bot_status():
    """Bot status displays core version, plugin count, and platform."""
    ctx, replies = make_context("运行状态", user_id="6005", level=0)
    await run_pipeline(ctx)
    assert len(replies) == 1
    content = replies[0]
    assert "Bot 运行状态" in content
    assert "核心版本" in content
    assert "Telegram" in content


# ==============================================================================
# 6. plugins/superuser/ Tests (FR-BIP-06)
# ==============================================================================


@pytest.mark.asyncio
async def test_superuser_permission_denied_for_normal_user():
    """Normal user calling superuser commands is rejected."""
    ctx, replies = make_context("插件开关 关闭 全局 ping", user_id="7001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == DENY(reason="权限不足", tip="需要超级用户权限 (等级 100)，当前等级 5")
    assert len(replies) == 0


@pytest.mark.asyncio
async def test_superuser_global_switch_effect():
    """Global switch disables plugin globally; enabling restores it."""
    # 1. Superuser disables ping globally
    ctx_off, rep_off = make_context("插件开关 关闭 全局 ping", user_id="1", level=100)
    await run_pipeline(ctx_off)
    assert "已将插件 'ping' 的全局开关设置为: 关闭" in rep_off[0]

    # 2. Normal user calling ping in private chat is rejected by GuardSwitch
    ctx_ping, rep_ping = make_context("ping", user_id="7002", level=0, chat_id=None)
    verdict = await run_pipeline(ctx_ping)
    assert verdict == DENY(reason="插件已全局关闭", tip="发送 /enable ping 开启")

    # 3. Superuser enables ping globally
    ctx_on, rep_on = make_context("插件开关 开启 全局 ping", user_id="1", level=100)
    await run_pipeline(ctx_on)
    assert "已将插件 'ping' 的全局开关设置为: 开启" in rep_on[0]

    # 4. Normal user can call ping again
    ctx_ping2, rep_ping2 = make_context("ping", user_id="7002", level=0, chat_id=None)
    verdict2 = await run_pipeline(ctx_ping2)
    assert verdict2 == ALLOW
    assert rep_ping2[0] == "pong"


@pytest.mark.asyncio
async def test_superuser_group_switch_overrides_global():
    """Group-level switch overrides global switch (FR-AUTH-07)."""
    gid = "-1006666"
    await group_service.get_or_create_group(chat_id=gid, title="Special Group")

    # Disable ping globally
    ctx_off, _ = make_context("插件开关 关闭 全局 ping", user_id="1", level=100)
    await run_pipeline(ctx_off)

    # Enable ping specifically in this group (group override)
    ctx_grp_on, rep_grp_on = make_context("插件开关 开启 本群 ping", user_id="1", level=100, chat_id=gid)
    await run_pipeline(ctx_grp_on)
    assert "已将插件 'ping' 在本群的开关设置为: 开启" in rep_grp_on[0]

    # Normal user in this group CAN call ping despite global switch being OFF!
    ctx_ping_grp, rep_ping_grp = make_context("ping", user_id="7003", level=0, chat_id=gid)
    verdict_grp = await run_pipeline(ctx_ping_grp)
    assert verdict_grp == ALLOW
    assert rep_ping_grp[0] == "pong"

    # Restore global ping to ON for other tests
    ctx_restore, _ = make_context("插件开关 开启 全局 ping", user_id="1", level=100)
    await run_pipeline(ctx_restore)


@pytest.mark.asyncio
async def test_superuser_broadcast_partial_failure_continues_and_summarizes():
    """Broadcast resiliently continues on individual failures and accurately summarizes failures."""
    # Create 3 active groups
    await group_service.get_or_create_group(chat_id="-1001", title="Group 1", status=True)
    await group_service.get_or_create_group(chat_id="-1002", title="Group 2", status=True)
    await group_service.get_or_create_group(chat_id="-1003", title="Group 3", status=True)

    delivered_chats = []

    async def fake_broadcast_send(action_name: str, kwargs: dict) -> bool:
        if action_name == "send_to":
            tgt = str(kwargs.get("target"))
            if tgt == "-1002":
                return False  # Inject platform failure for Group 2
            delivered_chats.append(tgt)
            return True
        return False

    ctx, replies = make_context(
        "广播 全体维护公告",
        user_id="1",
        level=100,
        chat_id=None,
        action_fn=fake_broadcast_send,
    )

    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]

    # Verify broadcast continued past failure
    assert "-1001" in delivered_chats
    assert "-1003" in delivered_chats
    assert len(delivered_chats) == 2

    # Verify summary reported 2 successes and 1 failure without swallowing
    assert "成功发送：2 个群" in content
    assert "发送失败：1 个群" in content
    assert "-1002" in content
    assert "失败详情" in content


@pytest.mark.asyncio
async def test_superuser_maintenance():
    """Data maintenance runs integrity check, cleanup, and stats flush."""
    ctx, replies = make_context("数据维护", user_id="1", level=100)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]
    assert "系统数据维护报告" in content
    assert "数据库完整性检查：正常" in content
    assert "清理过期道具数" in content
    assert "刷新调用统计记录数" in content


@pytest.mark.asyncio
async def test_superuser_leave_group():
    """Superuser leave group invokes ctx.leave()."""
    left_chats = []

    async def fake_leave_action(action_name: str, kwargs: dict) -> bool:
        if action_name == "leave":
            left_chats.append("left")
            return True
        return False

    ctx, replies = make_context("退出本群", user_id="1", level=100, chat_id="-1005555", action_fn=fake_leave_action)
    await run_pipeline(ctx)
    assert len(left_chats) == 1
    assert "正在退出本群" in replies[0]
