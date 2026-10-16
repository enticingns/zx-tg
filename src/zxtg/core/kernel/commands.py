from dataclasses import dataclass, field
import logging
import re
from typing import Any

from zxtg.core.event import CommandRef
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, PluginManifest

logger = logging.getLogger("zxtg.kernel.commands")

TG_SLASH_REGEX = re.compile(r"^[a-z0-9_]{1,32}$")

PLUGIN_TYPE_PRIORITY = {
    PluginType.NORMAL: 1,
    PluginType.ADMIN: 2,
    PluginType.SUPER_AND_ADMIN: 2,
    PluginType.SUPERUSER: 3,
    PluginType.DEPENDANT: 4,
    PluginType.HIDDEN: 5,
    PluginType.PARENT: 6,
}


@dataclass(frozen=True)
class RegisteredCommand:
    """Internal normalized representation of a registered command."""

    plugin_key: str
    cmd: Cmd
    manifest: PluginManifest
    effective_slash: str
    registered_to_telegram: bool = True


@dataclass(frozen=True)
class BotCommandEntry:
    """Structure mirroring Telegram BotCommand ready for setMyCommands."""

    command: str
    description: str


def compute_effective_slash(plugin_key: str, cmd: Cmd) -> str:
    """Compute effective slash command according to naming conventions (FR-CMD-05)."""
    if cmd.slash:
        slash = cmd.slash.lower().lstrip("/")
    else:
        # Auto-name <plugin_key>_<action>
        if cmd.key.startswith(f"{plugin_key}_"):
            slash = cmd.key.lower()
        else:
            slash = f"{plugin_key}_{cmd.key}".lower()
    return slash


def validate_slash_syntax(slash: str) -> None:
    """Validate slash command syntax conforms to Telegram Bot API rules (FR-CMD-03)."""
    if not TG_SLASH_REGEX.match(slash):
        raise ValueError(
            f"Slash command '{slash}' violates Telegram syntax ^[a-z0-9_]{{1,32}}$"
        )


