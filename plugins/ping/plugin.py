from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.registry import Cmd, PluginManifest

manifest = PluginManifest(
    key="ping",
    name="心跳测试",
    version="1.0.0",
    author="ZX-TG Team",
    description="心跳测试插件",
    usage="发送 ping 或 /ping 回复 pong",
    plugin_type=PluginType.NORMAL,
    cmds=[
        Cmd(
            key="ping",
            pattern="ping",
            slash="ping",
            aliases=["心跳"],
            help="测试机器人生存状态",
        )
    ],
)


async def handle_ping(ctx: CallContext) -> None:
    """Handle ping command and reply with pong."""
    await ctx.reply("pong")


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
