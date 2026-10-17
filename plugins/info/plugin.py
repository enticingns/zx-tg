from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.kernel.registry import registry
from zxtg.core.services.group_service import group_service
from zxtg.core.services.user_service import user_service

manifest = PluginManifest(
    key="info",
    name="信息查询",
    version="1.0.0",
    author="ZX-TG Team",
    description="查询用户信息、群聊信息与 Bot 状态",
    usage="个人信息 [用户ID]；群信息；运行状态",
    plugin_type=PluginType.NORMAL,
    menu_type="功能",
    level=0,
    cmds=[
        Cmd(
            key="user_info",
            pattern="个人信息",
            slash="me",
            aliases=["我的信息", "用户信息"],
            help="查询用户个人信息: 个人信息 [用户ID]",
        ),
        Cmd(
            key="group_info",
            pattern="群信息",
            slash="group",
            aliases=["本群信息"],
            help="查询当前群聊信息",
        ),
        Cmd(
            key="bot_status",
            pattern="运行状态",
            slash="status",
            aliases=["系统状态"],
            help="查询 Bot 运行状态与系统概况",
        ),
    ],
)


async def handle_user_info(ctx: CallContext) -> None:
    """Query user information with display name fallback (FR-BIP-05, FR-TG-08)."""
    args = ctx.event.command.args if ctx.event.command else []
    target_id = args[0] if args else str(ctx.user.id)

    user = await user_service.get_user(target_id)
    if user:
        display_name = user_service.get_display_name(user.username, user.full_name, user.user_id)
        level = user.level
        gold = user.gold
        impression = user.impression
    elif target_id == str(ctx.user.id):
        actor = ctx.event.actor
        display_name = user_service.get_display_name(actor.username, actor.full_name or "", target_id)
        level = ctx.user.level
        gold = ctx.user.gold
        impression = ctx.user.impression
    else:
        await ctx.reply(f"未找到用户 {target_id} 的信息")
        return

    msg = (
        f"👤 **用户信息**\n"
        f"- 昵称/用户名：{display_name}\n"
        f"- 用户ID：`{target_id}`\n"
        f"- 权限等级：{level}\n"
        f"- 金币余额：{gold}\n"
        f"- 好感度：{impression:.1f}"
    )
    await ctx.reply(msg)


async def handle_group_info(ctx: CallContext) -> None:
    """Query current group information (FR-BIP-05)."""
    if not ctx.group:
        await ctx.reply("该命令仅在群聊中可用。")
        return

    group = await group_service.get_group(ctx.group.id)
    title = group.group_name if group and group.group_name else ctx.group.title
    level = group.level if group else ctx.group.level
    members = group.member_count if group else 0
    status_str = "正常开启" if (group and group.status) else "正常开启"

    msg = (
        f"👥 **群聊信息**\n"
        f"- 群名称：{title or '未命名群组'}\n"
        f"- 群ID：`{ctx.group.id}`\n"
        f"- 群权限等级：{level}\n"
        f"- 群状态：{status_str}\n"
        f"- 成员数量：{members}"
    )
    await ctx.reply(msg)


async def handle_bot_status(ctx: CallContext) -> None:
    """Query bot runtime status and loaded plugins (FR-BIP-05)."""
    plugins = registry.list_plugins()
    msg = (
        f"🤖 **Bot 运行状态**\n"
        f"- 核心版本：{registry.core_version}\n"
        f"- 已装载插件数：{len(plugins)}\n"
        f"- 平台适配：Telegram\n"
        f"- 运行状态：正常运作中"
    )
    await ctx.reply(msg)


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
