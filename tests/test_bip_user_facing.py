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
from zxtg.core.services.config_service import config_service
from zxtg.core.services.db import close_db, init_db
from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.group_service import group_service
from zxtg.core.services.impression_service import impression_service
from zxtg.core.services.item_service import item_service
from zxtg.core.services.user_service import user_service

import plugins.help.plugin as help_plugin
import plugins.shop.plugin as shop_plugin
import plugins.sign_in.plugin as sign_in_plugin


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    registry.clear()
    await registry.startup()
    config_service.set_global("RENDER_ENGINE", "text")
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
# 1. plugins/help/ Tests (FR-BIP-01)
# ==============================================================================


@pytest.mark.asyncio
async def test_help_menu_permission_filtering():
    """Regular user (level 0) should only see normal plugins, not admin/superuser plugins."""
    ctx, replies = make_context("帮助", user_id="1001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]

    # Must contain normal plugins
    assert "帮助菜单" in content
    assert "每日签到" in content
    assert "道具商店" in content
    assert "信息查询" in content

    # Must NOT contain admin or superuser plugins for regular user
    assert "群管理" not in content
    assert "超级用户" not in content


@pytest.mark.asyncio
async def test_help_menu_superuser_sees_all():
    """Superuser (level 100) should see all plugins including admin and superuser."""
    ctx, replies = make_context("/help", user_id="1", level=100)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]

    assert "帮助菜单" in content
    assert "每日签到" in content
    assert "群管理" in content
    assert "超级用户" in content


