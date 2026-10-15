import pytest

from zxtg.core.context import CallContext, GroupView, PluginView, SentMessage, UserView
from zxtg.core.event import Actor, ChatRef, CommandRef, Role, UnifiedEvent
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
from zxtg.core.kernel.pipeline import PIPELINE, run_pipeline
from zxtg.core.kernel.registry import Cmd, PluginManifest, PluginRegistry


def test_pipeline_order_and_absence_of_priorities():
    """Verify PIPELINE order is fixed by list position without numeric priorities (FR-AUTH-03)."""
    expected = [
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
    assert PIPELINE == expected
    for guard in PIPELINE:
        # Check that guards do not define or rely on numeric priority attributes
        assert not hasattr(guard, "priority"), f"Guard {guard} must not have a priority attribute"


def test_verdict_behavior():
    """Verify Verdict boolean logic, equality, and repr formatting."""
    allow = ALLOW
    assert bool(allow) is True
    assert repr(allow) == "Verdict(ALLOW)"

    deny = DENY(reason="Plugin disabled in group", tip="Use /enable to activate")
    assert bool(deny) is False
    assert deny.reason == "Plugin disabled in group"
    assert deny.tip == "Use /enable to activate"
    assert "DENY" in repr(deny)
    assert "Plugin disabled in group" in repr(deny)

    assert ALLOW == Verdict(True)
    assert DENY("test", "tip") == Verdict(False, "test", "tip")
    assert ALLOW != DENY("test", "tip")


def test_call_context_immutability_and_repr():
    """Verify CallContext snapshots and repr representation (FR-AUTH-10, Design §5.12)."""
    actor = Actor(id=1, username="test", full_name="Test")
    event = UnifiedEvent(actor=actor, text="test")
    user = UserView(id="u1", level=10, gold=500, impression=20.0)
    group = GroupView(id="g1", title="Group 1", level=5)
    plugin = PluginView(key="sample", name="Sample", config={"KEY": "VAL"})

    ctx = CallContext(event=event, user=user, group=group, plugin=plugin)
    assert ctx.event == event
    assert ctx.user == user
    assert ctx.group == group
    assert ctx.plugin == plugin

    ctx_repr = repr(ctx)
    assert "CallContext(" in ctx_repr
    assert "u1" in ctx_repr
    assert "g1" in ctx_repr
    assert "sample" in ctx_repr


@pytest.mark.asyncio
async def test_run_pipeline_allow_and_dispatch():
    """Verify pipeline runs through all guards to dispatch handler when all allow."""
    handled = []

    async def mock_handler(ctx: CallContext) -> None:
        handled.append(ctx.event.command.name if ctx.event.command else "")
        await ctx.reply("handler reply")

    test_registry = PluginRegistry()
    manifest = PluginManifest(
        key="test_pkg",
        name="Test Package",
        cmds=[Cmd(key="testcmd", pattern="testcmd", slash="testcmd")],
    )
    test_registry.register(manifest, {"testcmd": mock_handler})

    # Temporarily monkeypatch global registry handler for Dispatch
    from zxtg.core.kernel import registry as global_registry

    global_registry.register(manifest, {"testcmd": mock_handler})

    actor = Actor(id=1, full_name="User")
    event = UnifiedEvent(
        actor=actor,
        text="/testcmd arg1",
    )
    user = UserView(id="u1", level=0)
    ctx = CallContext(event=event, user=user)

    verdict = await run_pipeline(ctx)
    assert bool(verdict) is True
    assert handled == ["testcmd"]
    assert len(ctx.replies) == 1
    assert ctx.replies[0].content == "handler reply"


@pytest.mark.asyncio
async def test_run_pipeline_short_circuit_on_deny():
    """Verify pipeline halts immediately at the first failing guard without reaching dispatch."""
    invoked = []

    async def guard_pass(ctx: CallContext) -> Verdict:
        invoked.append("pass")
        return ALLOW

    async def guard_fail(ctx: CallContext) -> Verdict:
        invoked.append("fail")
        return DENY(reason="Permission denied", tip="Ask admin")

    async def guard_unreached(ctx: CallContext) -> Verdict:
        invoked.append("unreached")
        return ALLOW

    custom_pipeline = [guard_pass, guard_fail, guard_unreached]

    actor = Actor(id=1, full_name="User")
    event = UnifiedEvent(actor=actor, text="test")
    ctx = CallContext(event=event, user=UserView(id="u1"))

    verdict = await run_pipeline(ctx, pipeline=custom_pipeline)
    assert bool(verdict) is False
    assert verdict.reason == "Permission denied"
    assert invoked == ["pass", "fail"]
    assert "unreached" not in invoked
