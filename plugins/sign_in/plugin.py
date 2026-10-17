import random
from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, ConfigSpec, PluginManifest
from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.impression_service import impression_service

manifest = PluginManifest(
    key="sign_in",
    name="每日签到",
    version="1.0.0",
    author="ZX-TG Team",
    description="每日签到获取金币与好感度，支持群内与全局好感度排行榜",
    usage="发送 签到 或 /sign 每日签到；发送 好感度排行 [群|全局] 查看排行榜",
    plugin_type=PluginType.NORMAL,
    menu_type="功能",
    level=0,
    configs=[
        ConfigSpec(
            key="SIGN_GOLD_MIN",
            type="int",
            default=10,
            help="签到最小金币奖励",
        ),
        ConfigSpec(
            key="SIGN_GOLD_MAX",
            type="int",
            default=30,
            help="签到最大金币奖励",
        ),
        ConfigSpec(
            key="SIGN_IMPRESSION",
            type="float",
            default=1.0,
            help="签到好感度奖励",
        ),
    ],
    cmds=[
        Cmd(
            key="sign_in",
            pattern="签到",
            slash="sign",
            aliases=["打卡"],
            help="每日签到获取金币与好感度",
        ),
        Cmd(
            key="sign_rank",
            pattern="好感度排行",
            slash="rank",
            aliases=["好感排行"],
            help="查看好感度排行榜: 好感度排行 [群|全局]",
        ),
    ],
)


async def handle_sign_in(ctx: CallContext) -> None:
    """Handle daily sign in with idempotency and atomic rewards (FR-BIP-02)."""
    dao = await ctx.db()
    # 1. Idempotency check: reject repeat sign-in on same day
    has_signed = await dao.has_signed_in_today(ctx.user.id)
    if has_signed:
        await ctx.reply("您今天已经签到过了，请明天再来吧！")
        return

    # 2. Compute rewards from configuration
    min_gold = await ctx.config("SIGN_GOLD_MIN") or 10
    max_gold = await ctx.config("SIGN_GOLD_MAX") or 30
    imp_reward = float(await ctx.config("SIGN_IMPRESSION") or 1.0)
    gold_reward = random.randint(min_gold, max_gold) if max_gold > min_gold else min_gold

    # 3. Apply rewards via services
    gid = ctx.group.id if ctx.group else ""
    reason = f"sign_in:{gid}" if gid else "sign_in"
    await gold_service.change_gold(ctx.user.id, gold_reward, reason=reason)
    await impression_service.change_impression(ctx.user.id, imp_reward, reason=reason)
    await dao.record_stat(ctx.user.id, gid or None)

    current_gold = await gold_service.get_gold(ctx.user.id)
    current_imp = await impression_service.get_impression(ctx.user.id)

    # 4. Render output via ctx.render (FR-RND-01)
    res = await ctx.render(
        "sign_in",
        {
            "gold_reward": gold_reward,
            "current_gold": current_gold,
            "imp_reward": imp_reward,
            "current_imp": current_imp,
            "user_id": ctx.user.id,
        },
    )
    if res.is_image:
        await ctx.reply(res.content)
    else:
        msg = f"💡 {res.notice}\n\n{res.content}" if res.notice else str(res.content)
        await ctx.reply(msg)


async def handle_sign_rank(ctx: CallContext) -> None:
    """Handle impression leaderboard (group/global) (FR-BIP-02, FR-RND-01)."""
    dao = await ctx.db()
    args = ctx.event.command.args if ctx.event.command else []
    scope_arg = args[0] if args else ""

    if "全局" in scope_arg:
        target_group = None
        title = "全局好感度排行榜"
    elif ctx.group:
        target_group = ctx.group.id
        title = f"【{ctx.group.title or '本群'}】好感度排行榜"
    else:
        target_group = None
        title = "全局好感度排行榜"

    ranking = await dao.get_impression_ranking(limit=10, group_id=target_group)
    if not ranking:
        await ctx.reply("暂无好感度排行数据。")
        return

    res = await ctx.render(
        "sign_rank",
        {
            "title": title,
            "ranking": ranking,
        },
    )
    if res.is_image:
        await ctx.reply(res.content)
    else:
        msg = f"💡 {res.notice}\n\n{res.content}" if res.notice else str(res.content)
        await ctx.reply(msg)


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
