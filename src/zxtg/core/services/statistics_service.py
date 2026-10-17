import collections
import logging
from typing import Any

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from zxtg.models.statistics import Statistics

logger = logging.getLogger("zxtg.services.statistics")


class StatisticsService:
    """Statistics service with in-memory buffering and batch flushing (FR-DATA-03)."""

    def __init__(self) -> None:
        # Buffer: (plugin_key, user_id, group_id) -> count
        self._buffer: dict[tuple[str, str, str | None], int] = collections.defaultdict(int)
        self._db_write_count: int = 0  # Instrumentation counter to assert 0 DB writes on buffer writes

    @property
    def db_write_count(self) -> int:
        return self._db_write_count

    def record_call(
        self,
        plugin_key: str,
        user_id: str | int,
        group_id: str | int | None = None,
        count: int = 1,
    ) -> None:
        """Buffer a call count in memory without performing database writes (FR-DATA-03)."""
        uid = str(user_id)
        gid = str(group_id) if group_id is not None else None
        key = (plugin_key, uid, gid)
        self._buffer[key] += count

    def get_buffered_count(
        self,
        plugin_key: str,
        user_id: str | int,
        group_id: str | int | None = None,
    ) -> int:
        """Return the count currently held in memory buffer."""
        uid = str(user_id)
        gid = str(group_id) if group_id is not None else None
        return self._buffer.get((plugin_key, uid, gid), 0)

    async def flush(self) -> int:
        """Flush in-memory buffered counts to database in batch (FR-DATA-03).

        Returns the number of distinct (plugin, user, group) entries written.
        """
        if not self._buffer:
            return 0

        if not Tortoise._inited:
            logger.debug("Database not initialized, skip statistics flush")
            return 0

        # Snapshot and clear buffer
        items = list(self._buffer.items())
        self._buffer.clear()

        flushed = 0
        async with in_transaction():
            for (plugin_key, user_id, group_id), count in items:
                stat = await Statistics.get_or_none(
                    plugin_key=plugin_key,
                    user_id=user_id,
                    group_id=group_id,
                )
                if stat:
                    stat.count += count
                    await stat.save(update_fields=["count"])
                else:
                    await Statistics.create(
                        plugin_key=plugin_key,
                        user_id=user_id,
                        group_id=group_id,
                        count=count,
                    )
                self._db_write_count += 1
                flushed += 1

        logger.debug("Flushed %d statistics records to database", flushed)
        return flushed

    async def get_total_count(
        self,
        plugin_key: str,
        user_id: str | int,
        group_id: str | int | None = None,
    ) -> int:
        """Get aggregate count from database + memory buffer."""
        buffered = self.get_buffered_count(plugin_key, user_id, group_id)
        db_count = 0
        if Tortoise._inited:
            uid = str(user_id)
            gid = str(group_id) if group_id is not None else None
            stat = await Statistics.get_or_none(
                plugin_key=plugin_key,
                user_id=uid,
                group_id=gid,
            )
            if stat:
                db_count = stat.count
        return db_count + buffered

    def clear(self) -> None:
        """Reset memory buffer and counters for testing."""
        self._buffer.clear()
        self._db_write_count = 0


statistics_service = StatisticsService()
