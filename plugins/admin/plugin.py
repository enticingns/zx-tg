from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest
from zxtg.core.services.user_service import user_service

manifest = PluginManifest(
    key="admin",
    name="群管理",
    version="1.0.0",
    author="ZX-TG Team",
    description="群成员禁言、解禁、踢出、封禁、解封及管理员设置",
    usage="禁言 <用户ID> [秒数]；解禁 <用户ID>；踢出 <用户ID>；封禁 <用户ID>；解封 <用户ID>；设置管理 <用户ID>；撤销管理 <用户ID>",
    plugin_type=PluginType.ADMIN,
    menu_type="管理",
    level=10,
    admin_level=10,
    cmds=[
        Cmd(
            key="admin_mute",
            pattern="禁言",
            slash="mute",
            aliases=["闭嘴"],
            help="禁言用户: 禁言 <用户ID> [秒数]",
        ),
        Cmd(
            key="admin_unmute",
            pattern="解禁",
            slash="unmute",
            aliases=["解禁言"],
            help="解禁用户: 解禁 <用户ID>",
        ),
        Cmd(
            key="admin_kick",
            pattern="踢出",
            slash="kick",
            aliases=["移出群聊"],
            help="踢出群成员: 踢出 <用户ID>",
        ),
        Cmd(
            key="admin_ban",
            pattern="封禁",
            slash="ban",
            aliases=["拉黑"],
            help="封禁用户: 封禁 <用户ID>",
        ),
        Cmd(
            key="admin_unban",
            pattern="解封",
            slash="unban",
            aliases=["解封禁"],
            help="解封用户: 解封 <用户ID>",
        ),
        Cmd(
            key="admin_set",
            pattern="设置管理",
            slash="set_admin",
            aliases=["升管"],
            help="设置管理员: 设置管理 <用户ID>",
        ),
        Cmd(
            key="admin_revoke",
            pattern="撤销管理",
            slash="revoke_admin",
            aliases=["降管"],
            help="撤销管理员: 撤销管理 <用户ID>",
        ),
    ],
)


async def handle_admin_mute(ctx: CallContext) -> None:
    """Mute a user with explicit failure feedback on platform rejection (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：禁言 123456 300")
        return

    target_id = args[0]
    duration = 300
    if len(args) > 1:
        try:
            duration = int(args[1])
        except ValueError:
            await ctx.reply("禁言时长必须为整数秒")
            return

    ok = await ctx.mute(target_id, duration)
    if not ok:
        await ctx.reply("禁言失败：Bot权限不足或目标用户无法被禁言")
        return

    await ctx.reply(f"已成功禁言用户 {target_id}，时长 {duration} 秒。")




async def handle_admin_unmute(ctx: CallContext) -> None:
    """Unmute a user with explicit failure feedback on platform rejection (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：解禁 123456")
        return

    target_id = args[0]
    ok = await ctx.unmute(target_id)
    if not ok:
        await ctx.reply("解禁失败：Bot权限不足或目标用户未被禁言")
        return

    await ctx.reply(f"已成功解除用户 {target_id} 的禁言。")


async def handle_admin_kick(ctx: CallContext) -> None:
    """Kick a user from group with explicit failure feedback (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：踢出 123456")
        return

    target_id = args[0]
    ok = await ctx.kick(target_id)
    if not ok:
        await ctx.reply("踢出失败：Bot权限不足或目标用户为群主/管理员")
        return

    await ctx.reply(f"已成功将用户 {target_id} 移出群聊。")


async def handle_admin_ban(ctx: CallContext) -> None:
    """Ban a user from group with explicit failure feedback (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：封禁 123456")
        return

    target_id = args[0]
    ok = await ctx.ban(target_id)
    if not ok:
        await ctx.reply("封禁失败：Bot权限不足或目标用户为群主/管理员")
        return

    await ctx.reply(f"已成功将用户 {target_id} 封禁。")


async def handle_admin_unban(ctx: CallContext) -> None:
    """Unban a user from group with explicit failure feedback (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：解封 123456")
        return

    target_id = args[0]
    ok = await ctx.unban(target_id)
    if not ok:
        await ctx.reply("解封失败：Bot权限不足或目标用户未被封禁")
        return

    await ctx.reply(f"已成功解除用户 {target_id} 的封禁。")


async def handle_admin_set(ctx: CallContext) -> None:
    """Promote user to administrator (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：设置管理 123456")
        return

    target_id = args[0]
    await user_service.set_level(target_id, 10)
    await ctx.reply(f"管理员变更通知：已将用户 {target_id} 设置为群管理员（权限等级 10）。")


async def handle_admin_revoke(ctx: CallContext) -> None:
    """Revoke administrator permissions from user (FR-BIP-04)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定目标用户ID，例如：撤销管理 123456")
        return

    target_id = args[0]
    await user_service.set_level(target_id, 0)
    await ctx.reply(f"管理员变更通知：已撤销用户 {target_id} 的群管理员权限（权限等级 0）。")


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
