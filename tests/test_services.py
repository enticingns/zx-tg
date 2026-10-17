import asyncio
import datetime
import os
from pathlib import Path
import pytest
from tortoise import Tortoise

from zxtg.core.context import CallContext, GroupView, PluginView, UserView
from zxtg.core.event import Actor, ChatRef, CommandRef, Role, UnifiedEvent
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.guards import (
    ALLOW,
    DENY,
    BuildCommand,
    Dispatch,
    GuardCost,
    GuardLevel,
    GuardSwitch,
    ResolveContext,
)
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.kernel.pipeline import PIPELINE, run_pipeline
from zxtg.core.kernel.registry import registry
from zxtg.core.services.dao import RawSQLError, get_plugin_dao
from zxtg.core.services.db import (
    check_db_integrity,
    close_db,
    get_db_pragmas,
    init_db,
    record_migration,
    run_explicit_migration,
)
from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.group_service import group_service
from zxtg.core.services.impression_service import impression_service
from zxtg.core.services.item_service import item_service
from zxtg.core.services.permission_service import permission_service
from zxtg.core.services.statistics_service import statistics_service
from zxtg.core.services.user_service import user_service
from zxtg.models.group_console import GroupConsole
from zxtg.models.logs import UserGoldLog, UserImpressionLog
from zxtg.models.plugin_info import PluginInfo
from zxtg.models.switch import GroupPluginSwitch
from zxtg.models.user_console import UserConsole


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    registry.clear()
    statistics_service.clear()
    yield
    await close_db()


# =====================================================================
# 1. 用户服务与显示名称回退 (FR-SVC-01, FR-SVC-07, FR-TG-08)
# =====================================================================


@pytest.mark.asyncio
async def test_user_service_crud_and_display_name_fallback():
    """Verify user CRUD, TG native user_id, level/gold/impression, and display name fallback."""
    # Create user with native Telegram user_id (string representation of int)
    user, created = await user_service.get_or_create_user(
        user_id=123456789,
        username="alice_tg",
        full_name="Alice Wonderland",
        level=0,
        gold=100,
        impression=10.0,
    )
    assert created is True
    assert user.user_id == "123456789"
    assert user.platform == "telegram"
    assert user.gold == 100
    assert user.impression == 10.0

    # Display name when username is present
    assert user_service.get_display_name(username="alice_tg", full_name="Alice") == "alice_tg"

    # Display name fallback to full_name when username is None
    assert user_service.get_display_name(username=None, full_name="Alice Wonderland") == "Alice Wonderland"
    assert user_service.get_display_name(username="", full_name="Alice Wonderland") == "Alice Wonderland"

    # Display name fallback to user_id when both are missing
    assert user_service.get_display_name(username=None, full_name="", user_id="123456789") == "123456789"

    # Read and update level
    assert await user_service.get_level(123456789) == 0
    await user_service.set_level(123456789, 10)
    assert await user_service.get_level(123456789) == 10


# =====================================================================
# 2. 群服务与插件开关初始化 (FR-SVC-04, FR-SVC-08, FR-PLG-09, FR-AUTH-11)
# =====================================================================


