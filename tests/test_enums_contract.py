"""Contract tests locking enum names and values verbatim to upstream (Design §1.2, NFR-19)."""
from zxtg.core.kernel.enums import (
    BlockType,
    LimitCheckType,
    LimitWatchType,
    PluginLimitType,
    PluginType,
)


def test_plugin_type_contract():
    expected = {
        "SUPERUSER": "SUPERUSER",
        "ADMIN": "ADMIN",
        "SUPER_AND_ADMIN": "ADMIN_SUPER",
        "NORMAL": "NORMAL",
        "DEPENDANT": "DEPENDANT",
        "HIDDEN": "HIDDEN",
        "PARENT": "PARENT",
    }
    actual = {member.name: member.value for member in PluginType}
    assert actual == expected, f"PluginType mismatch: {actual} != {expected}"


def test_block_type_contract():
    expected = {
        "PRIVATE": "PRIVATE",
        "GROUP": "GROUP",
        "ALL": "ALL",
    }
    actual = {member.name: member.value for member in BlockType}
    assert actual == expected, f"BlockType mismatch: {actual} != {expected}"


def test_plugin_limit_type_contract():
    expected = {
        "CD": "CD",
        "COUNT": "COUNT",
        "BLOCK": "BLOCK",
    }
    actual = {member.name: member.value for member in PluginLimitType}
    assert actual == expected, f"PluginLimitType mismatch: {actual} != {expected}"


def test_limit_check_type_contract():
    expected = {
        "PRIVATE": "PRIVATE",
        "GROUP": "GROUP",
        "ALL": "ALL",
    }
    actual = {member.name: member.value for member in LimitCheckType}
    assert actual == expected, f"LimitCheckType mismatch: {actual} != {expected}"


def test_limit_watch_type_contract():
    expected = {
        "USER": "USER",
        "GROUP": "GROUP",
        "ALL": "ALL",
    }
    actual = {member.name: member.value for member in LimitWatchType}
    assert actual == expected, f"LimitWatchType mismatch: {actual} != {expected}"
