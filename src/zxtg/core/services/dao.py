import logging
from typing import Any

from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.impression_service import impression_service
from zxtg.core.services.item_service import item_service
from zxtg.core.services.statistics_service import statistics_service
from zxtg.core.services.user_service import user_service

logger = logging.getLogger("zxtg.services.dao")


class RawSQLError(PermissionError):
    """Raised when an attempt to execute raw SQL from plugins or outside DAO is detected (FR-DATA-04)."""


class BaseDAO:
    """Standard Data Access Object (DAO) providing safe, high-level data access without raw SQL (FR-DATA-04)."""

    def __init__(self, plugin_key: str = "") -> None:
        self.plugin_key = plugin_key

    def execute_raw_sql(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        """Explicitly rejected method to intercept and block raw SQL access attempts."""
        raise RawSQLError(
            f"Direct raw SQL execution is strictly forbidden in plugin layer (FR-DATA-04). "
            f"Attempted query: {sql[:100]!r}"
        )

    # High-level whitelisted DAO interfaces
    async def get_user_gold(self, user_id: str | int) -> int:
        return await gold_service.get_gold(user_id)

    async def change_user_gold(self, user_id: str | int, amount: int, reason: str = "") -> tuple[bool, str]:
        return await gold_service.change_gold(user_id, amount, reason or f"dao_{self.plugin_key}")

    async def get_user_impression(self, user_id: str | int) -> float:
        return await impression_service.get_impression(user_id)

    async def change_user_impression(self, user_id: str | int, amount: float, reason: str = "") -> tuple[bool, str]:
        return await impression_service.change_impression(user_id, amount, reason or f"dao_{self.plugin_key}")

    async def record_stat(self, user_id: str | int, group_id: str | int | None = None, count: int = 1) -> None:
        statistics_service.record_call(self.plugin_key, user_id, group_id, count)


def get_plugin_dao(plugin_key: str = "") -> BaseDAO:
    """Factory function for retrieving a DAO instance for a plugin."""
    return BaseDAO(plugin_key=plugin_key)
