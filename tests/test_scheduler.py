import asyncio
from datetime import datetime, timezone
import pytest
from tortoise import Tortoise

from zxtg.core.kernel.manifest import TaskSpec
from zxtg.core.kernel.scheduler import TaskContext, TaskScheduler, matches_cron
from zxtg.core.services.db import close_db, init_db
from zxtg.models.task_record import TaskRecord


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db(db_path=":memory:", generate_schemas=True)
    yield
    await close_db()


def test_cron_matcher():
    """Verify matches_cron parsing and matching (FR-TSK-01)."""
    # 2026-10-15 08:30:00 (Thursday)
    # Python weekday: Mon=0, Tue=1, Wed=2, Thu=3. Cron weekday: Thu = (3+1)%7 = 4.
    dt = datetime(2026, 10, 15, 8, 30, 0, tzinfo=timezone.utc)

    assert matches_cron("30 8 * * *", dt) is True
    assert matches_cron("*/10 8 * * *", dt) is True
    assert matches_cron("0 8 * * *", dt) is False
    assert matches_cron("30 9 * * *", dt) is False
    assert matches_cron("* * * * *", dt) is True


@pytest.mark.asyncio
async def test_misfire_grace_time():
    """Tasks misfired beyond grace time are skipped (FR-TSK-03)."""
    scheduler = TaskScheduler()
    runs = []

    async def sample_task(ctx: TaskContext) -> None:
        runs.append("run")

    spec = TaskSpec(
        key="test:misfire",
        name="Misfire Test",
        func=sample_task,
        trigger="interval",
        seconds=10,
        misfire_grace_time=30,
    )
    scheduler.add_task(spec)

    now = datetime.now(timezone.utc).timestamp()

    # Scheduled 60s ago > 30s grace time -> skipped
    res1 = await scheduler.execute_task(spec, scheduled_time=now - 60)
    assert res1 is False
    assert len(runs) == 0

    # Scheduled 10s ago <= 30s grace time -> runs
    res2 = await scheduler.execute_task(spec, scheduled_time=now - 10)
    assert res2 is True
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_max_instances_concurrency():
    """Task concurrency is constrained by max_instances (FR-TSK-04)."""
    scheduler = TaskScheduler()
    active_count = []

    async def slow_task(ctx: TaskContext) -> None:
        active_count.append("active")
        await asyncio.sleep(0.05)

    spec = TaskSpec(
        key="test:concurrency",
        name="Concurrency Test",
        func=slow_task,
        trigger="interval",
        seconds=10,
        max_instances=1,
    )
    scheduler.add_task(spec)

    t1 = asyncio.create_task(scheduler.execute_task(spec))
    await asyncio.sleep(0.01)  # t1 is running
    t2 = asyncio.create_task(scheduler.execute_task(spec))

    res1, res2 = await asyncio.gather(t1, t2)
    assert res1 is True
    assert res2 is False
    assert len(active_count) == 1


@pytest.mark.asyncio
async def test_task_group_switch():
    """Group-level task switch suppresses execution for disabled groups (FR-TSK-02)."""
    scheduler = TaskScheduler()
    ran_groups = []

    async def task_fn(ctx: TaskContext) -> None:
        ran_groups.append(ctx.group_id)

    spec = TaskSpec(
        key="sign_in:reset",
        name="Reset",
        func=task_fn,
        trigger="cron",
        cron="0 0 * * *",
    )
    scheduler.add_task(spec)

    # Disable in group_2
    await TaskRecord.create(task_key="sign_in:reset", group_id="grp_2", status=False)

    # Execute for grp_1 -> Allowed
    res1 = await scheduler.execute_task(spec, group_id="grp_1")
    assert res1 is True
    assert "grp_1" in ran_groups

    # Execute for grp_2 -> Disabled, skipped
    res2 = await scheduler.execute_task(spec, group_id="grp_2")
    assert res2 is False
    assert "grp_2" not in ran_groups


@pytest.mark.asyncio
async def test_task_pre_check_and_egress():
    """Task pre-check condition and egress messaging (FR-TSK-05, FR-TSK-06)."""
    scheduler = TaskScheduler()
    ran = []

    async def task_fn(ctx: TaskContext) -> None:
        ran.append(True)
        await scheduler.egress_send(ctx.group_id or "default", "Hello from task")

    should_run = False

    def pre_check() -> bool:
        return should_run

    spec = TaskSpec(
        key="test:precheck",
        name="Precheck Test",
        func=task_fn,
        trigger="interval",
        seconds=10,
        check=pre_check,
    )
    scheduler.add_task(spec)

    # pre_check returns False -> Skipped
    assert await scheduler.execute_task(spec) is False
    assert len(ran) == 0

    # pre_check returns True -> Executed and sent egress
    should_run = True
    assert await scheduler.execute_task(spec, group_id="grp_100") is True
    assert len(ran) == 1
    assert len(scheduler._egress_messages) == 1
    assert scheduler._egress_messages[0] == ("grp_100", "Hello from task")
