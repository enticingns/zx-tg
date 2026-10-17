import logging
from typing import Any

from plugins.webui.server import webui_server
from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, ConfigSpec, PluginManifest
from zxtg.core.services.config_service import config_service

logger = logging.getLogger("zxtg.plugins.webui")

manifest = PluginManifest(
    key="webui",
    name="WebUI 管理后台",
    version="1.0.0",
    author="ZX-TG Team",
    description="WebUI 可选管理后台插件，提供插件开关、配置修改与群管理功能",
    usage="访问 WebUI 地址查看和操作管理面板",
    plugin_type=PluginType.NORMAL,
    menu_type="管理",
    level=100,
    configs=[
        ConfigSpec(
            key="WEBUI_ENABLED",
            type="bool",
            default=True,
            help="是否启用 WebUI 管理后台",
        ),
        ConfigSpec(
            key="WEBUI_HOST",
            type="str",
            default="127.0.0.1",
            help="WebUI 监听主机地址，改公网须显式配置",
        ),
        ConfigSpec(
            key="WEBUI_PORT",
            type="int",
            default=8080,
            help="WebUI 监听端口",
        ),
        ConfigSpec(
            key="WEBUI_TOKEN_TTL",
            type="int",
            default=3600,
            help="WebUI 令牌有效期（秒）",
        ),
        ConfigSpec(
            key="WEBUI_USERNAME",
            type="str",
            default="admin",
            help="WebUI 登录用户名",
        ),
        ConfigSpec(
            key="WEBUI_PASSWORD",
            type="str",
            default="admin",
            help="WebUI 登录密码",
        ),
    ],
    cmds=[
        Cmd(
            key="webui_status",
            pattern="webui状态",
            slash="webui",
            help="查看 WebUI 管理后台运行状态",
        ),
    ],
)


async def handle_webui_status(ctx: CallContext) -> None:
    """Check WebUI runtime status and listening address (FR-WEB-01)."""
    enabled = await ctx.config("WEBUI_ENABLED")
    if enabled is None:
        enabled = True
    host = await ctx.config("WEBUI_HOST") or "127.0.0.1"
    port = await ctx.config("WEBUI_PORT") or 8080
    is_running = bool(webui_server.task and not webui_server.task.done())

    msg = (
        f"🌐 **WebUI 管理后台状态**\n"
        f"- 启用配置: {'开启' if enabled else '关闭'}\n"
        f"- 运行状态: {'运行中' if is_running else '未运行'}\n"
        f"- 监听地址: `{host}:{port}`"
    )
    await ctx.reply(msg)


async def setup(ctx: Any = None) -> None:
    """Lifecycle startup hook to launch WebUI background server (FR-WEB-01, FR-WEB-07)."""
    enabled = config_service.get("WEBUI_ENABLED")
    if enabled is None:
        enabled = True
    if not enabled:
        logger.info("WebUI is disabled by configuration, skipping server launch")
        return

    host = str(config_service.get("WEBUI_HOST") or "127.0.0.1")
    port = int(config_service.get("WEBUI_PORT") or 8080)
    try:
        await webui_server.start(host=host, port=port)
        logger.info("WebUI server started on %s:%d", host, port)
    except Exception as exc:
        logger.warning("Failed to start WebUI server on %s:%d: %s", host, port, exc)


async def shutdown(ctx: Any = None) -> None:
    """Lifecycle shutdown hook ensuring zero leftover background tasks (FR-WEB-07)."""
    await webui_server.stop()
    logger.info("WebUI server stopped cleanly")