@pytest.mark.asyncio
async def test_group_service_crud_and_switch_initialization():
    """Verify group CRUD, TG native chat_id, level, and switch initialization according to default_status."""
    # Pre-register a plugin with default_status=False and one with default_status=True
    await PluginInfo.create(
        module="plg_enabled",
        module_path="plugins.plg_enabled",
        name="Enabled Plugin",
        default_status=True,
    )
    await PluginInfo.create(
        module="plg_disabled",
        module_path="plugins.plg_disabled",
        name="Disabled Plugin",
        default_status=False,
    )

    # Initialize a new group
    group, created = await group_service.get_or_create_group(
        chat_id="-100987654321",
        title="Test Group",
        member_count=42,
        level=5,
    )
    assert created is True
    assert group.group_id == "-100987654321"
    assert group.group_name == "Test Group"
    assert group.level == 5
    assert group.member_count == 42
    assert group.last_active is not None

    # Check switches initialized according to default_status
    sw_enabled = await group_service.get_plugin_switch("-100987654321", "plg_enabled")
    assert sw_enabled is True
    sw_disabled = await group_service.get_plugin_switch("-100987654321", "plg_disabled")
    assert sw_disabled is False

    # Modify switch
    await group_service.set_plugin_switch("-100987654321", "plg_disabled", True)
    assert await group_service.get_plugin_switch("-100987654321", "plg_disabled") is True

    # Idempotent re-initialization does NOT overwrite customized switches
    group2, created2 = await group_service.get_or_create_group(
        chat_id="-100987654321",
        title="Test Group Updated Title",
    )
    assert created2 is False
    assert group2.id == group.id
    assert group2.group_name == "Test Group Updated Title"
    assert await group_service.get_plugin_switch("-100987654321", "plg_disabled") is True


# =====================================================================
# 3. 金币与好感度原子扣费、并发防超扣与拒绝透支 (FR-SVC-02, FR-SVC-03, FR-SVC-05)
# =====================================================================


@pytest.mark.asyncio
async def test_atomic_gold_deduction_and_rejection():
    """Verify atomic gold deduction: insufficient balance rejected, zero partial deduct, concurrency safe."""
    uid = "user_econ_1"
    await user_service.get_or_create_user(user_id=uid, gold=100)

    # 1. Insufficient balance rejection: deducting 150 from 100 must fail, balance untouched
    ok, msg = await gold_service.change_gold(uid, -150, reason="test_overdraft")
    assert ok is False
    assert "金币不足" in msg
    assert await gold_service.get_gold(uid) == 100

    # Verify no log was recorded for rejected attempt
    logs = await gold_service.get_logs(uid)
    assert len(logs) == 0

    # 2. Concurrent deduction: 10 concurrent tasks each deducting 20 gold from 100
    # Exactly 5 must succeed, 5 must fail. Final balance must be exactly 0.
    async def try_deduct():
        return await gold_service.change_gold(uid, -20, reason="concurrent_deduct")

    results = await asyncio.gather(*[try_deduct() for _ in range(10)])
    success_count = sum(1 for ok, _ in results if ok)
    fail_count = sum(1 for ok, _ in results if not ok)

    assert success_count == 5
    assert fail_count == 5
    assert await gold_service.get_gold(uid) == 0

    # Exactly 5 audit logs recorded
    logs = await gold_service.get_logs(uid)
    assert len(logs) == 5
    for entry in logs:
        assert entry.amount == -20
        assert entry.reason == "concurrent_deduct"


@pytest.mark.asyncio
async def test_atomic_impression_deduction_and_rejection():
    """Verify atomic impression deduction: insufficient balance rejected and concurrent safe."""
    uid = "user_imp_1"
    await user_service.get_or_create_user(user_id=uid, impression=50.0)

    # Insufficient balance rejection
    ok, msg = await impression_service.change_impression(uid, -100.0, reason="test_overdraft")
    assert ok is False
    assert "好感度不足" in msg
    assert await impression_service.get_impression(uid) == 50.0

    # Concurrent deduction: 10 tasks deducting 10.0 each from 50.0
    async def try_deduct():
        return await impression_service.change_impression(uid, -10.0, reason="concurrent_imp")

    results = await asyncio.gather(*[try_deduct() for _ in range(10)])
    successes = sum(1 for ok, _ in results if ok)
    failures = sum(1 for ok, _ in results if not ok)

    assert successes == 5
    assert failures == 5
    assert abs(await impression_service.get_impression(uid) - 0.0) < 1e-5

    logs = await impression_service.get_logs(uid)
    assert len(logs) == 5
    for l in logs:
        assert l.amount == -10.0
        assert l.reason == "concurrent_imp"


