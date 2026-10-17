import logging
from typing import Any

from tortoise.expressions import F
from tortoise.transactions import in_transaction

from zxtg.models.logs import UserImpressionLog
from zxtg.models.user_console import UserConsole

logger = logging.getLogger("zxtg.services.impression")


class ImpressionService:
    """Impression service with atomic balance modification and audit logging (FR-SVC-03, FR-SVC-05)."""

    async def get_impression(self, user_id: str | int) -> float:
        """Fetch current impression balance."""
        user = await UserConsole.get_or_none(user_id=str(user_id))
        return user.impression if user else 0.0

    async def change_impression(
        self,
        user_id: str | int,
        amount: float,
        reason: str = "",
    ) -> tuple[bool, str]:
        """Atomically change impression balance and record audit log.

        - amount > 0: increase balance.
        - amount < 0: atomically deduct balance if sufficient (no overdraft, no partial deduct).
        - amount == 0: no-op.

        Returns (success: bool, msg: str).
        """
        uid = str(user_id)
        if amount == 0.0:
            return True, "ok"

        async with in_transaction():
            user = await UserConsole.get_or_none(user_id=uid)
            if user is None:
                return False, "用户不存在"

            if amount < 0:
                cost = -amount
                # Atomic deduction: filter impression__gte=cost to prevent race conditions & overdraft
                updated_count = await UserConsole.filter(
                    user_id=uid, impression__gte=cost
                ).update(impression=F("impression") - cost)
                if updated_count == 0:
                    return False, f"好感度不足 (需要 {cost:.1f}，当前拥有 {user.impression:.1f})"

                await UserImpressionLog.create(
                    user_id=uid,
                    amount=amount,
                    reason=reason,
                )
                return True, "ok"

            else:
                # Adding impression
                await UserConsole.filter(user_id=uid).update(
                    impression=F("impression") + amount
                )
                await UserImpressionLog.create(
                    user_id=uid,
                    amount=amount,
                    reason=reason,
                )
                return True, "ok"

    async def get_logs(self, user_id: str | int, limit: int = 50) -> list[UserImpressionLog]:
        """Fetch recent impression logs for a user."""
        return await UserImpressionLog.filter(user_id=str(user_id)).order_by("-create_time").limit(limit)


impression_service = ImpressionService()
