import pytest

from zxtg.core.context import CallContext, GroupView, PluginView, UserView
from zxtg.core.event import Actor, UnifiedEvent
from zxtg.core.kernel.manifest import ConfigSpec, PluginManifest
from zxtg.core.kernel.pipeline import MergeConfig
from zxtg.core.services.config_service import ConfigService, config_service


@pytest.fixture(autouse=True)
def clean_config_service():
    config_service.clear()
    yield
    config_service.clear()


def test_config_key_regex():
    """Config key must conform to ^[A-Z][A-Z0-9_]{1,63}$ (FR-CFG-02)."""
    # Valid
    s1 = ConfigSpec(key="MAX_SIGN_GOLD", type="int", default=100)
    assert s1.key == "MAX_SIGN_GOLD"

    s2 = ConfigSpec(key="BONUS_2_RATE", type="float", default=1.5)
    assert s2.key == "BONUS_2_RATE"

    # Invalid lowercase
    with pytest.raises(ValueError, match="violates regex"):
        ConfigSpec(key="max_sign_gold", type="int", default=100)

    # Invalid leading digit
    with pytest.raises(ValueError, match="violates regex"):
        ConfigSpec(key="1_MAX_GOLD", type="int", default=100)

    # Invalid hyphen
    with pytest.raises(ValueError, match="violates regex"):
        ConfigSpec(key="MAX-GOLD", type="int", default=100)


def test_callable_strictly_forbidden():
    """Callables are strictly forbidden in ConfigSpec (FR-CFG-04)."""
    with pytest.raises(ValueError, match="cannot be a Callable"):
        ConfigSpec(key="DYN_VAL", type="int", default=lambda: 10)

    with pytest.raises(ValueError, match="cannot be a Callable"):
        ConfigSpec(key="DYN_CHOICES", type="str", default="A", choices=lambda: ["A", "B"])


def test_config_three_tier_override():
    """Configuration three-tier resolution: Default -> Global -> Group (FR-CFG-01, §3)."""
    cs = ConfigService()
    spec = ConfigSpec(
        key="DAILY_GOLD_LIMIT",
        type="int",
        default=100,
        scope="group",
        min_value=10,
        max_value=1000,
    )
    cs.register_spec("sign_in", spec)

    # 1. Tier 1: Default
    assert cs.get("DAILY_GOLD_LIMIT", group_id=None, plugin_key="sign_in") == 100
    assert cs.get("DAILY_GOLD_LIMIT", group_id="group_1", plugin_key="sign_in") == 100

    # 2. Tier 2: Global overrides Default
    cs.set_global("DAILY_GOLD_LIMIT", 200, plugin_key="sign_in")
    assert cs.get("DAILY_GOLD_LIMIT", group_id=None, plugin_key="sign_in") == 200
    assert cs.get("DAILY_GOLD_LIMIT", group_id="group_1", plugin_key="sign_in") == 200
    assert cs.get("DAILY_GOLD_LIMIT", group_id="group_2", plugin_key="sign_in") == 200

    # 3. Tier 3: Group overrides Global
    cs.set_group("group_1", "DAILY_GOLD_LIMIT", 500, plugin_key="sign_in")
    # group_1 gets 500
    assert cs.get("DAILY_GOLD_LIMIT", group_id="group_1", plugin_key="sign_in") == 500
    # group_2 still gets global 200
    assert cs.get("DAILY_GOLD_LIMIT", group_id="group_2", plugin_key="sign_in") == 200
    # global query still gets 200
    assert cs.get("DAILY_GOLD_LIMIT", group_id=None, plugin_key="sign_in") == 200