# =====================================================================
# 4. 扣费与成功绑定 (FR-AUTH-09)
# =====================================================================


@pytest.mark.asyncio
async def test_cost_deduction_bound_to_handler_success():
    """FR-AUTH-09: Gold/impression cost is deducted ONLY IF handler succeeds; failure -> no deduct."""
    uid = "user_cost_test"
    await user_service.get_or_create_user(user_id=uid, gold=500, impression=20.0)

    # Plugin with cost_gold=50 and impression=5.0
    manifest = PluginManifest(
        key="costly_plugin",
        name="Costly Plugin",
        cost_gold=50,
        impression=5.0,
        cmds=[Cmd(key="cost_cmd", slash="cost_cmd")],
    )

    should_succeed = True

    async def mock_handler(ctx: CallContext) -> None:
        if not should_succeed:
            raise RuntimeError("Handler computation exploded!")
        await ctx.reply("handler finished successfully")

    registry.register(manifest, {"cost_cmd": mock_handler})

    # Case 1: Handler FAILS -> NO deduction must occur!
    should_succeed = False
    actor = Actor(id=uid, full_name="Cost User")
    event1 = UnifiedEvent(actor=actor, text="/cost_cmd")
    user_view1 = UserView(id=uid, level=0, gold=500, impression=20.0)
    ctx1 = CallContext(event=event1, user=user_view1)

    with pytest.raises(RuntimeError, match="Handler computation exploded!"):
        await run_pipeline(ctx1)

    # Gold and impression MUST remain 500 and 20.0 (NO deduction!)
    assert await gold_service.get_gold(uid) == 500
    assert await impression_service.get_impression(uid) == 20.0
    gold_logs = await gold_service.get_logs(uid)
    assert len(gold_logs) == 0

    # Case 2: Handler SUCCEEDS -> Deduction is applied!
    should_succeed = True
    event2 = UnifiedEvent(actor=actor, text="/cost_cmd")
    user_view2 = UserView(id=uid, level=0, gold=500, impression=20.0)
    ctx2 = CallContext(event=event2, user=user_view2)

    verdict = await run_pipeline(ctx2)
    assert bool(verdict) is True
    assert await gold_service.get_gold(uid) == 450
    assert abs(await impression_service.get_impression(uid) - 15.0) < 1e-5

    # Check logs
    gold_logs = await gold_service.get_logs(uid)
    assert len(gold_logs) == 1
    assert gold_logs[0].amount == -50
    assert gold_logs[0].reason == "cost_costly_plugin"

    imp_logs = await impression_service.get_logs(uid)
    assert len(imp_logs) == 1
    assert imp_logs[0].amount == -5.0
    assert imp_logs[0].reason == "cost_costly_plugin"


# =====================================================================
# 5. 权限服务：角色映射、群级覆盖与超管绕过 (FR-AUTH-08, FR-AUTH-11)
# =====================================================================


