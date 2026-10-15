import pytest

from zxtg.core.context import CallContext, UserView
from zxtg.core.event import Actor, UnifiedEvent
from zxtg.core.kernel.commands import CommandRegistry, command_registry, compute_effective_slash
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.kernel.registry import PluginRegistry as KernelPluginRegistry, registry


@pytest.fixture(autouse=True)
def clean_command_registry():
    command_registry.clear()
    registry.clear()
    yield
    command_registry.clear()
    registry.clear()


def test_slash_auto_naming():
    """Slash command auto-names to <plugin_key>_<action> when omitted (FR-CMD-05)."""
    # 1. Action without prefix -> prefixed with plugin_key
    cmd1 = Cmd(key="forecast", pattern="天气预报")
    assert compute_effective_slash("weather", cmd1) == "weather_forecast"

    # 2. Action already prefixed with plugin_key -> kept as is
    cmd2 = Cmd(key="weather_now", pattern="实时天气")
    assert compute_effective_slash("weather", cmd2) == "weather_now"

    # 3. Explicit slash provided -> used directly
    cmd3 = Cmd(key="lookup", pattern="查询", slash="find")
    assert compute_effective_slash("weather", cmd3) == "find"


@pytest.mark.asyncio
async def test_command_dual_track_normalization_and_dispatch():
    """Text track (pattern/aliases) and Slash track map to same CommandRef and handler (FR-CMD-01, §3)."""
    executed = []

    async def sample_handler(ctx: CallContext) -> None:
        executed.append(ctx.event.command.name if ctx.event.command else "")
        await ctx.reply(f"result:{ctx.event.command.name}")

    cmd = Cmd(
        key="sign_rank",
        pattern="签到排行",
        slash="sign_rank",
        aliases=["好感度排行"],
        help="查看签到榜",
    )
    manifest = PluginManifest(
        key="sign_in",
        name="签到",
        cmds=[cmd],
    )
    registry.register(manifest, {"sign_rank": sample_handler})

    actor = Actor(id=1, full_name="User")

    # 1. Text track with pattern "签到排行"
    executed.clear()
    ctx1 = CallContext(event=UnifiedEvent(actor=actor, text="签到排行"), user=UserView(id="1"))
    verdict1 = await run_pipeline(ctx1)
    assert bool(verdict1) is True
    assert executed == ["sign_rank"]
    assert ctx1.replies[0].content == "result:sign_rank"

    # 2. Text track with alias "好感度排行"
    executed.clear()
    ctx2 = CallContext(event=UnifiedEvent(actor=actor, text="好感度排行"), user=UserView(id="1"))
    verdict2 = await run_pipeline(ctx2)
    assert bool(verdict2) is True
    assert executed == ["sign_rank"]
    assert ctx2.replies[0].content == "result:sign_rank"

    # 3. Slash track with "/sign_rank"
    executed.clear()
    ctx3 = CallContext(event=UnifiedEvent(actor=actor, text="/sign_rank"), user=UserView(id="1"))
    verdict3 = await run_pipeline(ctx3)
    assert bool(verdict3) is True
    assert executed == ["sign_rank"]
    assert ctx3.replies[0].content == "result:sign_rank"

    # 4. Slash track with bot username "/sign_rank@my_telegram_bot"
    executed.clear()
    ctx4 = CallContext(event=UnifiedEvent(actor=actor, text="/sign_rank@my_telegram_bot"), user=UserView(id="1"))
    verdict4 = await run_pipeline(ctx4)
    assert bool(verdict4) is True
    assert executed == ["sign_rank"]
    assert ctx4.replies[0].content == "result:sign_rank"


