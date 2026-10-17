from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.commands import compute_effective_slash
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.kernel.registry import registry
from zxtg.core.services.permission_service import permission_service

manifest = PluginManifest(
    key="help",
    name="帮助菜单",
    version="1.0.0",
    author="ZX-TG Team",
    description="按分类展示可用功能列表与单插件详情",
    usage="发送 帮助 或 /help 查看功能菜单；发送 帮助 <插件名> 查看详情",
    plugin_type=PluginType.NORMAL,
    menu_type="基础",
    level=0,
    cmds=[
        Cmd(
            key="help",
            pattern="帮助",
            slash="help",
            aliases=["菜单"],
            help="查看帮助菜单与单插件详情",
        )
    ],
)


async def handle_help(ctx: CallContext) -> None:
    """Handle help menu display and single plugin details with permission filtering (FR-BIP-01)."""
    # 1. Single plugin detail query
    if ctx.event.command and ctx.event.command.args:
        target = ctx.event.command.args[0].lower().strip()
        all_plugins = registry.list_plugins()
        matched = None
        for p in all_plugins:
            if p.key.lower() == target or p.name.lower() == target:
                matched = p
                break
            for c in p.cmds:
                if c.key.lower() == target or c.pattern.lower() == target or (c.slash and c.slash.lower() == target):
                    matched = p
                    break
            if matched:
                break

        if not matched:
            await ctx.reply(f"未找到插件或功能：{target}")
            return

        # Permission check: must not expose plugins user cannot execute
        allowed = permission_service.can_execute(
            user=ctx.user, group=ctx.group, manifest=matched, role=ctx.event.role
        )
        if not allowed:
            await ctx.reply("权限不足，无法查看该插件详情。")
            return

        lines = [
            f"📖 **插件详情：{matched.name}** (`{matched.key}`)",
            f"- 描述：{matched.description or '无描述'}",
            f"- 用法：{matched.usage or '无用法说明'}",
            f"- 分类：{matched.menu_type}",
            f"- 所需权限：{matched.level}（类型：{matched.plugin_type.value}）",
        ]
        if matched.cost_gold > 0:
            lines.append(f"- 消耗金币：{matched.cost_gold}")
        if matched.impression > 0.0:
            lines.append(f"- 消耗好感度：{matched.impression:.1f}")
        if matched.cmds:
            lines.append("\n**命令列表：**")
            for c in matched.cmds:
                slash_str = compute_effective_slash(matched.key, c)
                pat_str = f" `{c.pattern}`" if c.pattern else ""
                lines.append(f"• /{slash_str}{pat_str} - {c.help or '无说明'}")
        await ctx.reply("\n".join(lines))
        return

    # 2. Categorized menu display with permission filtering
    all_plugins = registry.list_plugins()
    menu_groups: dict[str, list[PluginManifest]] = {}
    for p in all_plugins:
        if not p.is_show:
            continue
        if not permission_service.can_execute(
            user=ctx.user, group=ctx.group, manifest=p, role=ctx.event.role
        ):
            continue
        m_type = p.menu_type or "功能"
        menu_groups.setdefault(m_type, []).append(p)

    if not menu_groups:
        await ctx.reply("当前暂无可用的功能。")
        return

    lines = ["📖 **真寻 Telegram 帮助菜单**\n"]
    for m_type in sorted(menu_groups.keys()):
        lines.append(f"【{m_type}】")
        for p in menu_groups[m_type]:
            cmd_hint = ""
            if p.cmds:
                first_cmd = p.cmds[0]
                slash_str = compute_effective_slash(p.key, first_cmd)
                if first_cmd.pattern:
                    cmd_hint = f"（发送 `{first_cmd.pattern}` 或 `/{slash_str}`）"
                else:
                    cmd_hint = f"（发送 `/{slash_str}`）"
            lines.append(f"• {p.name} (`{p.key}`) {cmd_hint}")
        lines.append("")

    lines.append("💡 发送 `帮助 <插件名>` 可查看单插件详细用法。")
    await ctx.reply("\n".join(lines))


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