def test_permission_service_roles_and_group_override():
    """Verify OWNER=100, ADMIN=10, MEMBER=0, and GroupConsole.level override (FR-AUTH-11)."""
    # 1. Base Role mapping
    assert permission_service.role_to_level("creator") == 100
    assert permission_service.role_to_level("owner") == 100
    assert permission_service.role_to_level(Role.OWNER) == 100

    assert permission_service.role_to_level("administrator") == 10
    assert permission_service.role_to_level(Role.ADMINISTRATOR) == 10

    assert permission_service.role_to_level("member") == 0
    assert permission_service.role_to_level(Role.MEMBER) == 0
    assert permission_service.role_to_level(Role.RESTRICTED) == 0

    # 2. Group level override
    # Member in group with level=5 -> effective level is 5
    group5 = GroupView(id="-100", title="Group 5", level=5)
    assert permission_service.get_effective_level(Role.MEMBER, group=group5) == 5

    # Member in group with level=8 -> effective level is 8
    group8 = GroupView(id="-100", title="Group 8", level=8)
    assert permission_service.get_effective_level(Role.MEMBER, group=group8) == 8

    # Admin and Owner levels are never downgraded by group level
    assert permission_service.get_effective_level(Role.ADMINISTRATOR, group=group5) == 10
    assert permission_service.get_effective_level(Role.OWNER, group=group5) == 100

    # 3. Execution authorization check
    manifest_normal5 = PluginManifest(key="plg_normal5", name="P5", level=5, plugin_type=PluginType.NORMAL)
    manifest_normal8 = PluginManifest(key="plg_normal8", name="P8", level=8, plugin_type=PluginType.NORMAL)
    manifest_admin = PluginManifest(key="plg_admin", name="PAdmin", admin_level=10, plugin_type=PluginType.ADMIN)

    # In group5 (level 5): member can run p5, but CANNOT run p8 or admin plugin
    user_member = UserView(id="u1", level=0)
    assert permission_service.can_execute(user_member, group5, manifest_normal5, role=Role.MEMBER) is True
    assert permission_service.can_execute(user_member, group5, manifest_normal8, role=Role.MEMBER) is False
    assert permission_service.can_execute(user_member, group5, manifest_admin, role=Role.MEMBER) is False

    # In group8 (level 8): member can run p8
    assert permission_service.can_execute(user_member, group8, manifest_normal8, role=Role.MEMBER) is True

    # Admin can run normal and admin plugins
    assert permission_service.can_execute(user_member, group5, manifest_admin, role=Role.ADMINISTRATOR) is True


@pytest.mark.asyncio
async def test_permission_superuser_bypass_when_limit_superuser_false():
    """FR-AUTH-08: When limit_superuser=False, superusers bypass plugin switch and restrictions."""
    # Plugin globally disabled, with limit_superuser=False
    manifest = PluginManifest(
        key="super_plugin",
        name="Super Plugin",
        default_status=False,
        limit_superuser=False,
        cmds=[Cmd(key="super_cmd", slash="super_cmd")],
    )

    executed = []

    async def mock_handler(ctx: CallContext) -> None:
        executed.append(ctx.user.id)

    registry.register(manifest, {"super_cmd": mock_handler})

    # Regular member (level 0) -> Denied by GuardSwitch
    actor_normal = Actor(id=1, full_name="Normal User")
    ctx_normal = CallContext(
        event=UnifiedEvent(actor=actor_normal, text="/super_cmd", role=Role.MEMBER),
        user=UserView(id="1", level=0),
    )
    verdict_normal = await run_pipeline(ctx_normal)
    assert bool(verdict_normal) is False
    assert "插件已全局关闭" in verdict_normal.reason

    # Superuser (level 100, Role.OWNER) -> Bypasses switch and executes!
    actor_owner = Actor(id=999, full_name="Super Owner")
    ctx_owner = CallContext(
        event=UnifiedEvent(actor=actor_owner, text="/super_cmd", role=Role.OWNER),
        user=UserView(id="999", level=100),
    )
    verdict_owner = await run_pipeline(ctx_owner)
    assert bool(verdict_owner) is True
    assert executed == ["999"]


# =====================================================================
# 6. SQLite WAL 与 busy_timeout 生效 (FR-DATA-01, FR-DATA-02)
# =====================================================================


@pytest.mark.asyncio
async def test_sqlite_wal_and_busy_timeout():
    """FR-DATA-01/02: Verify file-backed SQLite enables WAL journal_mode and busy_timeout >= 5000."""
    test_db_file = Path("test_wal_verify.db").resolve()
    if test_db_file.exists():
        test_db_file.unlink()

    try:
        await init_db(db_path=str(test_db_file), generate_schemas=True)
        pragmas = await get_db_pragmas()
        assert pragmas["journal_mode"].lower() == "wal"
        assert pragmas["busy_timeout"] >= 5000
    finally:
        await close_db()
        if test_db_file.exists():
            test_db_file.unlink()
        wal_file = Path(f"{test_db_file}-wal")
        shm_file = Path(f"{test_db_file}-shm")
        if wal_file.exists():
            wal_file.unlink()
        if shm_file.exists():
            shm_file.unlink()


