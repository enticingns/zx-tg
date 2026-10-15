from collections.abc import Callable, Coroutine
import logging
from typing import Any, Protocol, runtime_checkable

from zxtg.core.context import CallContext
from zxtg.core.kernel.guards import (
    ALLOW,
    DENY,
    BuildCommand,
    Dispatch,
    GuardBan,
    GuardCost,
    GuardLevel,
    GuardLimit,
    GuardSwitch,
    MergeConfig,
    ResolveContext,
    Verdict,
)

logger = logging.getLogger("zxtg.kernel.pipeline")


@runtime_checkable
class GuardProtocol(Protocol):
    """Protocol that every Guard unit must implement."""

    async def __call__(self, ctx: CallContext) -> Verdict:
        ...


Guard = Callable[[CallContext], Coroutine[Any, Any, Verdict]]

# Ordered pipeline list. Order is strictly determined by position (FR-AUTH-02, FR-AUTH-03).
# Priority numbers are strictly forbidden.
PIPELINE: list[Guard] = [
    ResolveContext,
    BuildCommand,
    MergeConfig,
    GuardBan,
    GuardSwitch,
    GuardLevel,
    GuardCost,
    GuardLimit,
    Dispatch,
]


async def run_pipeline(
    ctx: CallContext,
    pipeline: list[Guard] | None = None,
) -> Verdict:
    """Execute guards sequentially until a guard denies or all guards allow."""
    active_pipeline = pipeline if pipeline is not None else PIPELINE
    logger.debug("Starting pipeline with %d guards for context: %r", len(active_pipeline), ctx)

    for guard in active_pipeline:
        guard_name = getattr(guard, "__name__", repr(guard))
        verdict = await guard(ctx)
        logger.debug("Guard %s returned %r", guard_name, verdict)
        if not verdict:
            logger.info("Pipeline denied at %s: %s (%s)", guard_name, verdict.reason, verdict.tip)
            return verdict

    logger.debug("Pipeline completed with ALLOW")
    return ALLOW
