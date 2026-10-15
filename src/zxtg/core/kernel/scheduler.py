import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Any

from tortoise import Tortoise

from zxtg.core.kernel.manifest import TaskSpec
from zxtg.models.task_record import TaskRecord

logger = logging.getLogger("zxtg.kernel.scheduler")


@dataclass
class TaskContext:
    """Execution context passed to scheduled tasks."""

    task_key: str
    group_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _parse_field(field_str: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field with *, commas, ranges, and steps."""
    result: set[int] = set()
    for part in field_str.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            subparts = part.split("/", 1)
            part = subparts[0]
            step = int(subparts[1])

        if part == "*":
            start, end = min_val, max_val
        elif "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(part)

        for val in range(start, end + 1, step):
            if min_val <= val <= max_val:
                result.add(val)
    return result


def matches_cron(cron_expr: str, dt: datetime) -> bool:
    """Check if a datetime matches a 5-part cron expression (minute hour day month day_of_week)."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: {cron_expr!r}")

    minutes = _parse_field(parts[0], 0, 59)
    hours = _parse_field(parts[1], 0, 23)
    days = _parse_field(parts[2], 1, 31)
    months = _parse_field(parts[3], 1, 12)
    # Python weekday(): Monday is 0 and Sunday is 6. Cron standard: 0 is Sunday, 1 is Monday ... 6 is Saturday (or 7 Sunday)
    cron_weekday = (dt.weekday() + 1) % 7
    weekdays = _parse_field(parts[4], 0, 6)

    return (
        dt.minute in minutes
        and dt.hour in hours
        and dt.day in days
        and dt.month in months
        and cron_weekday in weekdays
    )


class TaskScheduler:
    """Lightweight asyncio-based task scheduler (FR-TSK-01~07)."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskSpec] = {}
        self._running_instances: dict[str, int] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._egress_messages: list[tuple[str, Any]] = []

    def add_task(self, spec: TaskSpec) -> None:
        """Register a TaskSpec into the scheduler."""
        self._tasks[spec.key] = spec
        self._running_instances[spec.key] = 0

    def remove_task(self, key: str) -> None:
        """Remove a task by key."""
        self._tasks.pop(key, None)
        self._running_instances.pop(key, None)

    async def is_task_enabled_for_group(self, task_key: str, group_id: str) -> bool:
        """Check group-level task switch in task_record table (FR-TSK-02)."""
        if not Tortoise._inited:
            return True
        record = await TaskRecord.get_or_none(task_key=task_key, group_id=str(group_id))
        if record is not None:
            return record.status
        return True

    async def egress_send(self, group_id: str, message: Any) -> bool:
        """Unified message egress for scheduled tasks (FR-TSK-05, rate limiting in M2)."""
        self._egress_messages.append((str(group_id), message))
        logger.info("Scheduler egress sent message to group %s", group_id)
        return True

    async def execute_task(
        self,
        spec: TaskSpec,
        group_id: str | None = None,
        scheduled_time: float | None = None,
    ) -> bool:
        """Execute a task instance with concurrency, misfire, group switch, and pre-check guards."""
        now = datetime.now(timezone.utc).timestamp()

        # 1. Misfire grace time check (FR-TSK-03)
        if scheduled_time is not None:
            elapsed_since_scheduled = now - scheduled_time
            if elapsed_since_scheduled > spec.misfire_grace_time:
                logger.warning(
                    "Task %s misfired by %.1fs (grace time: %ds), skipping execution",
                    spec.key,
                    elapsed_since_scheduled,
                    spec.misfire_grace_time,
                )
                return False

        # 2. Concurrency limit check (FR-TSK-04)
        current_instances = self._running_instances.get(spec.key, 0)
        if current_instances >= spec.max_instances:
            logger.warning(
                "Task %s reached max concurrent instances (%d), skipping",
                spec.key,
                spec.max_instances,
            )
            return False

        # 3. Group switch check (FR-TSK-02)
        if group_id is not None:
            enabled = await self.is_task_enabled_for_group(spec.key, group_id)
            if not enabled:
                logger.info("Task %s is disabled in group %s, skipping", spec.key, group_id)
                return False

        # 4. Pre-check function (FR-TSK-06)
        if spec.check is not None:
            try:
                check_res = spec.check()
                if asyncio.iscoroutine(check_res):
                    check_res = await check_res
                if not check_res:
                    logger.debug("Task %s pre-check returned False, skipping", spec.key)
                    return False
            except Exception as e:
                logger.error("Task %s pre-check raised exception: %s", spec.key, e)
                return False

        # 5. Execute task
        self._running_instances[spec.key] = current_instances + 1
        ctx = TaskContext(task_key=spec.key, group_id=group_id)
        try:
            res = spec.func(ctx)
            if asyncio.iscoroutine(res):
                await res
            # Update last_run in DB if applicable
            if group_id is not None and Tortoise._inited:
                record = await TaskRecord.get_or_none(task_key=spec.key, group_id=str(group_id))
                if record:
                    record.last_run = datetime.now(timezone.utc)
                    await record.save()
            return True
        finally:
            self._running_instances[spec.key] = max(0, self._running_instances.get(spec.key, 1) - 1)

    async def start(self) -> None:
        """Start the background scheduling loop."""
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background scheduling loop."""
        self._stop_event.set()
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Internal worker loop executing interval and cron jobs."""
        last_interval_ticks: dict[str, float] = {}

        while not self._stop_event.is_set():
            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()

            for spec in list(self._tasks.values()):
                if spec.trigger == "interval" and spec.seconds:
                    last_tick = last_interval_ticks.get(spec.key, now_ts)
                    if now_ts - last_tick >= spec.seconds:
                        last_interval_ticks[spec.key] = now_ts
                        asyncio.create_task(self.execute_task(spec, scheduled_time=now_ts))
                    elif spec.key not in last_interval_ticks:
                        last_interval_ticks[spec.key] = now_ts

                elif spec.trigger == "cron" and spec.cron:
                    if matches_cron(spec.cron, now_dt):
                        asyncio.create_task(self.execute_task(spec, scheduled_time=now_ts))

            await asyncio.sleep(1)

    def clear(self) -> None:
        """Reset scheduler state for tests."""
        self._tasks.clear()
        self._running_instances.clear()
        self._egress_messages.clear()


scheduler = TaskScheduler()