# =====================================================================
# 7. 数据库文件损坏检测与诊断 (FR-DATA-09)
# =====================================================================


@pytest.mark.asyncio
async def test_database_integrity_check():
    """FR-DATA-09: Verify database corruption is detected and diagnosed on startup."""
    # 1. In-memory check returns healthy
    healthy, msg = await check_db_integrity(":memory:")
    assert healthy is True
    assert "ok" in msg

    # 2. Corrupted file database test
    corrupt_file = Path("test_corrupt.db").resolve()
    corrupt_file.write_bytes(b"CORRUPTED_GARBAGE_BYTES_HEADER_NOT_A_SQLITE_DB")

    try:
        is_ok, diagnosis = await check_db_integrity(str(corrupt_file))
        assert is_ok is False
        assert "Database file corruption" in diagnosis or "file is not a database" in diagnosis
    finally:
        if corrupt_file.exists():
            corrupt_file.unlink()


# =====================================================================
# 8. 高频计数缓冲与批量落盘 (FR-DATA-03)
# =====================================================================


@pytest.mark.asyncio
async def test_high_frequency_counter_buffer_and_batch_flush():
    """FR-DATA-03: N calls do NOT trigger N database writes; flush batch writes total count."""
    statistics_service.clear()

    # Call record_call 100 times in memory
    for i in range(100):
        statistics_service.record_call(
            plugin_key="high_freq_plugin",
            user_id="user_stat_1",
            group_id="-10099",
            count=1,
        )

    # Assert 0 database writes occurred!
    assert statistics_service.db_write_count == 0
    assert statistics_service.get_buffered_count("high_freq_plugin", "user_stat_1", "-10099") == 100

    # Total count combines DB and buffer
    total_before = await statistics_service.get_total_count("high_freq_plugin", "user_stat_1", "-10099")
    assert total_before == 100

    # Batch flush: exactly 1 database write operation performed for the batch
    flushed_records = await statistics_service.flush()
    assert flushed_records == 1
    assert statistics_service.db_write_count == 1
    assert statistics_service.get_buffered_count("high_freq_plugin", "user_stat_1", "-10099") == 0

    # Total count after flush is still 100 (now retrieved from DB)
    total_after = await statistics_service.get_total_count("high_freq_plugin", "user_stat_1", "-10099")
    assert total_after == 100

    # Subsequent flush on empty buffer produces 0 writes
    flushed_again = await statistics_service.flush()
    assert flushed_again == 0
    assert statistics_service.db_write_count == 1


# =====================================================================
# 9. 插件裸 SQL 防护 (FR-DATA-04)
# =====================================================================


def test_plugin_raw_sql_protection():
    """FR-DATA-04: Plugins cannot execute raw SQL; attempting raw SQL raises RawSQLError."""
    dao = get_plugin_dao(plugin_key="sample_plugin")
    with pytest.raises(RawSQLError, match="Direct raw SQL execution is strictly forbidden"):
        dao.execute_raw_sql("DROP TABLE user_console;")


# =====================================================================
# 10. 群与用户初始化幂等性
# =====================================================================


