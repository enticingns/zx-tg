import logging
from typing import Any

from tortoise.expressions import F
from tortoise.transactions import in_transaction

from zxtg.models.logs import UserGoldLog
from zxtg.models.user_console import UserConsole

logger = logging.getLogger("zxtg.services.gold")


class GoldService:
    """Gold economy service with atomic balance modification and audit logging (FR-SVC-02, FR-SVC-05)."""

    async def get_gold(self, user_id: str | int) -> int:
        """Fetch current gold balance."""
        user = await UserConsole.get_or_none(user_id=str(user_id))
        return user.gold if user else 0

    async def change_gold(
        self,
        user_id: str | int,
        amount: int,
        reason: str = "",
    ) -> tuple[bool, str]:
        """Atomically change gold balance and record audit log.

        - amount > 0: increase balance.
        - amount < 0: atomically deduct balance if sufficient (no overdraft, no partial deduct).
        - amount == 0: no-op.

        Returns (success: bool, msg: str).
        """
        uid = str(user_id)
        if amount == 0:
            return True, "ok"

        async with in_transaction():
            user = await UserConsole.get_or_none(user_id=uid)
            if user is None:
                return False, "用户不存在"

            if amount < 0:
                cost = -amount
                # Atomic deduction: filter gold__gte=cost to prevent race conditions & overdraft
                updated_count = await UserConsole.filter(user_id=uid, gold__gte=cost).update(
                    gold=F("gold") - cost
                )
                if updated_count == 0:
                    return False, f"金币不足 (需要 {cost}，当前拥有 {user.gold})"

                await UserGoldLog.create(
                    user_id=uid,
                    amount=amount,
                    reason=reason,
                )
                return True, "ok"

            else:
                # Adding gold
                await UserConsole.filter(user_id=uid).update(gold=F("gold") + amount)
                await UserGoldLog.create(
                    user_id=uid,
                    amount=amount,
                    reason=reason,
                )
                return True, "ok"

    async def get_logs(self, user_id: str | int, limit: int = 50) -> list[UserGoldLog]:
        """Fetch recent gold logs for a user."""
        return await UserGoldLog.filter(user_id=str(user_id)).order_by("-create_time").limit(limit)


gold_service = GoldService()