def test_illegal_config_values_rejected():
    """Illegal config values must be rejected with explicit errors (FR-CFG-07, §3)."""
    cs = ConfigService()
    spec_int = ConfigSpec(
        key="MAX_RETRIES",
        type="int",
        default=3,
        min_value=1,
        max_value=10,
    )
    cs.register_spec("network", spec_int)

    # Type error
    with pytest.raises(ValueError, match="expected int"):
        cs.set_global("MAX_RETRIES", "not_a_number", plugin_key="network")

    # Min range error
    with pytest.raises(ValueError, match="less than min_value"):
        cs.set_global("MAX_RETRIES", 0, plugin_key="network")

    # Max range error
    with pytest.raises(ValueError, match="greater than max_value"):
        cs.set_global("MAX_RETRIES", 15, plugin_key="network")

    # Choices error
    spec_choice = ConfigSpec(
        key="LOG_LEVEL",
        type="str",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    cs.register_spec("system", spec_choice)

    with pytest.raises(ValueError, match="not in allowed choices"):
        cs.set_global("LOG_LEVEL", "VERBOSE", plugin_key="system")

    # Scope error: global-only config cannot be set at group level
    spec_global_only = ConfigSpec(
        key="SERVER_BIND_IP",
        type="str",
        default="127.0.0.1",
        scope="global",
    )
    cs.register_spec("system", spec_global_only)
    with pytest.raises(ValueError, match="has scope 'global' and cannot be set at group level"):
        cs.set_group("group_1", "SERVER_BIND_IP", "0.0.0.0", plugin_key="system")


def test_export_json_schema():
    """All configuration specs can be exported to standard JSON Schema (FR-CFG-05)."""
    cs = ConfigService()
    spec1 = ConfigSpec(
        key="SIGN_GOLD",
        type="int",
        default=50,
        help="Amount of gold gained from sign-in",
        min_value=1,
        max_value=1000,
    )
    spec2 = ConfigSpec(
        key="SIGN_MODE",
        type="str",
        default="NORMAL",
        help="Sign in mode",
        choices=["NORMAL", "SPECIAL"],
    )
    cs.register_spec("sign_in", spec1)
    cs.register_spec("sign_in", spec2)

    schema = cs.export_json_schema("sign_in")
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "SIGN_GOLD" in props
    assert props["SIGN_GOLD"]["type"] == "integer"
    assert props["SIGN_GOLD"]["minimum"] == 1
    assert props["SIGN_GOLD"]["maximum"] == 1000
    assert props["SIGN_GOLD"]["default"] == 50

    assert "SIGN_MODE" in props
    assert props["SIGN_MODE"]["type"] == "string"
    assert props["SIGN_MODE"]["enum"] == ["NORMAL", "SPECIAL"]
    assert props["SIGN_MODE"]["default"] == "NORMAL"


@pytest.mark.asyncio
async def test_call_context_config_three_tier_resolution():
    """CallContext.config resolves 3-tier config automatically (Design §5.7, §5.12)."""
    spec = ConfigSpec(
        key="REWARD_GOLD",
        type="int",
        default=10,
        scope="group",
    )
    config_service.register_spec("reward_pkg", spec)
    config_service.set_global("REWARD_GOLD", 25, plugin_key="reward_pkg")
    config_service.set_group("grp_abc", "REWARD_GOLD", 99, plugin_key="reward_pkg")

    actor = Actor(id=1, full_name="User")
    event = UnifiedEvent(actor=actor, text="test")

    # In group grp_abc -> should resolve to 99
    ctx_in_group = CallContext(
        event=event,
        user=UserView(id="1"),
        group=GroupView(id="grp_abc"),
        plugin=PluginView(key="reward_pkg"),
    )
    await MergeConfig(ctx_in_group)
    assert await ctx_in_group.config("REWARD_GOLD") == 99

    # In another group -> should resolve to global 25
    ctx_other_group = CallContext(
        event=event,
        user=UserView(id="1"),
        group=GroupView(id="grp_other"),
        plugin=PluginView(key="reward_pkg"),
    )
    await MergeConfig(ctx_other_group)
    assert await ctx_other_group.config("REWARD_GOLD") == 25
