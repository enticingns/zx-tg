import datetime
import logging
from typing import Any

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from zxtg.models.item import UserItem

logger = logging.getLogger("zxtg.services.item")


class ItemService:
    """Item service supporting holding, usage, and expiration (FR-SVC-06)."""

    async def add_item(
        self,
        user_id: str | int,
        item_id: str,
        count: int = 1,
        expire_at: datetime.datetime | None = None,
    ) -> UserItem:
        """Add item(s) to a user's inventory."""
        uid = str(user_id)
        if count <= 0:
            raise ValueError(f"count must be positive, got {count}")

        # If item with same expiration exists, increment count; else create new entry
        item = await UserItem.filter(user_id=uid, item_id=item_id, expire_at=expire_at).first()
        if item:
            item.count += count
            await item.save(update_fields=["count", "updated_at"])
            return item

        return await UserItem.create(
            user_id=uid,
            item_id=item_id,
            count=count,
            expire_at=expire_at,
        )

    async def get_items(
        self,
        user_id: str | int,
        include_expired: bool = False,
    ) -> list[UserItem]:
        """Get list of items owned by user."""
        uid = str(user_id)
        query = UserItem.filter(user_id=uid, count__gt=0)
        items = await query.all()
        now = datetime.datetime.now(datetime.timezone.utc)
        if not include_expired:
            items = [item for item in items if item.expire_at is None or item.expire_at > now]
        return items

    async def has_item(self, user_id: str | int, item_id: str, min_count: int = 1) -> bool:
        """Check if user has at least min_count unexpired instances of item."""
        items = await self.get_items(user_id, include_expired=False)
        total = sum(i.count for i in items if i.item_id == item_id)
        return total >= min_count

    async def use_item(
        self,
        user_id: str | int,
        item_id: str,
        count: int = 1,
    ) -> tuple[bool, str]:
        """Use/consume item(s) from user's inventory. Expired items cannot be used."""
        uid = str(user_id)
        if count <= 0:
            return False, "使用数量必须大于0"

        now = datetime.datetime.now(datetime.timezone.utc)
        async with in_transaction():
            all_items = await UserItem.filter(user_id=uid, item_id=item_id, count__gt=0).all()
            valid_items = [i for i in all_items if i.expire_at is None or i.expire_at > now]

            total_available = sum(i.count for i in valid_items)
            if total_available < count:
                return False, f"道具数量不足 (需要 {count}，当前可用 {total_available})"

            # Sort items with expire_at first, then permanent items
            valid_items.sort(
                key=lambda i: (
                    0 if i.expire_at else 1,
                    i.expire_at or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
                )
            )

            remaining_to_deduct = count
            for item in valid_items:
                if remaining_to_deduct <= 0:
                    break
                deduct = min(item.count, remaining_to_deduct)
                item.count -= deduct
                remaining_to_deduct -= deduct
                await item.save(update_fields=["count", "updated_at"])

            return True, "使用成功"

    async def clean_expired_items(self) -> int:
        """Purge expired items."""
        now = datetime.datetime.now(datetime.timezone.utc)
        expired = await UserItem.filter(expire_at__lt=now).delete()
        return expired


item_service = ItemService()
