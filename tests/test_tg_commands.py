import pytest

from zxtg.core.kernel.commands import CommandRegistry, broadcast_commands
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.platform.tg.fake_client import FakeTelegramClient


@pytest.mark.asyncio
async def test_set_my_commands_scope_grouping_parameters():
    """Verify set_my_commands parameters are grouped by scope correctly (FR-CMD-02, FR-CMD-06)."""
    cr = CommandRegistry()

    m_norm = PluginManifest(
        key="norm_pkg",
        name="Normal Pkg",
        plugin_type=PluginType.NORMAL,
        cmds=[Cmd(key="help", slash="help", pattern="帮助", help="Show help")],
    )
    m_admin = PluginManifest(
        key="admin_pkg",
        name="Admin Pkg",
        plugin_type=PluginType.ADMIN,
        cmds=[Cmd(key="ban", slash="ban", pattern="封禁", help="Ban member")],
    )
    m_su = PluginManifest(
        key="su_pkg",
        name="Superuser Pkg",
        plugin_type=PluginType.SUPERUSER,
        cmds=[Cmd(key="reload", slash="reload", pattern="重载", help="Reload system")],
    )

    cr.register_plugin_commands(m_norm)
    cr.register_plugin_commands(m_admin)
    cr.register_plugin_commands(m_su)

    client = FakeTelegramClient()
    await broadcast_commands(client, registry=cr, superusers=[99999])

    # Check client calls
    calls = client.set_commands_calls
    scopes = [c["scope"]["type"] for c in calls]
    assert "all_group_chats" in scopes
    assert "all_chat_administrators" in scopes
    assert "all_private_chats" in scopes
    assert "chat" in scopes

    # Verify group scope contains normal commands
    group_call = next(c for c in calls if c["scope"]["type"] == "all_group_chats")
    group_cmds = [cmd["command"] for cmd in group_call["commands"]]
    assert "help" in group_cmds
    assert "ban" not in group_cmds
    assert "reload" not in group_cmds

    # Verify admin scope contains admin commands
    admin_call = next(c for c in calls if c["scope"]["type"] == "all_chat_administrators")
    admin_cmds = [cmd["command"] for cmd in admin_call["commands"]]
    assert "ban" in admin_cmds
    assert "reload" not in admin_cmds

    # Verify superuser scope contains superuser commands
    su_call = next(c for c in calls if c["scope"]["type"] == "chat")
    su_cmds = [cmd["command"] for cmd in su_call["commands"]]
    assert "reload" in su_cmds
    assert "help" in su_cmds


@pytest.mark.asyncio
async def test_100_command_truncation_not_in_scope_and_text_track_still_works():
    """Verify >100 commands are truncated from setMyCommands but work via Text track (FR-CMD-04)."""
    cr = CommandRegistry()

    # Create 50 NORMAL commands
    norm_cmds = [Cmd(key=f"n_{i}", slash=f"n_{i}", pattern=f"常规_{i}") for i in range(50)]
    cr.register_plugin_commands(PluginManifest(key="p_norm", name="Norm", plugin_type=PluginType.NORMAL, cmds=norm_cmds))

    # Create 30 ADMIN commands
    admin_cmds = [Cmd(key=f"a_{i}", slash=f"a_{i}", pattern=f"管理_{i}") for i in range(30)]
    cr.register_plugin_commands(PluginManifest(key="p_admin", name="Admin", plugin_type=PluginType.ADMIN, cmds=admin_cmds))

    # Create 30 SUPERUSER commands (priority 3)
    su_cmds = [Cmd(key=f"su_{i}", slash=f"su_{i}", pattern=f"超管_{i}") for i in range(30)]
    cr.register_plugin_commands(PluginManifest(key="p_su", name="SU", plugin_type=PluginType.SUPERUSER, cmds=su_cmds))

    # Create 10 HIDDEN commands (priority 5)
    hidden_cmds = [Cmd(key=f"h_{i}", slash=f"h_{i}", pattern=f"隐藏_{i}") for i in range(10)]
    cr.register_plugin_commands(PluginManifest(key="p_hid", name="Hid", plugin_type=PluginType.HIDDEN, cmds=hidden_cmds))

    # Total 50 + 30 + 30 + 10 = 120 commands
    cr.recalculate_truncation()

    assert len(cr.degraded_commands) == 20
    degraded_slashes = {rc.effective_slash for rc in cr.degraded_commands}

    # Degradation must be from lowest priority (HIDDEN: 10 commands, and last 10 SUPERUSER commands)
    for i in range(10):
        assert f"h_{i}" in degraded_slashes

    client = FakeTelegramClient()
    await broadcast_commands(client, registry=cr, superusers=[123])

    # Assert none of the degraded commands entered setMyCommands
    for call in client.set_commands_calls:
        for cmd_entry in call["commands"]:
            assert cmd_entry["command"] not in degraded_slashes, (
                f"Degraded command {cmd_entry['command']} must not be in setMyCommands!"
            )

    # Assert degraded commands STILL match on Text track! (Function not lost)
    match_result = cr.match("隐藏_0")
    assert match_result is not None
    ref, reg_cmd = match_result
    assert ref.name == "h_0"
    assert reg_cmd.effective_slash == "h_0"
    assert reg_cmd.registered_to_telegram is False
