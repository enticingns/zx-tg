from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Chat member role with level mapping (owner=100, administrator=10, member=0, restricted=0)."""

    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"

    @property
    def level(self) -> int:
        match self:
            case Role.OWNER:
                return 100
            case Role.ADMINISTRATOR:
                return 10
            case _:
                return 0


@dataclass
class Actor:
    """Event initiator (user / bot)."""

    id: str | int
    full_name: str
    username: str | None = None
    is_bot: bool = False

    @property
    def display(self) -> str:
        """Fallback to full_name when username is None or empty (FR-TG-08)."""
        return self.username if self.username else self.full_name


@dataclass
class ChatRef:
    """Chat reference."""

    id: str | int
    type: str  # "private" | "group" | "supergroup"
    title: str | None = None


@dataclass
class CommandRef:
    """Command reference parsed from text or slash command."""

    name: str
    args: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class UnifiedEvent:
    """Platform-agnostic unified event model (FR-CORE-07, FR-CORE-08)."""

    actor: Actor
    kind: str = "text"  # text|command|callback|join|leave|member_update|join_request
    text: str = ""
    role: Role = Role.MEMBER
    chat: ChatRef | None = None
    command: CommandRef | None = None
    message_id: int = 0
    raw: Any = None  # Escape hatch: disabled in plugin layer (Boundary B)
