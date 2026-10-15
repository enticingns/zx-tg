import pytest

from zxtg.core.context import CallContext, GroupView, PluginView, UserView
from zxtg.core.event import Actor, ChatRef, Role, UnifiedEvent
from zxtg.core.kernel.enums import BlockType, LimitCheckType, LimitWatchType, PluginLimitType
from zxtg.core.kernel.guards import GuardLimit
from zxtg.core.kernel.manifest import LimitSpec, PluginManifest
from zxtg.core.kernel.pipeline import run_pipeline
from zxtg.core.kernel.registry import PluginRegistry, registry
from zxtg.core.services.limit_service import LimitService, limit_service


@pytest.fixture(autouse=True)
def clean_limit_service():
    limit_service.clear()
    yield
    limit_service.clear()


def test_cd_limit_enforcement():
    """CD limit rejects calls within cooldown window and allows after expiry (§3, FR-LIM-01)."""
    ls = LimitService()
    spec = LimitSpec(
        type=PluginLimitType.CD,
        cd=10,
        result="技能冷却中，请稍后再试",
    )
    m = PluginManifest(key="skill_pkg", name="Skill", limits=[spec])

    base_time = 1000.0

    # Call 1: Allowed at t=1000.0
    allowed, _ = ls.check_all_and_record(m, user_id="user_1", now=base_time)
    assert allowed is True

    # Call 2: Blocked at t=1005.0 (5s elapsed < 10s cd)
    allowed, reason = ls.check_all_and_record(m, user_id="user_1", now=base_time + 5.0)
    assert allowed is False
    assert reason == "技能冷却中，请稍后再试"

    # Call 3: Allowed at t=1011.0 (11s elapsed >= 10s cd)
    allowed, _ = ls.check_all_and_record(m, user_id="user_1", now=base_time + 11.0)
    assert allowed is True


def test_count_rolling_window_limit():
    """COUNT limit with rolling period window enforces max calls and resets after period (§3, FR-LIM-02)."""
    ls = LimitService()
    # 3 calls per 1 hour (3600s)
    spec = LimitSpec(
        type=PluginLimitType.COUNT,
        max_count=3,
        period="1h",
        result="已达到每小时调用上限",
    )
    m = PluginManifest(key="query_pkg", name="Query", limits=[spec])

    t0 = 2000.0

    # Call 1, 2, 3: All allowed
    assert ls.check_all_and_record(m, user_id="user_1", now=t0)[0] is True
    assert ls.check_all_and_record(m, user_id="user_1", now=t0 + 100)[0] is True
    assert ls.check_all_and_record(m, user_id="user_1", now=t0 + 200)[0] is True

    # Call 4: Exceeds 3 calls within window -> Rejected
    allowed, reason = ls.check_all_and_record(m, user_id="user_1", now=t0 + 500)
    assert allowed is False
    assert reason == "已达到每小时调用上限"

    # Call 5: Advance clock past window (t0 + 3601s): first call expired -> Allowed!
    allowed, _ = ls.check_all_and_record(m, user_id="user_1", now=t0 + 3601)
    assert allowed is True


def test_block_permanent_rejection():
    """BLOCK limit permanently rejects calls (§3, FR-LIM-03)."""
    ls = LimitService()
    spec = LimitSpec(
        type=PluginLimitType.BLOCK,
        result="该插件已由管理员永久拉黑",
    )
    m = PluginManifest(key="banned_pkg", name="Banned", limits=[spec])

    # Call 1: Rejected
    allowed, reason = ls.check_all_and_record(m, user_id="user_1")
    assert allowed is False
    assert reason == "该插件已由管理员永久拉黑"

    # Call 2: Still rejected
    allowed, reason = ls.check_all_and_record(m, user_id="user_1")
    assert allowed is False


def test_watch_type_user_and_group():
    """Watch type correctly isolates limits by USER or GROUP (FR-LIM-04)."""
    ls = LimitService()
    spec = LimitSpec(
        type=PluginLimitType.CD,
        cd=30,
        watch_type=LimitWatchType.USER,
    )
    m = PluginManifest(key="cd_pkg", name="CD", limits=[spec])

    t = 5000.0
    # user_1 is on CD
    assert ls.check_all_and_record(m, user_id="user_1", now=t)[0] is True
    assert ls.check_all_and_record(m, user_id="user_1", now=t + 5)[0] is False

    # user_2 is NOT on CD
    assert ls.check_all_and_record(m, user_id="user_2", now=t + 5)[0] is True


def test_check_type_private_and_group():
    """Check type applies limits only in matching chat types (FR-LIM-05)."""
    ls = LimitService()
    # Only applies in GROUP
    spec = LimitSpec(
        type=PluginLimitType.BLOCK,
        check_type=LimitCheckType.GROUP,
        result="群聊中禁用此功能",
    )
    m = PluginManifest(key="priv_only_pkg", name="PrivOnly", limits=[spec])

    # Private chat (is_group=False) -> Allowed
    assert ls.check_all_and_record(m, user_id="u1", is_group=False)[0] is True

    # Group chat (is_group=True) -> Blocked
    allowed, reason = ls.check_all_and_record(m, user_id="u1", is_group=True)
    assert allowed is False
    assert reason == "群聊中禁用此功能"


def test_superuser_limit_bypass():
    """Superuser bypasses limits when limit_superuser is False (Design §5.3, §5.8)."""
    ls = LimitService()
    spec = LimitSpec(
        type=PluginLimitType.BLOCK,
        result="Banned",
    )
    # limit_superuser=False means superusers are exempt
    m = PluginManifest(key="admin_pkg", name="AdminPkg", limit_superuser=False, limits=[spec])

    # Normal user -> Blocked
    assert ls.check_all_and_record(m, user_id="u1", is_superuser=False)[0] is False

    # Superuser -> Allowed
    assert ls.check_all_and_record(m, user_id="u1", is_superuser=True)[0] is True


@pytest.mark.asyncio
async def test_guard_limit_pipeline_integration():
    """GuardLimit integrates seamlessly with pipeline and halts execution on limit violation."""
    spec = LimitSpec(
        type=PluginLimitType.CD,
        cd=60,
        result="技能正在冷却",
    )
    m = PluginManifest(key="limited_pkg", name="Limited", limits=[spec])
    registry.register(m)

    actor = Actor(id=999, full_name="Player")
    event = UnifiedEvent(actor=actor, text="test")
    ctx = CallContext(
        event=event,
        user=UserView(id="999"),
        plugin=PluginView(key="limited_pkg"),
    )

    # 1. First execution passes
    v1 = await GuardLimit(ctx)
    assert bool(v1) is True

    # 2. Second execution immediately after is denied
    v2 = await GuardLimit(ctx)
    assert bool(v2) is False
    assert "技能正在冷却" in v2.reason
