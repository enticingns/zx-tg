import logging
import re
import time
from typing import Any

from zxtg.core.kernel.enums import BlockType, LimitCheckType, LimitWatchType, PluginLimitType
from zxtg.core.kernel.manifest import LimitSpec, PluginManifest

logger = logging.getLogger("zxtg.services.limit")

PERIOD_REGEX = re.compile(r"^(\d+)\s*([smhdw])$", re.IGNORECASE)

UNIT_MULTIPLIERS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_period_to_seconds(period_str: str | None) -> int:
    """Parse period string like '1d', '2h', '30m', '60s' into seconds."""
    if not period_str:
        return 0
    match = PERIOD_REGEX.match(period_str.strip())
    if not match:
        try:
            return int(period_str)
        except ValueError:
            raise ValueError(f"Invalid period format: {period_str!r} (expected e.g. '1d', '2h', '30m', '60s')")
    val, unit = match.groups()
    return int(val) * UNIT_MULTIPLIERS[unit.lower()]


class LimitService:
    """Limiter management: CD, COUNT (with rolling period window), BLOCK (FR-LIM-01~06)."""

    def __init__(self) -> None:
        # cd_records: (plugin_key, watch_type, target_id) -> last_timestamp
        self._cd_records: dict[tuple[str, str, str], float] = {}
        # count_records: (plugin_key, watch_type, target_id) -> list[timestamp]
        self._count_records: dict[tuple[str, str, str], list[float]] = {}
        # block_records: (plugin_key, watch_type, target_id) -> bool
        self._block_records: dict[tuple[str, str, str], bool] = {}
        # registered limits by plugin: plugin_key -> list[LimitSpec]
        self._plugin_limits: dict[str, list[LimitSpec]] = {}

    def register_limit(self, plugin_key: str, spec: LimitSpec) -> None:
        """Register a LimitSpec for a plugin."""
        if plugin_key not in self._plugin_limits:
            self._plugin_limits[plugin_key] = []
        self._plugin_limits[plugin_key].append(spec)

    def set_block(
        self,
        plugin_key: str,
        watch_type: LimitWatchType,
        target_id: str,
        blocked: bool = True,
    ) -> None:
        """Set permanent block for a target."""
        self._block_records[(plugin_key, str(watch_type), str(target_id))] = blocked

    def _resolve_target_id(
        self,
        watch_type: LimitWatchType,
        user_id: str | int | None,
        group_id: str | int | None,
    ) -> str:
        if watch_type == LimitWatchType.USER:
            return str(user_id or "")
        if watch_type == LimitWatchType.GROUP:
            return str(group_id or "")
        return "GLOBAL"

    def _is_check_type_matching(
        self, check_type: LimitCheckType | BlockType, is_group: bool
    ) -> bool:
        check_val = str(check_type)
        if check_val == LimitCheckType.ALL or check_val == BlockType.ALL:
            return True
        if is_group:
            return check_val in (LimitCheckType.GROUP, BlockType.GROUP)
        return check_val in (LimitCheckType.PRIVATE, BlockType.PRIVATE)

    def check_limit(
        self,
        spec: LimitSpec,
        plugin_key: str,
        user_id: str | int | None,
        group_id: str | int | None = None,
        is_group: bool = False,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Check if a specific limit triggers. Returns (allowed, reason)."""
        if not spec.status:
            return True, ""

        if not self._is_check_type_matching(spec.check_type, is_group):
            return True, ""

        target_id = self._resolve_target_id(spec.watch_type, user_id, group_id)
        current_time = time.time() if now is None else now

        # 1. BLOCK check
        if spec.type == PluginLimitType.BLOCK:
            block_key = (plugin_key, str(spec.watch_type), target_id)
            is_blocked = self._block_records.get(block_key, True)  # If spec is BLOCK and active
            if is_blocked:
                msg = spec.result or "该功能已被禁用"
                return False, msg

        # 2. CD check
        elif spec.type == PluginLimitType.CD:
            cd_seconds = spec.cd or 0
            cd_key = (plugin_key, str(spec.watch_type), target_id)
            last_run = self._cd_records.get(cd_key)
            if last_run is not None:
                elapsed = current_time - last_run
                if elapsed < cd_seconds:
                    remaining = cd_seconds - elapsed
                    msg = spec.result or f"冷却中，请在 {int(remaining) + 1} 秒后再试"
                    return False, msg

        # 3. COUNT check (rolling window)
        elif spec.type == PluginLimitType.COUNT:
            period_seconds = parse_period_to_seconds(spec.period)
            max_count = spec.max_count or 1
            count_key = (plugin_key, str(spec.watch_type), target_id)
            timestamps = self._count_records.get(count_key, [])
            # Purge expired timestamps outside the rolling window
            valid_timestamps = [t for t in timestamps if current_time - t < period_seconds]
            self._count_records[count_key] = valid_timestamps
            if len(valid_timestamps) >= max_count:
                msg = spec.result or f"已达到使用次数上限（{spec.period} 内最多 {max_count} 次）"
                return False, msg

        return True, ""

    def record_usage(
        self,
        spec: LimitSpec,
        plugin_key: str,
        user_id: str | int | None,
        group_id: str | int | None = None,
        now: float | None = None,
    ) -> None:
        """Record limit usage after a successful call."""
        if not spec.status:
            return

        target_id = self._resolve_target_id(spec.watch_type, user_id, group_id)
        current_time = time.time() if now is None else now

        if spec.type == PluginLimitType.CD:
            cd_key = (plugin_key, str(spec.watch_type), target_id)
            self._cd_records[cd_key] = current_time

        elif spec.type == PluginLimitType.COUNT:
            count_key = (plugin_key, str(spec.watch_type), target_id)
            if count_key not in self._count_records:
                self._count_records[count_key] = []
            self._count_records[count_key].append(current_time)

    def check_all_and_record(
        self,
        manifest: PluginManifest,
        user_id: str | int | None,
        group_id: str | int | None = None,
        is_group: bool = False,
        is_superuser: bool = False,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Check all limits for a plugin. If all pass, record usage and return (True, '')."""
        # Superuser bypass check (Design §5.3: limit_superuser=False means superusers bypass)
        if is_superuser and not manifest.limit_superuser:
            return True, ""

        limits = list(manifest.limits) + self._plugin_limits.get(manifest.key, [])
        for spec in limits:
            allowed, reason = self.check_limit(
                spec=spec,
                plugin_key=manifest.key,
                user_id=user_id,
                group_id=group_id,
                is_group=is_group,
                now=now,
            )
            if not allowed:
                return False, reason

        # All passed, record usage
        for spec in limits:
            self.record_usage(
                spec=spec,
                plugin_key=manifest.key,
                user_id=user_id,
                group_id=group_id,
                now=now,
            )

        return True, ""

    def clear(self) -> None:
        """Reset service state for testing."""
        self._cd_records.clear()
        self._count_records.clear()
        self._block_records.clear()
        self._plugin_limits.clear()


limit_service = LimitService()
