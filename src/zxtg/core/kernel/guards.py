import logging

from tortoise import Tortoise

from zxtg.core.context import CallContext, GroupView, PluginView, UserView
from zxtg.core.event import CommandRef
from zxtg.core.kernel.commands import command_registry
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.registry import registry
from zxtg.core.services.config_service import config_service
from zxtg.core.services.limit_service import limit_service
from zxtg.models.group_console import GroupConsole
from zxtg.models.logs import UserGoldLog, UserImpressionLog
from zxtg.models.plugin_info import PluginInfo
from zxtg.models.switch import GroupPluginSwitch
from zxtg.models.user_console import UserConsole

logger = logging.getLogger("zxtg.kernel.guards")


class Verdict:
    """Verdict returned by Guards and the Pipeline (ALLOW / DENY)."""

    def __init__(self, allowed: bool, reason: str = "", tip: str = "") -> None:
        self.allowed = allowed
        self.reason = reason
        self.tip = tip

    def __bool__(self) -> bool:
        return self.allowed

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Verdict):
            return (
                self.allowed == other.allowed
                and self.reason == other.reason
                and self.tip == other.tip
            )
        return False

    def __repr__(self) -> str:
        if self.allowed:
            return "Verdict(ALLOW)"
        return f"Verdict(DENY, reason={self.reason!r}, tip={self.tip!r})"


ALLOW = Verdict(True)


def DENY(reason: str = "", tip: str = "") -> Verdict:
    return Verdict(False, reason=reason, tip=tip)


async def ResolveContext(ctx: CallContext) -> Verdict:
    """Resolve actor / chat context from database if initialized."""
    if not Tortoise._inited:
        return ALLOW

    actor_id = str(ctx.event.actor.id)
    user_record = await UserConsole.get_or_none(user_id=actor_id)
    if user_record is None:
        user_record = await UserConsole.create(
            user_id=actor_id,
            username=ctx.event.actor.username,
            full_name=ctx.event.actor.full_name or "",
        )

    ctx._user = UserView(
        id=user_record.user_id,
        level=ctx.event.role.level,
        gold=user_record.gold,
        impression=user_record.impression,
    )

    if ctx.event.chat and ctx.event.chat.type in ("group", "supergroup"):
        group_id = str(ctx.event.chat.id)
        group_record = await GroupConsole.get_or_none(group_id=group_id)
        if group_record is None:
            group_record = await GroupConsole.create(
                group_id=group_id,
                group_name=ctx.event.chat.title or "",
            )
        ctx._group = GroupView(
            id=group_record.group_id,
            title=group_record.group_name,
            level=group_record.level,
        )

    return ALLOW


async def BuildCommand(ctx: CallContext) -> Verdict:
    """Dual-track command matching (text/slash) and plugin resolution."""
    if ctx.event.command is None and ctx.event.text:
        match_result = command_registry.match(ctx.event.text)
        if match_result:
            ref, reg_cmd = match_result
            ctx.event.command = ref
            ctx._plugin = PluginView(key=reg_cmd.manifest.key, name=reg_cmd.manifest.name)
        else:
            raw_text = ctx.event.text.strip()
            if raw_text:
                parts = raw_text.split()
                cmd_token = parts[0]
                cmd_name = cmd_token[1:] if cmd_token.startswith("/") else cmd_token
                if "@" in cmd_name:
                    cmd_name = cmd_name.split("@", 1)[0]
                args = parts[1:]
                ctx.event.command = CommandRef(name=cmd_name, args=args, raw=raw_text)

    # Attach plugin view if command matched a registered plugin
    if ctx.event.command and ctx.plugin is None:
        p = registry.get_plugin(ctx.event.command.name)
        if p:
            ctx._plugin = PluginView(key=p.key, name=p.name)

    return ALLOW


async def MergeConfig(ctx: CallContext) -> Verdict:
    """Merge 3-tier configurations into effective plugin config dictionary (FR-CFG-01)."""
    if ctx.plugin:
        group_id = ctx.group.id if ctx.group else None
        effective = config_service.get_plugin_effective_configs(ctx.plugin.key, group_id)
        # Merge with any existing config pre-populated on the plugin view
        merged = {**effective, **ctx.plugin.config}
        ctx._plugin = PluginView(key=ctx.plugin.key, name=ctx.plugin.name, config=merged)
    return ALLOW


async def GuardBan(ctx: CallContext) -> Verdict:
    """Check user/chat blacklist and ban status."""
    if Tortoise._inited and ctx.group:
        group_record = await GroupConsole.get_or_none(group_id=str(ctx.group.id))
        if group_record and not group_record.status:
            return DENY(reason="群聊已被禁用", tip="请联系机器人管理员")
    return ALLOW


