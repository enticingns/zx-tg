from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from zxtg.core.kernel.enums import PluginType

HandlerFunc = Callable[..., Coroutine[Any, Any, Any]]


@dataclass(frozen=True)
class Cmd:
    """Command declaration."""

    key: str
    pattern: str = ""
    slash: str | None = None
    aliases: list[str] = field(default_factory=list)
    help: str = ""


@dataclass(frozen=True)
class PluginManifest:
    """Plugin manifest specification (Design §5.3)."""

    key: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    usage: str = ""
    plugin_type: PluginType = PluginType.NORMAL
    cmds: list[Cmd] = field(default_factory=list)
    default_status: bool = True
    level: int = 5
    cost_gold: int = 0
    impression: float = 0.0


class PluginRegistry:
    """Plugin registry skeleton (M0 minimum implementation)."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._handlers: dict[str, HandlerFunc] = {}

    def register(
        self,
        manifest: PluginManifest,
        handlers: dict[str, HandlerFunc] | None = None,
    ) -> None:
        self._plugins[manifest.key] = manifest
        if handlers:
            for cmd_name, handler in handlers.items():
                self._handlers[cmd_name.lower()] = handler
                for cmd in manifest.cmds:
                    if cmd.key.lower() == cmd_name.lower() or (
                        cmd.slash and cmd.slash.lower() == cmd_name.lower()
                    ):
                        if cmd.pattern:
                            self._handlers[cmd.pattern.lower()] = handler
                        if cmd.slash:
                            self._handlers[cmd.slash.lower()] = handler
                        for alias in cmd.aliases:
                            self._handlers[alias.lower()] = handler

    def register_handler(self, command_name: str, handler: HandlerFunc) -> None:
        self._handlers[command_name.lower()] = handler

    def get_handler(self, command_name: str) -> HandlerFunc | None:
        return self._handlers.get(command_name.lower())

    def get_plugin(self, key: str) -> PluginManifest | None:
        return self._plugins.get(key)

    def list_plugins(self) -> list[PluginManifest]:
        return list(self._plugins.values())


registry = PluginRegistry()
