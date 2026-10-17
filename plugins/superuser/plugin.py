from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.services.db import check_db_integrity
from zxtg.core.services.group_service import group_service
from zxtg.core.services.item_service import item_service
from zxtg.core.services.statistics_service import statistics_service

manifest = PluginManifest(
    key="superuser",
    name="超级用户",
    version="1.0.0",
    author="ZX-TG Team",
    description="全局与群级插件开关、广播、退群与数据维护",
    usage="插件开关 <开启|关闭> <全局|本群> <插件名>；广播 <内容>；退出本群；数据维护",
    plugin_type=PluginType.SUPERUSER,
    menu_type="超级管理",
    level=100,
    limit_superuser=False,
    cmds=[
        Cmd(
            key="su_switch",
            pattern="插件开关",
            slash="switch",
            aliases=["开关"],
            help="管理插件开关: 插件开关 <开启|关闭> <全局|本群> <插件名>",
        ),
        Cmd(
            key="su_broadcast",
            pattern="广播",
            slash="broadcast",
            aliases=["全员广播"],
            help="向所有活跃群发送广播: 广播 <内容>",
        ),
        Cmd(
            key="su_leave",
            pattern="退出本群",
            slash="leave",
            aliases=["退群"],
            help="让机器人退出当前群聊",
        ),
        Cmd(
            key="su_maintenance",
            pattern="数据维护",
            slash="maintenance",
            aliases=["数据检查"],
            help="系统数据维护与健康检查",
        ),
    ],
)


async def handle_su_switch(ctx: CallContext) -> None:
    """Manage global and group-level plugin switches (FR-BIP-06, FR-AUTH-07)."""
    args = ctx.event.command.args if ctx.event.command else []
    if len(args) < 3:
        await ctx.reply("格式错误，请使用：插件开关 <开启|关闭> <全局|本群> <插件名>")
        return

    action = args[0]
    scope = args[1]
    plugin_key = args[2].lower().strip()

    if action not in ("开启", "关闭"):
        await ctx.reply("操作动作必须为 '开启' 或 '关闭'")
        return

    target_status = action == "开启"

    if scope == "全局":
        ok = await group_service.set_global_plugin_switch(plugin_key, target_status)
        if not ok:
            await ctx.reply(f"设置全局开关失败：插件 '{plugin_key}' 不存在")
            return
        await ctx.reply(f"已将插件 '{plugin_key}' 的全局开关设置为: {'开启' if target_status else '关闭'}")
    elif scope == "本群":
        if not ctx.group:
            await ctx.reply("本群开关只能在群聊中使用")
            return
        await group_service.set_plugin_switch(ctx.group.id, plugin_key, target_status)
        await ctx.reply(f"已将插件 '{plugin_key}' 在本群的开关设置为: {'开启' if target_status else '关闭'}")
    else:
        await ctx.reply("范围必须为 '全局' 或 '本群'")


async def handle_su_broadcast(ctx: CallContext) -> None:
    """Broadcast messages to all active groups with resilient failure aggregation (FR-BIP-06)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请输入广播内容，例如：广播 系统升级维护通知")
        return

    content = " ".join(args)
    targets = await group_service.get_active_group_ids()
    if not targets:
        await ctx.reply("当前无活跃群聊目标可广播")
        return

    success_count = 0
    failures: list[dict[str, Any]] = []

    for target in targets:
        try:
            ok = await ctx.send_to(target, f"📢 【系统广播】\n{content}")
            if ok:
                success_count += 1
            else:
                failures.append({"target": target, "error": "平台发送失败或被拒绝"})
        except Exception as exc:
            failures.append({"target": target, "error": str(exc)})

    summary = f"📢 **广播发送完成**\n- 成功发送：{success_count} 个群\n- 发送失败：{len(failures)} 个群"
    if failures:
        details = "\n".join(f"- 目标群 {f['target']}: {f['error']}" for f in failures)
        summary += f"\n\n**失败详情：**\n{details}"

    await ctx.reply(summary)


async def handle_su_leave(ctx: CallContext) -> None:
    """Leave current group (FR-BIP-06)."""
    if not ctx.group:
        await ctx.reply("该命令只能在群聊中使用")
        return

    ok = await ctx.leave()
    if not ok:
        await ctx.reply("退群失败：Bot 缺少权限或平台操作失败")
        return

    await ctx.reply("收到退群指令，正在退出本群...")


async def handle_su_maintenance(ctx: CallContext) -> None:
    """Perform database check, item cleanup, and stat flushing (FR-BIP-06)."""
    healthy, diag = await check_db_integrity()
    cleaned = await item_service.clean_expired_items()
    flushed = await statistics_service.flush()
    status_text = "正常" if healthy else "异常"

    msg = (
        f"🔧 **系统数据维护报告**\n"
        f"- 数据库完整性检查：{status_text} ({diag})\n"
        f"- 清理过期道具数：{cleaned}\n"
        f"- 刷新调用统计记录数：{flushed}"
    )
    await ctx.reply(msg)


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