@pytest.mark.asyncio
async def test_resolve_context_idempotence():
    """Verify ResolveContext is idempotent across multiple calls without duplicating records."""
    actor = Actor(id="idemp_user_1", username="idemp_name", full_name="Idempotent User")
    chat = ChatRef(id="-1008888", type="supergroup", title="Idempotent Chat")
    event = UnifiedEvent(actor=actor, chat=chat, text="test")

    ctx = CallContext(event=event, user=UserView(id="idemp_user_1"))

    # First resolution
    v1 = await ResolveContext(ctx)
    assert bool(v1) is True
    assert ctx.user.id == "idemp_user_1"
    assert ctx.group.id == "-1008888"

    # User and Group created in DB
    user_count1 = await UserConsole.filter(user_id="idemp_user_1").count()
    group_count1 = await GroupConsole.filter(group_id="-1008888").count()
    assert user_count1 == 1
    assert group_count1 == 1

    # Second resolution with same event: must not duplicate or fail
    v2 = await ResolveContext(ctx)
    assert bool(v2) is True

    user_count2 = await UserConsole.filter(user_id="idemp_user_1").count()
    group_count2 = await GroupConsole.filter(group_id="-1008888").count()
    assert user_count2 == 1
    assert group_count2 == 1


# =====================================================================
# 11. 道具服务：持有、使用与过期处理 (FR-SVC-06)
# =====================================================================


@pytest.mark.asyncio
async def test_item_service_holding_using_and_expiration():
    """FR-SVC-06: Verify item service holding, using, and expiration lifecycle."""
    uid = "user_item_test"

    # 1. Add permanent item
    item1 = await item_service.add_item(user_id=uid, item_id="coffee", count=3)
    assert item1.count == 3
    assert await item_service.has_item(uid, "coffee", min_count=3) is True

    # 2. Add expiring item (already expired)
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    await item_service.add_item(user_id=uid, item_id="expired_potion", count=1, expire_at=past)

    # Expired item is not counted as usable
    assert await item_service.has_item(uid, "expired_potion") is False

    # Attempting to use expired item fails
    ok_exp, msg_exp = await item_service.use_item(uid, "expired_potion", count=1)
    assert ok_exp is False
    assert "道具数量不足" in msg_exp

    # 3. Use permanent item
    ok, msg = await item_service.use_item(uid, "coffee", count=2)
    assert ok is True
    assert "使用成功" in msg
    assert await item_service.has_item(uid, "coffee", min_count=2) is False
    assert await item_service.has_item(uid, "coffee", min_count=1) is True

    # 4. Clean expired items
    cleaned = await item_service.clean_expired_items()
    assert cleaned >= 1


# =====================================================================
# 12. M3FIX 复核修正测试
# =====================================================================


@pytest.mark.asyncio
async def test_dispatch_cost_requires_initialized_db(monkeypatch):
    """M3FIX: Cost deduction requires an initialized database; raises RuntimeError and does not alter user view."""
    from tortoise.context import _current_context

    token = _current_context.set(None)
    try:
        assert not Tortoise._inited

        manifest = PluginManifest(
            key="costly_no_db",
            name="Costly No DB",
            cost_gold=50,
            cmds=[Cmd(key="costly_cmd", slash="costly_cmd")],
        )

        executed = []

        async def mock_handler(ctx: CallContext) -> None:
            executed.append("run")
            await ctx.reply("handler executed")

        registry.register(manifest, {"costly_cmd": mock_handler})

        actor = Actor(id="user_uninit", full_name="Uninit User")
        event = UnifiedEvent(actor=actor, text="/costly_cmd")
        user_view = UserView(id="user_uninit", level=0, gold=500)
        ctx = CallContext(event=event, user=user_view)

        gold_before = ctx.user.gold
        with pytest.raises(RuntimeError, match="扣费需要已初始化的数据库"):
            await run_pipeline(ctx)

        assert executed == ["run"]
        assert ctx.user.gold == gold_before == 500
    finally:
        _current_context.reset(token)


@pytest.mark.asyncio
async def test_group_init_switch_failure_propagates(monkeypatch):
    """M3FIX: Switch initialization failure during group creation must propagate instead of being swallowed."""
    async def mock_fail(*args, **kwargs):
        raise RuntimeError("Simulated switch initialization database error")

    monkeypatch.setattr(PluginInfo, "all", mock_fail)

    with pytest.raises(RuntimeError, match="Simulated switch initialization database error"):
        await group_service.get_or_create_group(
            chat_id="-100999999",
            title="Fail Group",
        )