class CommandRegistry:
    """Command registry implementing dual-track normalization and 100-command truncation (FR-CMD-01~06)."""

    def __init__(self) -> None:
        self._commands: list[RegisteredCommand] = []
        self._by_key: dict[str, RegisteredCommand] = {}
        self._by_slash: dict[str, RegisteredCommand] = {}
        self._by_pattern: dict[str, RegisteredCommand] = {}
        self._by_alias: dict[str, RegisteredCommand] = {}
        self._degraded_commands: list[RegisteredCommand] = []

    def register_plugin_commands(self, manifest: PluginManifest) -> None:
        """Register all commands declared in a plugin manifest."""
        for cmd in manifest.cmds:
            effective_slash = compute_effective_slash(manifest.key, cmd)
            validate_slash_syntax(effective_slash)

            reg_cmd = RegisteredCommand(
                plugin_key=manifest.key,
                cmd=cmd,
                manifest=manifest,
                effective_slash=effective_slash,
                registered_to_telegram=True,
            )
            self._commands.append(reg_cmd)
            self._by_key[cmd.key.lower()] = reg_cmd
            self._by_slash[effective_slash] = reg_cmd
            if cmd.pattern:
                self._by_pattern[cmd.pattern.lower()] = reg_cmd
            for alias in cmd.aliases:
                self._by_alias[alias.lower()] = reg_cmd

    def recalculate_truncation(self) -> None:
        """Sort commands by PluginType priority and apply 100-command truncation (FR-CMD-04)."""
        # Sort key: priority asc, then stable order
        sorted_cmds = sorted(
            self._commands,
            key=lambda rc: PLUGIN_TYPE_PRIORITY.get(rc.manifest.plugin_type, 99),
        )

        self._degraded_commands.clear()
        updated_commands: list[RegisteredCommand] = []

        for idx, rc in enumerate(sorted_cmds):
            if idx < 100:
                updated_commands.append(
                    RegisteredCommand(
                        plugin_key=rc.plugin_key,
                        cmd=rc.cmd,
                        manifest=rc.manifest,
                        effective_slash=rc.effective_slash,
                        registered_to_telegram=True,
                    )
                )
            else:
                degraded = RegisteredCommand(
                    plugin_key=rc.plugin_key,
                    cmd=rc.cmd,
                    manifest=rc.manifest,
                    effective_slash=rc.effective_slash,
                    registered_to_telegram=False,
                )
                updated_commands.append(degraded)
                self._degraded_commands.append(degraded)

        self._commands = updated_commands
        self._by_key.clear()
        self._by_slash.clear()
        self._by_pattern.clear()
        self._by_alias.clear()
        for rc in self._commands:
            self._by_key[rc.cmd.key.lower()] = rc
            self._by_slash[rc.effective_slash] = rc
            if rc.cmd.pattern:
                self._by_pattern[rc.cmd.pattern.lower()] = rc
            for alias in rc.cmd.aliases:
                self._by_alias[alias.lower()] = rc

        if self._degraded_commands:
            names = [f"/{rc.effective_slash}({rc.cmd.key})" for rc in self._degraded_commands]
            logger.warning(
                "Commands exceeded 100-command limit. Degraded %d commands to Text-track: %s",
                len(self._degraded_commands),
                ", ".join(names),
            )

    def match(self, raw_text: str) -> tuple[CommandRef, RegisteredCommand] | None:
        """Dual-track matching: matches either text track or slash track (FR-CMD-01)."""
        text = raw_text.strip()
        if not text:
            return None

        # 1. Slash track match (/slash_command [args])
        if text.startswith("/"):
            parts = text[1:].split()
            if not parts:
                return None
            cmd_token = parts[0]
            # Strip bot username, e.g. /ping@my_bot -> ping
            if "@" in cmd_token:
                cmd_token = cmd_token.split("@", 1)[0]
            slash_candidate = cmd_token.lower()
            args = parts[1:]

            reg_cmd = self._by_slash.get(slash_candidate)
            if not reg_cmd:
                # Also check by command key directly
                reg_cmd = self._by_key.get(slash_candidate)
            if reg_cmd:
                ref = CommandRef(name=reg_cmd.cmd.key, args=args, raw=text)
                return ref, reg_cmd

        # 2. Text track match (pattern or alias prefix matching)
        for pattern, reg_cmd in self._by_pattern.items():
            if text.lower() == pattern or text.lower().startswith(pattern + " "):
                args_text = text[len(pattern):].strip()
                args = args_text.split() if args_text else []
                ref = CommandRef(name=reg_cmd.cmd.key, args=args, raw=text)
                return ref, reg_cmd

        for alias, reg_cmd in self._by_alias.items():
            if text.lower() == alias or text.lower().startswith(alias + " "):
                args_text = text[len(alias):].strip()
                args = args_text.split() if args_text else []
                ref = CommandRef(name=reg_cmd.cmd.key, args=args, raw=text)
                return ref, reg_cmd

        # Fallback word check (e.g. text == "ping")
        first_word = text.split()[0].lower()
        if first_word in self._by_key:
            reg_cmd = self._by_key[first_word]
            args = text.split()[1:]
            return CommandRef(name=reg_cmd.cmd.key, args=args, raw=text), reg_cmd

        return None

    def get_scope_grouped_commands(self) -> dict[str, list[BotCommandEntry]]:
        """Calculate scope grouping for setMyCommands for top 100 non-degraded commands (FR-CMD-06)."""
        grouped: dict[str, list[BotCommandEntry]] = {
            "default": [],
            "all_chat_administrators": [],
            "superuser": [],
        }

        for rc in self._commands:
            if not rc.registered_to_telegram:
                continue

            desc = rc.cmd.help or rc.manifest.description or rc.cmd.key
            # Telegram description limit 3-256 chars
            if len(desc) < 3:
                desc = f"{desc} command"
            desc = desc[:256]

            entry = BotCommandEntry(command=rc.effective_slash, description=desc)

            scope_type = rc.cmd.scope or rc.manifest.plugin_type
            if scope_type in (PluginType.ADMIN, PluginType.SUPER_AND_ADMIN):
                grouped["all_chat_administrators"].append(entry)
            elif scope_type == PluginType.SUPERUSER:
                grouped["superuser"].append(entry)
            else:
                grouped["default"].append(entry)

        return grouped

    async def broadcast_commands(
        self,
        client: Any,
        superusers: list[int | str] | None = None,
        chat_members: list[tuple[int | str, int | str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Broadcast scope-grouped commands to Telegram setMyCommands (FR-CMD-02, FR-CMD-04, FR-CMD-06)."""
        self.recalculate_truncation()
        grouped = self.get_scope_grouped_commands()
        calls: list[dict[str, Any]] = []

        # 1. all_group_chats scope
        group_cmds = [{"command": e.command, "description": e.description} for e in grouped["default"]]
        scope_group = {"type": "all_group_chats"}
        await client.set_my_commands(commands=group_cmds, scope=scope_group)
        calls.append({"scope": scope_group, "commands": group_cmds})

        # 2. all_chat_administrators scope
        admin_cmds = [{"command": e.command, "description": e.description} for e in grouped["all_chat_administrators"]]
        scope_admin = {"type": "all_chat_administrators"}
        await client.set_my_commands(commands=admin_cmds, scope=scope_admin)
        calls.append({"scope": scope_admin, "commands": admin_cmds})

        # 3. all_private_chats scope
        private_cmds = [{"command": e.command, "description": e.description} for e in grouped["default"]]
        scope_private = {"type": "all_private_chats"}
        await client.set_my_commands(commands=private_cmds, scope=scope_private)
        calls.append({"scope": scope_private, "commands": private_cmds})

        # 4. chat_member / superuser scope
        if chat_members and grouped.get("superuser"):
            su_cmds = group_cmds + [{"command": e.command, "description": e.description} for e in grouped["superuser"]]
            for cid, uid in chat_members:
                scope_cm = {"type": "chat_member", "chat_id": cid, "user_id": uid}
                await client.set_my_commands(commands=su_cmds, scope=scope_cm)
                calls.append({"scope": scope_cm, "commands": su_cmds})
        elif superusers and grouped.get("superuser"):
            su_cmds = group_cmds + [{"command": e.command, "description": e.description} for e in grouped["superuser"]]
            for su_id in superusers:
                scope_su = {"type": "chat", "chat_id": su_id}
                await client.set_my_commands(commands=su_cmds, scope=scope_su)
                calls.append({"scope": scope_su, "commands": su_cmds})

        return calls

    @property
    def degraded_commands(self) -> list[RegisteredCommand]:
        return list(self._degraded_commands)

    @property
    def all_commands(self) -> list[RegisteredCommand]:
        return list(self._commands)

    def clear(self) -> None:
        self._commands.clear()
        self._by_key.clear()
        self._by_slash.clear()
        self._by_pattern.clear()
        self._by_alias.clear()
        self._degraded_commands.clear()


command_registry = CommandRegistry()


async def broadcast_commands(
    client: Any,
    registry: CommandRegistry = command_registry,
    superusers: list[int | str] | None = None,
    chat_members: list[tuple[int | str, int | str]] | None = None,
) -> list[dict[str, Any]]:
    """Broadcast registered commands to Telegram via set_my_commands."""
    return await registry.broadcast_commands(client, superusers=superusers, chat_members=chat_members)
