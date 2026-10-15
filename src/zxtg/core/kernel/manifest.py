from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any, Literal

from zxtg.core.kernel.enums import BlockType, LimitCheckType, LimitWatchType, PluginLimitType, PluginType

SEMVER_REGEX = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

CONFIG_KEY_REGEX = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
PLUGIN_KEY_REGEX = re.compile(r"^[a-z][a-z0-9_]{2,31}$")


class BotPerm(StrEnum):
    """Telegram Bot required administrator permissions."""

    CAN_DELETE_MESSAGES = "can_delete_messages"
    CAN_RESTRICT_MEMBERS = "can_restrict_members"
    CAN_PROMOTE_MEMBERS = "can_promote_members"
    CAN_INVITE_USERS = "can_invite_users"
    CAN_PIN_MESSAGES = "can_pin_messages"


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parse a SemVer string into (major, minor, patch). Raises ValueError on mismatch."""
    m = SEMVER_REGEX.match(version_str.strip())
    if not m:
        raise ValueError(f"Invalid SemVer version string: {version_str!r} (must be MAJOR.MINOR.PATCH)")
    return int(m.group("major")), int(m.group("minor")), int(m.group("patch"))


def matches_semver_range(version_str: str, spec_range: str) -> bool:
    """Check if version_str satisfies a comma-separated SemVer constraint (e.g. '>=1.0,<2.0')."""
    v_parts = parse_semver(version_str)
    constraints = [c.strip() for c in spec_range.split(",") if c.strip()]
    if not constraints:
        return True

    op_pattern = re.compile(r"^(>=|<=|==|!=|>|<|~=)?\s*(\d+(?:\.\d+)*)$")

    for constraint in constraints:
        match = op_pattern.match(constraint)
        if not match:
            raise ValueError(f"Unsupported SemVer specifier clause: {constraint!r}")
        op, target_str = match.groups()
        op = op or "=="

        target_parts = [int(p) for p in target_str.split(".")]
        while len(target_parts) < 3:
            target_parts.append(0)
        t_tuple = (target_parts[0], target_parts[1], target_parts[2])

        if op == "==":
            if v_parts != t_tuple:
                return False
        elif op == "!=":
            if v_parts == t_tuple:
                return False
        elif op == ">=":
            if v_parts < t_tuple:
                return False
        elif op == "<=":
            if v_parts > t_tuple:
                return False
        elif op == ">":
            if v_parts <= t_tuple:
                return False
        elif op == "<":
            if v_parts >= t_tuple:
                return False
        elif op == "~=":
            # ~=1.2 means >=1.2.0, <2.0.0
            next_major = (t_tuple[0] + 1, 0, 0)
            if not (t_tuple <= v_parts < next_major):
                return False

    return True


def validate_callback_data(callback_data: str) -> None:
    """Validate callback_data size does not exceed 64 UTF-8 bytes (FR-TG-11)."""
    encoded_len = len(callback_data.encode("utf-8"))
    if encoded_len > 64:
        raise ValueError(
            f"callback_data exceeds Telegram 64-byte limit: {encoded_len} bytes ({callback_data!r})"
        )


@dataclass(frozen=True)
class Example:
    """Command usage example."""

    command: str
    description: str = ""


@dataclass(frozen=True)
class Param:
    """Command parameter specification (Design §5.4 / FR-CMD-07)."""

    name: str
    type: Literal["int", "str", "bool", "word", "greedy"] = "str"
    required: bool = False
    default: Any = None
    help: str = ""


@dataclass(frozen=True)
class Cmd:
    """Command contract (Design §5.4, §5.5 / FR-CMD-01~09)."""

    key: str
    pattern: str = ""
    slash: str | None = None
    aliases: tuple[str, ...] | list[str] = field(default_factory=tuple)
    params: tuple[Param, ...] | list[Param] = field(default_factory=tuple)
    scope: PluginType | None = None
    help: str = ""
    examples: tuple[Example, ...] | list[Example] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConfigSpec:
    """Plugin configuration specification (Design §5.7 / FR-CFG-01~07)."""

    key: str
    type: str  # "int" | "float" | "str" | "bool" | "list" | "json"
    default: Any
    help: str = ""
    scope: Literal["global", "group"] = "global"
    min_value: float | None = None
    max_value: float | None = None
    choices: tuple[Any, ...] | list[Any] | None = None

    def __post_init__(self) -> None:
        if not CONFIG_KEY_REGEX.match(self.key):
            raise ValueError(
                f"Config key {self.key!r} violates regex ^[A-Z][A-Z0-9_]{{1,63}}$"
            )
        if callable(self.default):
            raise ValueError(f"Config {self.key} default cannot be a Callable (FR-CFG-04)")
        if self.choices is not None and callable(self.choices):
            raise ValueError(f"Config {self.key} choices cannot be a Callable (FR-CFG-04)")


@dataclass(frozen=True)
class LimitSpec:
    """Plugin limiter specification (Design §5.8 / FR-LIM-01~06)."""

    type: PluginLimitType
    status: bool = True
    check_type: LimitCheckType | BlockType = LimitCheckType.ALL
    watch_type: LimitWatchType = LimitWatchType.USER
    result: str | None = None
    cd: int | None = None
    max_count: int | None = None
    period: str | None = None

    def __post_init__(self) -> None:
        if self.type == PluginLimitType.COUNT and not self.period:
            raise ValueError("LimitSpec of type COUNT must explicitly declare period (FR-LIM-02)")


@dataclass(frozen=True)
class TaskSpec:
    """Scheduled background / periodic task specification (Design §5.9 / FR-TSK-01~07)."""

    key: str
    name: str
    func: Callable
    trigger: Literal["cron", "interval"]
    cron: str | None = None
    seconds: int | None = None
    default_status: bool = True
    check: Callable | None = None
    max_instances: int = 1
    misfire_grace_time: int = 60

    def __post_init__(self) -> None:
        if not self.misfire_grace_time or self.misfire_grace_time <= 0:
            raise ValueError("TaskSpec misfire_grace_time is mandatory and must be > 0 (FR-TSK-03)")
        if self.trigger == "cron" and not self.cron:
            raise ValueError("TaskSpec with trigger='cron' must specify a cron expression")
        if self.trigger == "interval" and (self.seconds is None or self.seconds <= 0):
            raise ValueError("TaskSpec with trigger='interval' must specify seconds > 0")


@dataclass(frozen=True)
class EventSpec:
    """Event subscription specification (Design §5.10)."""

    kind: Literal["join", "leave", "member_update", "join_request", "text", "callback"]
    func: Callable
    priority: int = 50


@dataclass(frozen=True)
class PluginManifest:
    """Complete Plugin Manifest contract (Design §5.3 / FR-PLG-12, FR-PLG-13)."""

    key: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    usage: str = ""
    superuser_help: str | None = None
    introduction: str | None = None
    precautions: tuple[str, ...] | list[str] | None = None
    plugin_type: PluginType = PluginType.NORMAL
    menu_type: str = "功能"
    is_show: bool = True
    parent: str | None = None
    level: int = 5
    admin_level: int | None = None
    default_status: bool = True
    limit_superuser: bool = False
    cost_gold: int = 0
    impression: float = 0.0
    cmds: tuple[Cmd, ...] | list[Cmd] = field(default_factory=tuple)
    aliases: frozenset[str] | set[str] = field(default_factory=frozenset)
    configs: tuple[ConfigSpec, ...] | list[ConfigSpec] = field(default_factory=tuple)
    limits: tuple[LimitSpec, ...] | list[LimitSpec] = field(default_factory=tuple)
    tasks: tuple[TaskSpec, ...] | list[TaskSpec] = field(default_factory=tuple)
    events: tuple[EventSpec, ...] | list[EventSpec] = field(default_factory=tuple)
    callbacks: tuple[str, ...] | list[str] = field(default_factory=tuple)
    requires_core: str = ">=1.0,<2.0"
    requires: tuple[str, ...] | list[str] = field(default_factory=tuple)
    requires_services: tuple[str, ...] | list[str] = field(default_factory=tuple)
    bot_permissions: frozenset[BotPerm] | set[BotPerm] = field(default_factory=frozenset)
    ignore_prompt: bool = False
    ignore_statistics: bool = False

    def __post_init__(self) -> None:
        # Validate SemVer version
        parse_semver(self.version)
        # Validate plugin key regex
        if not PLUGIN_KEY_REGEX.match(self.key):
            raise ValueError(
                f"Plugin key {self.key!r} violates regex ^[a-z][a-z0-9_]{{2,31}}$ (FR-PLG-03)"
            )
        # Validate callbacks if present
        for cb in self.callbacks:
            validate_callback_data(cb)
