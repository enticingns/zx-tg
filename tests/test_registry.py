import pytest
from tortoise import Tortoise

from zxtg.core.context import CallContext, GroupView, UserView
from zxtg.core.event import Actor, ChatRef, UnifiedEvent
from zxtg.core.kernel.manifest import Cmd, ConfigSpec, PluginManifest
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.kernel.registry import PluginRegistry
from zxtg.core.services.db import close_db, init_db
from zxtg.models.plugin_info import PluginInfo
from zxtg.models.switch import GroupPluginSwitch


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    yield
    await close_db()


def test_plugin_key_validation():
    """Verify valid and invalid plugin key formats (FR-PLG-03)."""
    # Valid
    m_valid = PluginManifest(key="sign_in", name="签到")
    assert m_valid.key == "sign_in"

    # Invalid uppercase
    with pytest.raises(ValueError, match="violates regex"):
        PluginManifest(key="Sign_in", name="Bad")

    # Invalid leading digit
    with pytest.raises(ValueError, match="violates regex"):
        PluginManifest(key="1sign", name="Bad")

    # Invalid too short (<3 chars)
    with pytest.raises(ValueError, match="violates regex"):
        PluginManifest(key="ab", name="Bad")


def test_plugin_key_conflict_fails_with_conflicting_parties():
    """Key conflict fails and prints both conflicting parties (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(key="duplicate_pkg", name="插件甲")
    m2 = PluginManifest(key="duplicate_pkg", name="插件乙")

    with pytest.raises(ValueError) as exc_info:
        reg.validate([m1, m2])

    err = str(exc_info.value)
    assert "duplicate_pkg" in err
    assert "插件甲" in err
    assert "插件乙" in err


def test_command_key_conflict_fails_with_conflicting_parties():
    """Command key conflict fails and prints conflicting parties (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(
        key="plugin_one",
        name="插件一",
        cmds=[Cmd(key="clash_cmd", pattern="one", slash="cmd_one")],
    )
    m2 = PluginManifest(
        key="plugin_two",
        name="插件二",
        cmds=[Cmd(key="clash_cmd", pattern="two", slash="cmd_two")],
    )

    with pytest.raises(ValueError) as exc_info:
        reg.validate([m1, m2])

    err = str(exc_info.value)
    assert "clash_cmd" in err
    assert "plugin_one" in err
    assert "plugin_two" in err


def test_command_slash_conflict_fails_with_conflicting_parties():
    """Command slash conflict fails and prints conflicting parties (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(
        key="plugin_one",
        name="插件一",
        cmds=[Cmd(key="cmd_one", slash="same_slash")],
    )
    m2 = PluginManifest(
        key="plugin_two",
        name="插件二",
        cmds=[Cmd(key="cmd_two", slash="same_slash")],
    )

    with pytest.raises(ValueError) as exc_info:
        reg.validate([m1, m2])

    err = str(exc_info.value)
    assert "same_slash" in err
    assert "plugin_one" in err
    assert "plugin_two" in err


def test_command_pattern_conflict_fails_with_conflicting_parties():
    """Command pattern conflict fails and prints conflicting parties (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(
        key="plugin_one",
        name="插件一",
        cmds=[Cmd(key="cmd_one", pattern="签到", slash="sign_one")],
    )
    m2 = PluginManifest(
        key="plugin_two",
        name="插件二",
        cmds=[Cmd(key="cmd_two", pattern="签到", slash="sign_two")],
    )

    with pytest.raises(ValueError) as exc_info:
        reg.validate([m1, m2])

    err = str(exc_info.value)
    assert "签到" in err
    assert "plugin_one" in err
    assert "plugin_two" in err


def test_command_pattern_prefix_conflict_fails_with_conflicting_parties():
    """Pattern prefix conflict fails and prints conflicting parties (FR-CMD-09, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(
        key="plugin_one",
        name="插件一",
        cmds=[Cmd(key="cmd_one", pattern="签到", slash="sign_one")],
    )
    m2 = PluginManifest(
        key="plugin_two",
        name="插件二",
        cmds=[Cmd(key="cmd_two", pattern="签到排行", slash="sign_two")],
    )

    with pytest.raises(ValueError) as exc_info:
        reg.validate([m1, m2])

    err = str(exc_info.value)
    assert "prefix conflict" in err.lower()
    assert "签到" in err
    assert "签到排行" in err
    assert "plugin_one" in err
    assert "plugin_two" in err


def test_requires_missing_fails():
    """Missing required plugin fails startup (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m = PluginManifest(
        key="child_pkg",
        name="子插件",
        requires=["non_existent_dep"],
    )

    with pytest.raises(ValueError, match="Missing dependency.*non_existent_dep"):
        reg.validate([m])


def test_requires_cycle_fails():
    """Circular requires dependency fails startup (FR-PLG-04, §3)."""
    reg = PluginRegistry()
    m1 = PluginManifest(key="plugin_a", name="A", requires=["plugin_b"])
    m2 = PluginManifest(key="plugin_b", name="B", requires=["plugin_a"])

    with pytest.raises(ValueError, match="Circular dependency detected"):
        reg.validate([m1, m2])


def test_requires_core_mismatch_fails():
    """requires_core mismatch fails startup (FR-PLG-06, §3)."""
    reg = PluginRegistry(core_version="1.0.0")
    m = PluginManifest(
        key="plugin_future",
        name="未来插件",
        requires_core=">=2.0,<3.0",
    )

    with pytest.raises(ValueError, match="requires_core mismatch"):
        reg.validate([m])


def test_callback_data_exceeds_64_bytes_fails():
    """callback_data > 64 bytes fails startup (FR-TG-11, §3)."""
    oversized_data = "k=sign_in&a=" + "x" * 60  # total length > 64 bytes
    with pytest.raises(ValueError, match="callback_data exceeds Telegram 64-byte limit"):
        PluginManifest(
            key="sign_in",
            name="签到",
            callbacks=[oversized_data],
        )


def test_topological_sort_resolve():
    """Dependencies are resolved in correct topological order (FR-PLG-07)."""
    reg = PluginRegistry()
    m_base = PluginManifest(key="pkg_base", name="Base")
    m_mid = PluginManifest(key="pkg_mid", name="Mid", requires=["pkg_base"])
    m_top = PluginManifest(key="pkg_top", name="Top", requires=["pkg_mid"])

    # Provided in scrambled order
    resolved = reg.resolve([m_top, m_base, m_mid])
    keys = [m.key for m in resolved]
    assert keys == ["pkg_base", "pkg_mid", "pkg_top"]


@pytest.mark.asyncio
async def test_config_not_resurrected_on_reregister():
    """配置不复活：群内关闭插件后重跑 register 该群仍关闭 (FR-PLG-08, 验收 A3, §3)."""
    reg = PluginRegistry()
    manifest = PluginManifest(
        key="sample_plugin",
        name="示例插件",
        version="1.0.0",
        default_status=True,
        cmds=[Cmd(key="sample_cmd", pattern="sample", slash="sample")],
    )

    # 1. First registration
    await reg.register_manifest(manifest)

    # Verify initial DB state
    info = await PluginInfo.get(module="sample_plugin")
    assert info.status is True
    assert info.default_status is True

    # 2. Administrator disables the plugin in group '-100999' and globally
    await GroupPluginSwitch.create(group_id="-100999", plugin_key="sample_plugin", status=False)
    info.status = False
    await info.save()

    # 3. Simulate bot reboot / re-running register
    updated_manifest = PluginManifest(
        key="sample_plugin",
        name="示例插件-升级版",
        version="1.0.1",
        default_status=True,  # Default in code is still True!
        cmds=[Cmd(key="sample_cmd", pattern="sample", slash="sample")],
    )
    await reg.register_manifest(updated_manifest)

    # 4. Verify DB state is NOT overwritten (status must remain False)
    reloaded_info = await PluginInfo.get(module="sample_plugin")
    assert reloaded_info.status is False, "Global status was overwritten (resurrected)!"
    assert reloaded_info.name == "示例插件-升级版"
    assert reloaded_info.version == "1.0.1"

    # Verify group switch is still False
    group_sw = await GroupPluginSwitch.get(group_id="-100999", plugin_key="sample_plugin")
    assert group_sw.status is False, "Group switch was overwritten (resurrected)!"

    # 5. Pipeline execution in group '-100999' must be denied by GuardSwitch
    from zxtg.core.kernel.registry import registry as global_reg
    global_reg.register(updated_manifest)

    actor = Actor(id=1, full_name="User")
    chat = ChatRef(id="-100999", type="supergroup", title="Test Group")
    event = UnifiedEvent(actor=actor, chat=chat, text="/sample")
    ctx = CallContext(
        event=event,
        user=UserView(id="1"),
        group=GroupView(id="-100999", title="Test Group"),
    )

    verdict = await run_pipeline(ctx)
    assert bool(verdict) is False
    assert "插件已在群内关闭" in verdict.reason or "插件已全局关闭" in verdict.reason
