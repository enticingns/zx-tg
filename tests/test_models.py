import pytest
from tortoise import Tortoise

from zxtg.core.kernel.enums import BlockType, LimitCheckType, LimitWatchType, PluginLimitType, PluginType
from zxtg.core.services.db import close_db, init_db, record_migration, run_migrations
from zxtg.models import (
    FGRequest,
    GroupConsole,
    GroupPluginSwitch,
    JoinRequest,
    MigrationRecord,
    PluginInfo,
    PluginLimit,
    Statistics,
    TaskRecord,
    UserConsole,
    UserGoldLog,
    UserImpressionLog,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    yield
    await close_db()


def test_plugin_info_26_fields_present():
    """Verify PluginInfo has all 26 required fields verbatim (Design §1.2, SRS v1.0 §8)."""
    expected_fields = {
        "id",
        "module",
        "module_path",
        "name",
        "status",
        "block_type",
        "load_status",
        "author",
        "version",
        "level",
        "default_status",
        "limit_superuser",
        "menu_type",
        "plugin_type",
        "cost_gold",
        "admin_level",
        "ignore_prompt",
        "is_delete",
        "parent",
        "is_show",
        "ignore_statistics",
        "impression",
        "plugin_limit",
        "description",
        "usage",
        "superuser_help",
    }
    model_fields = set(PluginInfo._meta.fields_map.keys())
    assert len(expected_fields) == 26
    for f in expected_fields:
        assert f in model_fields, f"Field '{f}' missing from PluginInfo._meta.fields_map"
    assert model_fields == expected_fields, f"Fields mismatch: {model_fields ^ expected_fields}"


@pytest.mark.asyncio
async def test_plugin_info_crud():
    """Test PluginInfo creation, persistence, and queries."""
    plugin = await PluginInfo.create(
        module="ping",
        module_path="plugins.ping",
        name="心跳测试",
        status=True,
        block_type=BlockType.ALL,
        load_status=True,
        author="ZX-TG Team",
        version="1.0.0",
        level=5,
        default_status=True,
        limit_superuser=False,
        menu_type="功能",
        plugin_type=PluginType.NORMAL,
        cost_gold=0,
        admin_level=0,
        ignore_prompt=False,
        is_delete=False,
        parent=None,
        is_show=True,
        ignore_statistics=False,
        impression=0.0,
        description="心跳测试插件",
        usage="/ping",
        superuser_help="/ping debug",
    )
    assert plugin.id is not None
    assert plugin.name == "心跳测试"

    fetched = await PluginInfo.get(module="ping")
    assert fetched.version == "1.0.0"
    assert fetched.plugin_type == PluginType.NORMAL


@pytest.mark.asyncio
async def test_plugin_limit_crud():
    plugin = await PluginInfo.create(
        module="lim_test",
        module_path="plugins.lim_test",
        name="Limit Test",
    )
    limit = await PluginLimit.create(
        module="lim_test",
        plugin=plugin,
        limit_type=PluginLimitType.CD,
        watch_type=LimitWatchType.USER,
        status=True,
        check_type=LimitCheckType.ALL,
        cd=10,
        max_count=5,
        period="1d",
        target_id="user_123",
    )
    assert limit.id is not None
    assert limit.period == "1d"


@pytest.mark.asyncio
async def test_group_console_crud():
    group = await GroupConsole.create(
        group_id="-1009999",
        group_name="Test TG Group",
        member_count=50,
        level=5,
        status=True,
    )
    assert group.id is not None
    assert group.group_id == "-1009999"


@pytest.mark.asyncio
async def test_user_console_crud():
    user = await UserConsole.create(
        user_id="tg_12345",
        username="tg_user",
        full_name="Telegram User",
        gold=200,
        impression=5.5,
    )
    assert user.id is not None
    assert user.gold == 200
    assert user.impression == 5.5


@pytest.mark.asyncio
async def test_logs_crud():
    gold_log = await UserGoldLog.create(
        user_id="tg_12345",
        amount=50,
        reason="sign_in",
    )
    assert gold_log.id is not None
    assert gold_log.gold == 50
    assert gold_log.source == "sign_in"

    imp_log = await UserImpressionLog.create(
        user_id="tg_12345",
        amount=2.5,
        reason="gift",
    )
    assert imp_log.id is not None
    assert imp_log.amount == 2.5


@pytest.mark.asyncio
async def test_switch_crud():
    sw = await GroupPluginSwitch.create(
        group_id="-1009999",
        plugin_key="sign_in",
        status=False,
    )
    assert sw.id is not None
    assert sw.status is False


@pytest.mark.asyncio
async def test_task_record_crud():
    task = await TaskRecord.create(
        task_key="sign_in:daily_reset",
        group_id="-1009999",
        status=True,
    )
    assert task.id is not None
    assert task.status is True


@pytest.mark.asyncio
async def test_statistics_crud():
    stat = await Statistics.create(
        plugin_key="ping",
        user_id="tg_12345",
        group_id="-1009999",
        count=1,
    )
    assert stat.id is not None
    assert stat.plugin_name == "ping"


@pytest.mark.asyncio
async def test_join_request_crud():
    req = await JoinRequest.create(
        request_id="req_abc",
        user_id="tg_12345",
        group_id="-1009999",
        type="GROUP",
        handle_type="PENDING",
    )
    assert req.id is not None
    assert FGRequest == JoinRequest


@pytest.mark.asyncio
async def test_migration_record_crud():
    mig = await MigrationRecord.create(
        plugin_key="ping",
        version="1.0.0",
    )
    assert mig.id is not None

    rec = await record_migration("ping", "1.0.0")
    assert rec.version == "1.0.0"

    applied = await run_migrations("ping", "1.0.1")
    assert "1.0.1" in applied
