from tortoise import fields
from tortoise.models import Model


class UserItem(Model):
    """用户道具持有记录表 (FR-SVC-06)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=255, description="用户ID")
    item_id = fields.CharField(max_length=255, description="道具标识")
    count = fields.IntField(default=1, description="持有数量")
    expire_at = fields.DatetimeField(null=True, description="过期时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="获得时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "user_item"
        table_description = "用户道具表"
        indexes = [
            ("user_id",),
            ("user_id", "item_id"),
        ]
