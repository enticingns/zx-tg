import logging

from tortoise import Tortoise

from zxtg.core.context import CallContext, GroupView, PluginView, UserView
from zxtg.core.event import CommandRef
from zxtg.core.kernel.commands import command_registry
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.registry import registry
from zxtg.models.plugin_info import PluginInfo

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
        return (
            isinstance(other, Verdict)
            and self.allowed == other.allowed
            and self.reason == other.reason
            and self.tip == other.tip
        )

    def __repr__(self) -> str:
        if self.allowed:
            return "Verdict(ALLOW)"
        return f"Verdict(DENY, reason={self.reason!r}, tip={self.tip!r})"


ALLOW = Verdict(True)


def DENY(reason: str = "", tip: str = "") -> Verdict:
    return Verdict(False, reason=reason, tip=tip)


async def ResolveContext(ctx: CallContext) -> Verdict:
    """Resolve actor / chat context from user_service and group_service (FR-SVC-01, FR-SVC-04, FR-AUTH-11)."""
    if not Tortoise._inited:
        return ALLOW

    from zxtg.core.services.group_service import group_service
    from zxtg.core.services.permission_service import permission_service
    from zxtg.core.services.user_service import user_service

    actor_id = str(ctx.event.actor.id)
    user_record, _ = await user_service.get_or_create_user(
        user_id=actor_id,
        username=ctx.event.actor.username,
        full_name=ctx.event.actor.full_name or "",
    )

    group_record = None
    if ctx.event.chat and ctx.event.chat.type in ("group", "supergroup"):
        group_id = str(ctx.event.chat.id)
        group_record, _ = await group_service.get_or_create_group(
            chat_id=group_id,
            title=ctx.event.chat.title or "",
        )
        ctx._group = GroupView(
            id=group_record.group_id,
            title=group_record.group_name,
            level=group_record.level,
        )

    effective_level = permission_service.get_effective_level(
        role=ctx.event.role,
        group=group_record,
        user_level=user_record.level,
    )
    ctx._user = UserView(
        id=user_record.user_id,
        level=effective_level,
        gold=user_record.gold,
        impression=user_record.impression,
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
                ctx.event.command = CommandRef(name=cmd_name, args=parts[1:], raw=raw_text)

    if ctx.event.command and ctx.plugin is None:
        p = registry.get_plugin(ctx.event.command.name)
        if p:
            ctx._plugin = PluginView(key=p.key, name=p.name)
    return ALLOW


async def MergeConfig(ctx: CallContext) -> Verdict:
    """Merge 3-tier configurations into effective plugin config dictionary (FR-CFG-01)."""
    if ctx.plugin:
        from zxtg.core.services.config_service import config_service

        group_id = ctx.group.id if ctx.group else None
        effective = config_service.get_plugin_effective_configs(ctx.plugin.key, group_id)
        merged = {**effective, **ctx.plugin.config}
        ctx._plugin = PluginView(key=ctx.plugin.key, name=ctx.plugin.name, config=merged)
    return ALLOW


async def GuardBan(ctx: CallContext) -> Verdict:
    """Check user/chat blacklist and ban status."""
    if Tortoise._inited and ctx.group:
        from zxtg.core.services.group_service import group_service

        group_record = await group_service.get_group(ctx.group.id)
        if group_record and not group_record.status:
            return DENY(reason="群聊已被禁用", tip="请联系机器人管理员")
    return ALLOW


async def GuardSwitch(ctx: CallContext) -> Verdict:
    """Check global and group plugin switches (FR-PLG-08, FR-AUTH-08)."""
    if not ctx.plugin:
        return ALLOW

    plugin_key = ctx.plugin.key
    manifest = registry.get_plugin(plugin_key)
    if not manifest:
        return ALLOW

    # Superuser bypass check (FR-AUTH-08)
    if ctx.user.level >= 100 and not manifest.limit_superuser:
        return ALLOW

    is_globally_enabled = True
    if Tortoise._inited:
        info = await PluginInfo.get_or_none(module=plugin_key)
        is_globally_enabled = info.status if info is not None else manifest.default_status
    else:
        is_globally_enabled = manifest.default_status

    if not is_globally_enabled:
        return DENY(reason="插件已全局关闭", tip=f"发送 /enable {plugin_key} 开启")

    if Tortoise._inited and ctx.group:
        from zxtg.core.services.group_service import group_service

        sw = await group_service.get_plugin_switch(ctx.group.id, plugin_key)
        if sw is False:
            return DENY(reason="插件已在群内关闭", tip=f"发送 /enable {plugin_key} 开启")

    return ALLOW


async def GuardLevel(ctx: CallContext) -> Verdict:
    """Check user permission level against manifest requirements using permission_service (FR-AUTH-11)."""
    if not ctx.plugin:
        return ALLOW

    manifest = registry.get_plugin(ctx.plugin.key)
    if not manifest:
        return ALLOW

    from zxtg.core.services.permission_service import permission_service

    allowed, reason, tip = permission_service.can_execute_detailed(
        user=ctx.user, group=ctx.group, manifest=manifest, role=ctx.event.role
    )
    if not allowed:
        return DENY(reason=reason, tip=tip)
    return ALLOW


async def GuardCost(ctx: CallContext) -> Verdict:
    """Check economy cost (gold / impression) and register pending deduction (FR-AUTH-09)."""
    if not ctx.plugin:
        return ALLOW

    manifest = registry.get_plugin(ctx.plugin.key)
    if not manifest:
        return ALLOW

    if ctx.user.level >= 100 and not manifest.limit_superuser:
        return ALLOW

    if manifest.cost_gold > 0 and ctx.user.gold < manifest.cost_gold:
        return DENY(reason="金币不足", tip=f"本次调用需要 {manifest.cost_gold} 金币，当前拥有 {ctx.user.gold}")

    if manifest.impression > 0.0 and ctx.user.impression < manifest.impression:
        return DENY(
            reason="好感度不足",
            tip=f"本次调用需要 {manifest.impression:.1f} 好感度，当前拥有 {ctx.user.impression:.1f}",
        )

    # Attach pending deduction to context so Dispatch only deducts IF handler succeeds (FR-AUTH-09)
    if manifest.cost_gold > 0 or manifest.impression > 0.0:
        ctx._pending_cost = (manifest.cost_gold, manifest.impression, manifest.key)

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
    is_superuser = ctx.user.level >= 100 or ctx.event.role.level >= 100

    from zxtg.core.services.limit_service import limit_service

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
    """Dispatch command to registered handler and execute cost deduction on success (FR-AUTH-09)."""
    cmd = ctx.event.command
    if not cmd:
        return DENY(reason="No command specified", tip="Send /ping to test")

    handler = registry.get_handler(cmd.name)
    if not handler:
        return DENY(reason=f"Unknown command: {cmd.name}", tip="Available command: /ping")

    # Execute handler
    await handler(ctx)

    # If handler succeeds without exception, apply pending cost deduction (FR-AUTH-09)
    pending_cost = getattr(ctx, "_pending_cost", None)
    if pending_cost:
        if not Tortoise._inited:
            raise RuntimeError("扣费需要已初始化的数据库")
        cost_gold, cost_imp, plugin_key = pending_cost
        from zxtg.core.services.gold_service import gold_service
        from zxtg.core.services.impression_service import impression_service

        if cost_gold > 0:
            ok, msg = await gold_service.change_gold(ctx.user.id, -cost_gold, f"cost_{plugin_key}")
            if not ok:
                return DENY(reason=msg, tip="金币扣除失败")

        if cost_imp > 0.0:
            ok, msg = await impression_service.change_impression(ctx.user.id, -cost_imp, f"cost_{plugin_key}")
            if not ok:
                return DENY(reason=msg, tip="好感度扣除失败")

        current_gold = await gold_service.get_gold(ctx.user.id)
        current_imp = await impression_service.get_impression(ctx.user.id)
        ctx._user = UserView(
            id=ctx.user.id, level=ctx.user.level, gold=current_gold, impression=current_imp
        )

    if ctx.plugin:
        from zxtg.core.services.statistics_service import statistics_service

        group_id = ctx.group.id if ctx.group else None
        statistics_service.record_call(ctx.plugin.key, ctx.user.id, group_id)

    return ALLOW
