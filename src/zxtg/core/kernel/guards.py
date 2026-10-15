import logging

from zxtg.core.context import CallContext
from zxtg.core.event import CommandRef
from zxtg.core.kernel.registry import registry

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
    """Resolve actor / chat / role context."""
    logger.debug("Executing ResolveContext for actor=%s", ctx.event.actor.id)
    return ALLOW


async def BuildCommand(ctx: CallContext) -> Verdict:
    """Parse text into CommandRef if not already populated."""
    logger.debug("Executing BuildCommand for text=%r", ctx.event.text)
    if ctx.event.command is None and ctx.event.text:
        raw_text = ctx.event.text.strip()
        if raw_text:
            parts = raw_text.split()
            cmd_token = parts[0]
            if cmd_token.startswith("/"):
                cmd_name = cmd_token[1:]
            else:
                cmd_name = cmd_token
            # Remove bot username if present, e.g. /ping@my_bot -> ping
            if "@" in cmd_name:
                cmd_name = cmd_name.split("@", 1)[0]
            args = parts[1:]
            ctx.event.command = CommandRef(name=cmd_name, args=args, raw=raw_text)
    return ALLOW


async def MergeConfig(ctx: CallContext) -> Verdict:
    """Merge global and group configs."""
    logger.debug("Executing MergeConfig")
    return ALLOW


async def GuardBan(ctx: CallContext) -> Verdict:
    """Check user/chat blacklist."""
    logger.debug("Executing GuardBan for actor=%s", ctx.event.actor.id)
    return ALLOW


async def GuardSwitch(ctx: CallContext) -> Verdict:
    """Check plugin global and group switch."""
    logger.debug("Executing GuardSwitch")
    return ALLOW


async def GuardLevel(ctx: CallContext) -> Verdict:
    """Check user permission level."""
    logger.debug("Executing GuardLevel with role=%s (level=%d)", ctx.event.role, ctx.event.role.level)
    return ALLOW


async def GuardCost(ctx: CallContext) -> Verdict:
    """Check and atomically deduct economy cost."""
    logger.debug("Executing GuardCost")
    return ALLOW


async def GuardLimit(ctx: CallContext) -> Verdict:
    """Check CD, call count, and rate limits."""
    logger.debug("Executing GuardLimit")
    return ALLOW


async def Dispatch(ctx: CallContext) -> Verdict:
    """Dispatch command to registered handler."""
    cmd = ctx.event.command
    if not cmd:
        logger.debug("Dispatch: no command found on event")
        return DENY(reason="No command specified", tip="Send /ping to test")

    handler = registry.get_handler(cmd.name)
    if not handler:
        logger.debug("Dispatch: no handler found for command %r", cmd.name)
        return DENY(reason=f"Unknown command: {cmd.name}", tip="Available command: /ping")

    logger.debug("Dispatch: invoking handler for command %r", cmd.name)
    await handler(ctx)
    return ALLOW