async def GuardSwitch(ctx: CallContext) -> Verdict:
    """Check global and group plugin switches (FR-PLG-08)."""
    if not ctx.plugin:
        return ALLOW

    plugin_key = ctx.plugin.key
    manifest = registry.get_plugin(plugin_key)

    if Tortoise._inited:
        info = await PluginInfo.get_or_none(module=plugin_key)
        if info and not info.status:
            return DENY(reason="插件已全局关闭", tip=f"发送 /enable {plugin_key} 开启")

        if ctx.group:
            sw = await GroupPluginSwitch.get_or_none(group_id=str(ctx.group.id), plugin_key=plugin_key)
            if sw and not sw.status:
                return DENY(reason="插件已在群内关闭", tip=f"发送 /enable {plugin_key} 开启")
    elif manifest and not manifest.default_status:
        return DENY(reason="插件已全局关闭", tip=f"发送 /enable {plugin_key} 开启")

    return ALLOW


async def GuardLevel(ctx: CallContext) -> Verdict:
    """Check user permission level against manifest requirements."""
    if not ctx.plugin:
        return ALLOW

    manifest = registry.get_plugin(ctx.plugin.key)
    if not manifest:
        return ALLOW

    user_level = ctx.event.role.level
    if manifest.admin_level is not None and user_level < manifest.admin_level:
        return DENY(reason="管理员权限不足", tip=f"需要管理权限等级 {manifest.admin_level}")

    if manifest.plugin_type in (PluginType.ADMIN, PluginType.SUPERUSER):
        if user_level < manifest.level:
            return DENY(reason="权限不足", tip=f"需要权限等级 {manifest.level}")

    return ALLOW


async def GuardCost(ctx: CallContext) -> Verdict:
    """Check and atomically deduct economy cost (gold / impression)."""
    if not ctx.plugin:
        return ALLOW

    manifest = registry.get_plugin(ctx.plugin.key)
    if not manifest:
        return ALLOW

    if manifest.cost_gold > 0 and ctx.user.gold < manifest.cost_gold:
        return DENY(reason="金币不足", tip=f"本次调用需要 {manifest.cost_gold} 金币，当前拥有 {ctx.user.gold}")

    if manifest.impression > 0.0 and ctx.user.impression < manifest.impression:
        return DENY(
            reason="好感度不足",
            tip=f"本次调用需要 {manifest.impression:.1f} 好感度，当前拥有 {ctx.user.impression:.1f}",
        )

    # Atomic deduction in database
    if Tortoise._inited and (manifest.cost_gold > 0 or manifest.impression > 0.0):
        user_record = await UserConsole.get_or_none(user_id=str(ctx.user.id))
        if user_record:
            if manifest.cost_gold > 0:
                user_record.gold -= manifest.cost_gold
                await UserGoldLog.create(
                    user_id=str(ctx.user.id),
                    amount=-manifest.cost_gold,
                    reason=f"cost_{manifest.key}",
                )
            if manifest.impression > 0.0:
                user_record.impression -= manifest.impression
                await UserImpressionLog.create(
                    user_id=str(ctx.user.id),
                    amount=-manifest.impression,
                    reason=f"cost_{manifest.key}",
                )
            await user_record.save()
            ctx._user = UserView(
                id=ctx.user.id,
                level=ctx.user.level,
                gold=user_record.gold,
                impression=user_record.impression,
            )

    return ALLOW


async def GuardLimit(ctx: CallContext) -> Verdict:
    """Check CD, COUNT (with rolling period), and BLOCK limiters (FR-LIM-01~06)."""
    if not ctx.plugin:
        return ALLOW

    manifest = registry.get_plugin(ctx.plugin.key)
    if not manifest:
        return ALLOW

    is_group = bool(ctx.group or (ctx.event.chat and ctx.event.chat.type in ("group", "supergroup")))
    group_id = ctx.group.id if ctx.group else (ctx.event.chat.id if ctx.event.chat else None)
    is_superuser = ctx.event.role.level >= 100

    allowed, reason = limit_service.check_all_and_record(
        manifest=manifest,
        user_id=str(ctx.event.actor.id),
        group_id=str(group_id) if group_id else None,
        is_group=is_group,
        is_superuser=is_superuser,
    )

    if not allowed:
        return DENY(reason=reason, tip="请遵守插件频率限制")

    return ALLOW


async def Dispatch(ctx: CallContext) -> Verdict:
    """Dispatch command to registered handler."""
    cmd = ctx.event.command
    if not cmd:
        return DENY(reason="No command specified", tip="Send /ping to test")

    handler = registry.get_handler(cmd.name)
    if not handler:
        return DENY(reason=f"Unknown command: {cmd.name}", tip="Available command: /ping")

    await handler(ctx)
    return ALLOW