@pytest.mark.asyncio
async def test_help_single_plugin_detail():
    """Querying single plugin details displays name, usage, commands, and permissions."""
    ctx, replies = make_context("帮助 sign_in", user_id="1001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]

    assert "每日签到" in content
    assert "sign_in" in content
    assert "签到" in content
    assert "/sign" in content
    assert "好感度排行" in content


@pytest.mark.asyncio
async def test_help_single_plugin_permission_denied():
    """Regular user requesting details of an admin plugin is rejected with permission tip."""
    ctx, replies = make_context("帮助 admin", user_id="1001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    assert "权限不足" in replies[0]


@pytest.mark.asyncio
async def test_help_no_plugins_available():
    """Graceful handling when no plugins match or are available."""
    original_plugins = registry._plugins.copy()
    try:
        registry._plugins.clear()
        ctx, replies = make_context("帮助", user_id="1001", level=0)
        await help_plugin.handle_help(ctx)
        assert len(replies) == 1
        assert "当前暂无可用的功能" in replies[0]
    finally:
        registry._plugins = original_plugins


# ==============================================================================
# 2. plugins/sign_in/ Tests (FR-BIP-02)
# ==============================================================================


@pytest.mark.asyncio
async def test_sign_in_first_time_success():
    """First sign in of the day succeeds and grants gold and impression."""
    await user_service.get_or_create_user(user_id="2001", username="alice", gold=100, impression=5.0)

    ctx, replies = make_context("签到", user_id="2001", level=0, gold=100, impression=5.0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]
    assert "签到成功" in content
    assert "获得金币" in content
    assert "获得好感度" in content

    new_gold = await gold_service.get_gold("2001")
    new_imp = await impression_service.get_impression("2001")
    assert new_gold > 100
    assert new_imp > 5.0


@pytest.mark.asyncio
async def test_sign_in_repeat_rejected_balance_unchanged():
    """Repeat sign in on the same day must be rejected with balance remaining strictly unchanged."""
    await user_service.get_or_create_user(user_id="2002", username="bob", gold=100, impression=5.0)

    # First sign in
    ctx1, replies1 = make_context("签到", user_id="2002", level=0)
    await run_pipeline(ctx1)
    gold_after_first = await gold_service.get_gold("2002")
    imp_after_first = await impression_service.get_impression("2002")

    # Second sign in attempt on the same day
    ctx2, replies2 = make_context("签到", user_id="2002", level=0)
    await run_pipeline(ctx2)
    assert len(replies2) == 1
    assert "已经签到过了" in replies2[0]

    # Assert balances strictly unchanged
    gold_after_second = await gold_service.get_gold("2002")
    imp_after_second = await impression_service.get_impression("2002")
    assert gold_after_second == gold_after_first
    assert imp_after_second == imp_after_first


@pytest.mark.asyncio
async def test_sign_in_leaderboard_sorted_correctly():
    """Impression leaderboard ranks users in strictly descending order."""
    await user_service.get_or_create_user(user_id="2010", username="user_low", impression=10.0)
    await user_service.get_or_create_user(user_id="2020", username="user_top", impression=100.0)
    await user_service.get_or_create_user(user_id="2030", username="user_mid", impression=50.0)

    ctx, replies = make_context("好感度排行 全局", user_id="2010", username="user_low", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]

    assert "排行榜" in content
    idx_top = content.find("user_top")
    idx_mid = content.find("user_mid")
    idx_low = content.find("user_low")
    assert idx_top != -1 and idx_mid != -1 and idx_low != -1
    assert idx_top < idx_mid < idx_low


@pytest.mark.asyncio
async def test_sign_in_group_leaderboard():
    """Group leaderboard shows group sign-in participants."""
    gid = "-1008888"
    await group_service.get_or_create_group(chat_id=gid, title="Test Group")
    await user_service.get_or_create_user(user_id="2040", username="guser_a", impression=30.0)

    # Sign in in this group to associate
    ctx_sign, _ = make_context("签到", user_id="2040", username="guser_a", chat_id=gid, level=0)
    await run_pipeline(ctx_sign)

    ctx_rank, replies = make_context("好感度排行", user_id="2040", username="guser_a", chat_id=gid, level=0)
    await run_pipeline(ctx_rank)
    assert len(replies) == 1
    assert "guser_a" in replies[0]


# ==============================================================================
# 3. plugins/shop/ Tests (FR-BIP-03)
# ==============================================================================


@pytest.mark.asyncio
async def test_shop_list_items():
    """Listing items shows configured items with prices and stock."""
    ctx, replies = make_context("商店", user_id="3001", level=0)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    content = replies[0]
    assert "曲奇饼干" in content
    assert "50 金币" in content
    assert "库存" in content


@pytest.mark.asyncio
async def test_shop_normal_buy_success():
    """Normal purchase deducts gold, decrements stock, and delivers item."""
    await user_service.get_or_create_user(user_id="3002", username="buyer", gold=200)

    # Item 'cookie' costs 50 gold, initial stock 10
    ctx, replies = make_context("购买 cookie 2", user_id="3002", level=0, gold=200)
    verdict = await run_pipeline(ctx)
    assert verdict == ALLOW
    assert len(replies) == 1
    assert "购买成功" in replies[0]
    assert "消耗金币：100" in replies[0]

    # Verify gold deducted: 200 - 100 = 100
    gold = await gold_service.get_gold("3002")
    assert gold == 100

    # Verify inventory received 2 cookies
    items = await item_service.get_items("3002")
    cookie_item = next((i for i in items if i.item_id == "cookie"), None)
    assert cookie_item is not None
    assert cookie_item.count == 2

    # Verify stock decremented: 10 - 2 = 8
    shop_items = await shop_plugin._get_shop_items(ctx)
    assert shop_items["cookie"]["stock"] == 8


@pytest.mark.asyncio
async def test_shop_buy_insufficient_gold():
    """Insufficient gold aborts purchase; gold and stock remain strictly unchanged."""
    await user_service.get_or_create_user(user_id="3003", username="poor_buyer", gold=30)
    shop_items_before = await shop_plugin._get_shop_items(None)
    stock_before = shop_items_before["cookie"]["stock"]

    # Cookie costs 50, user has 30
    ctx, replies = make_context("购买 cookie 1", user_id="3003", level=0, gold=30)
    await run_pipeline(ctx)
    assert len(replies) == 1
    assert "金币不足" in replies[0]

    # Balances and stock strictly unchanged
    gold = await gold_service.get_gold("3003")
    assert gold == 30
    shop_items_after = await shop_plugin._get_shop_items(None)
    assert shop_items_after["cookie"]["stock"] == stock_before

    # No items delivered
    items = await item_service.get_items("3003")
    assert len(items) == 0


@pytest.mark.asyncio
async def test_shop_buy_insufficient_stock():
    """Insufficient stock aborts purchase; gold remains unchanged."""
    await user_service.get_or_create_user(user_id="3004", username="rich_buyer", gold=5000)

    # Request 999 items exceeding stock
    ctx, replies = make_context("购买 cookie 999", user_id="3004", level=0, gold=5000)
    await run_pipeline(ctx)
    assert len(replies) == 1
    assert "库存不足" in replies[0]

    # Gold unchanged
    gold = await gold_service.get_gold("3004")
    assert gold == 5000


@pytest.mark.asyncio
async def test_shop_buy_delisted_or_nonexistent():
    """Purchasing delisted or nonexistent item is rejected."""
    await user_service.get_or_create_user(user_id="3005", username="buyer", gold=500)

    ctx, replies = make_context("购买 magic_sword 1", user_id="3005", level=0, gold=500)
    await run_pipeline(ctx)
    assert len(replies) == 1
    assert "不存在或已下架" in replies[0]


@pytest.mark.asyncio
async def test_shop_buy_rollback_on_delivery_failure(monkeypatch):
    """Failure in item delivery rolls back gold deduction and restores stock."""
    await user_service.get_or_create_user(user_id="3006", username="unlucky_buyer", gold=200)

    shop_items = await shop_plugin._get_shop_items(None)
    stock_before = shop_items["cookie"]["stock"]

    async def mock_failed_add_item(*args, **kwargs):
        raise RuntimeError("Simulated DB delivery failure")

    monkeypatch.setattr(item_service, "add_item", mock_failed_add_item)

    ctx, replies = make_context("购买 cookie 1", user_id="3006", level=0, gold=200)
    await run_pipeline(ctx)

    assert len(replies) == 1
    assert "道具发放异常" in replies[0]
    assert "回滚" in replies[0]

    # Assert gold was refunded to 200
    gold_after = await gold_service.get_gold("3006")
    assert gold_after == 200

    # Assert stock was restored
    shop_items_after = await shop_plugin._get_shop_items(None)
    assert shop_items_after["cookie"]["stock"] == stock_before

    # Assert no inventory item created
    items = await item_service.get_items("3006")
    assert len(items) == 0


@pytest.mark.asyncio
async def test_shop_stock_management():
    """Admin can manage stock (shelf/delist/increase) while normal user is rejected."""
    # Normal user attempt rejected
    ctx_norm, rep_norm = make_context("库存 下架 cookie", user_id="3007", level=0)
    await run_pipeline(ctx_norm)
    assert "权限不足" in rep_norm[0]

    # Admin user can delist
    ctx_delist, rep_delist = make_context("库存 下架 cookie", user_id="3008", level=10)
    await run_pipeline(ctx_delist)
    assert "已下架" in rep_delist[0]
    items = await shop_plugin._get_shop_items(ctx_delist)
    assert items["cookie"]["status"] is False

    # Admin user can re-shelf
    ctx_shelf, rep_shelf = make_context("库存 上架 cookie", user_id="3008", level=10)
    await run_pipeline(ctx_shelf)
    assert "已上架" in rep_shelf[0]
    items = await shop_plugin._get_shop_items(ctx_shelf)
    assert items["cookie"]["status"] is True

    # Admin user can increase stock
    cur_stock = items["cookie"]["stock"]
    ctx_add, rep_add = make_context("库存 增加 cookie 5", user_id="3008", level=10)
    await run_pipeline(ctx_add)
    assert "增加库存 5" in rep_add[0]
    items = await shop_plugin._get_shop_items(ctx_add)
    assert items["cookie"]["stock"] == cur_stock + 5


@pytest.mark.asyncio
async def test_shop_stock_persists_across_restart(tmp_path):
    """Writing stock persists to database and is recovered across close_db and init_db (FR-CFG-01)."""
    db_file = str(tmp_path / "test_stock_persist.db")
    await close_db()
    await init_db(db_path=db_file, generate_schemas=True)
    registry.clear()
    await registry.startup()

    try:
        # Step 1: Write stock = 7
        items = await shop_plugin._get_shop_items()
        items["cookie"]["stock"] = 7
        await shop_plugin._save_shop_items(items)

        # Confirm written in current runtime
        current_items = await shop_plugin._get_shop_items()
        assert current_items["cookie"]["stock"] == 7

        # Step 2: Simulate restart: close DB, clear runtime memory, re-init DB
        await close_db()
        registry.clear()
        await init_db(db_path=db_file, generate_schemas=True)
        await registry.startup()

        # Step 3: Read back and assert equality
        restored_items = await shop_plugin._get_shop_items()
        assert restored_items["cookie"]["stock"] == 7
    finally:
        await close_db()
        await init_db(db_path=":memory:", generate_schemas=True)
        registry.clear()
        await registry.startup()


@pytest.mark.asyncio
async def test_shop_purchase_decrements_persisted_stock(tmp_path):
    """Purchasing decrements stock in DB, which persists across close_db and init_db (FR-BIP-03)."""
    db_file = str(tmp_path / "test_purchase_persist.db")
    await close_db()
    await init_db(db_path=db_file, generate_schemas=True)
    registry.clear()
    await registry.startup()

    try:
        # Step 1: Create user with sufficient gold
        await user_service.get_or_create_user(user_id="3099", username="persist_buyer", gold=500)
        items_before = await shop_plugin._get_shop_items()
        initial_stock = items_before["cookie"]["stock"]
        assert initial_stock == 10

        # Step 2: Purchase 1 cookie
        ctx, replies = make_context("购买 cookie 1", user_id="3099", level=0, gold=500)
        verdict = await run_pipeline(ctx)
        assert verdict == ALLOW
        assert len(replies) == 1
        assert "购买成功" in replies[0]

        items_after_buy = await shop_plugin._get_shop_items()
        assert items_after_buy["cookie"]["stock"] == initial_stock - 1

        # Step 3: Simulate restart: close DB, clear memory, re-init DB
        await close_db()
        registry.clear()
        await init_db(db_path=db_file, generate_schemas=True)
        await registry.startup()

        # Step 4: Re-open DB and verify stock is still decremented
        items_restarted = await shop_plugin._get_shop_items()
        assert items_restarted["cookie"]["stock"] == initial_stock - 1
    finally:
        await close_db()
        await init_db(db_path=":memory:", generate_schemas=True)
        registry.clear()
        await registry.startup()