@pytest.mark.asyncio
async def test_100_command_truncation_and_degraded_still_triggers():
    """120 commands: top 100 to TG, 101+ degraded to Text track but STILL TRIGGERABLE (验收 A4, §3)."""
    cr = CommandRegistry()
    reg = KernelPluginRegistry()

    invoked_commands = []

    async def universal_handler(ctx: CallContext) -> None:
        invoked_commands.append(ctx.event.command.name if ctx.event.command else "")
        await ctx.reply("executed")

    manifests = []
    # 1. Create 50 NORMAL commands (priority 1)
    for i in range(50):
        key = f"cmd_norm_{i}"
        cmd = Cmd(key=key, pattern=f"普通_{i}", slash=f"norm_{i}")
        m = PluginManifest(
            key=f"pkg_n_{i}",
            name=f"NormPkg_{i}",
            plugin_type=PluginType.NORMAL,
            cmds=[cmd],
        )
        manifests.append(m)

    # 2. Create 30 ADMIN commands (priority 2)
    for i in range(30):
        key = f"cmd_adm_{i}"
        cmd = Cmd(key=key, pattern=f"管理_{i}", slash=f"adm_{i}")
        m = PluginManifest(
            key=f"pkg_a_{i}",
            name=f"AdmPkg_{i}",
            plugin_type=PluginType.ADMIN,
            cmds=[cmd],
        )
        manifests.append(m)

    # 3. Create 30 SUPERUSER commands (priority 3)
    for i in range(30):
        key = f"cmd_su_{i}"
        cmd = Cmd(key=key, pattern=f"超管_{i}", slash=f"su_{i}")
        m = PluginManifest(
            key=f"pkg_s_{i}",
            name=f"SuPkg_{i}",
            plugin_type=PluginType.SUPERUSER,
            cmds=[cmd],
        )
        manifests.append(m)

    # 4. Create 10 HIDDEN commands (priority 5)
    for i in range(10):
        key = f"cmd_hid_{i}"
        cmd = Cmd(key=key, pattern=f"隐藏_{i}", slash=f"hid_{i}")
        m = PluginManifest(
            key=f"pkg_h_{i}",
            name=f"HidPkg_{i}",
            plugin_type=PluginType.HIDDEN,
            cmds=[cmd],
        )
        manifests.append(m)

    total_count = len(manifests)
    assert total_count == 120  # 50 + 30 + 30 + 10 = 120 commands

    # Register all manifests into CommandRegistry
    for m in manifests:
        cr.register_plugin_commands(m)
        reg.register(m, {m.cmds[0].key: universal_handler})

    # Recalculate 100-command truncation
    cr.recalculate_truncation()

    all_cmds = cr.all_commands
    assert len(all_cmds) == 120

    # Top 100 are registered to Telegram
    tg_cmds = [c for c in all_cmds if c.registered_to_telegram]
    degraded_cmds = [c for c in all_cmds if not c.registered_to_telegram]
    assert len(tg_cmds) == 100
    assert len(degraded_cmds) == 20

    # Verify degraded list matches cr.degraded_commands
    assert len(cr.degraded_commands) == 20

    # Verify priority ordering:
    # 50 NORMAL + 30 ADMIN = 80 commands
    # Next 20 are SUPERUSER commands (indices 80 to 99)
    # Remaining 10 SUPERUSER commands and 10 HIDDEN commands are degraded (total 20)
    for c in tg_cmds[:50]:
        assert c.manifest.plugin_type == PluginType.NORMAL
    for c in tg_cmds[50:80]:
        assert c.manifest.plugin_type == PluginType.ADMIN
    for c in tg_cmds[80:100]:
        assert c.manifest.plugin_type == PluginType.SUPERUSER

    # 101st command is at index 100 in sorted list (101st item)
    cmd_101 = all_cmds[100]
    assert cmd_101.registered_to_telegram is False
    assert cmd_101 in degraded_cmds

    # ---- CRITICAL TEST: 101st command is STILL TRIGGERABLE! ----
    # Trigger 101st command by its pattern via CommandRegistry matching
    matched = cr.match(cmd_101.cmd.pattern)
    assert matched is not None
    ref, reg_cmd = matched
    assert ref.name == cmd_101.cmd.key
    assert reg_cmd.cmd.key == cmd_101.cmd.key

    # Also test triggering via pipeline dispatch
    # Wire cr into global command_registry for run_pipeline test
    from zxtg.core.kernel.commands import command_registry as global_cr
    for m in manifests:
        global_cr.register_plugin_commands(m)
    global_cr.recalculate_truncation()

    from zxtg.core.kernel.registry import registry as global_reg
    for m in manifests:
        global_reg.register(m, {m.cmds[0].key: universal_handler})

    actor = Actor(id=1, full_name="User")
    from zxtg.core.event import Role
    event = UnifiedEvent(actor=actor, text=cmd_101.cmd.pattern, role=Role.OWNER)
    ctx = CallContext(event=event, user=UserView(id="1", level=100))

    invoked_commands.clear()
    verdict = await run_pipeline(ctx)
    assert bool(verdict) is True
    assert invoked_commands == [cmd_101.cmd.key]
    assert len(ctx.replies) == 1
    assert ctx.replies[0].content == "executed"


def test_scope_grouped_commands_calculation():
    """Commands are properly grouped into Telegram BotCommand scopes (FR-CMD-06)."""
    cr = CommandRegistry()

    m_norm = PluginManifest(
        key="pkg_norm",
        name="Norm",
        plugin_type=PluginType.NORMAL,
        cmds=[Cmd(key="cmd_n", slash="normal_cmd", help="Normal command")],
    )
    m_admin = PluginManifest(
        key="pkg_admin",
        name="Admin",
        plugin_type=PluginType.ADMIN,
        cmds=[Cmd(key="cmd_a", slash="admin_cmd", help="Admin command")],
    )
    m_su = PluginManifest(
        key="pkg_su",
        name="SU",
        plugin_type=PluginType.SUPERUSER,
        cmds=[Cmd(key="cmd_s", slash="su_cmd", help="Superuser command")],
    )

    cr.register_plugin_commands(m_norm)
    cr.register_plugin_commands(m_admin)
    cr.register_plugin_commands(m_su)
    cr.recalculate_truncation()

    groups = cr.get_scope_grouped_commands()
    assert "default" in groups
    assert "all_chat_administrators" in groups
    assert "superuser" in groups

    default_slashes = [e.command for e in groups["default"]]
    admin_slashes = [e.command for e in groups["all_chat_administrators"]]
    su_slashes = [e.command for e in groups["superuser"]]

    assert "normal_cmd" in default_slashes
    assert "admin_cmd" in admin_slashes
    assert "su_cmd" in su_slashes
