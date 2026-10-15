from tortoise import fields
from tortoise.models import Model


class UserGoldLog(Model):
    """用户金币流水日志表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=255, description="用户ID")
    amount = fields.IntField(default=0, description="金币变动数值")
    reason = fields.CharField(max_length=255, default="", description="变动原因或来源模块")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    @property
    def gold(self) -> int:
        return self.amount

    @property
    def source(self) -> str:
        return self.reason

    class Meta:
        table = "user_gold_log"
        table_description = "用户金币记录表"
        indexes = [
            ("user_id",),
            ("user_id", "create_time"),
        ]


class UserImpressionLog(Model):
    """用户好感度流水日志表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=255, description="用户ID")
    amount = fields.FloatField(default=0.0, description="好感度变动数值")
    reason = fields.CharField(max_length=255, default="", description="变动原因或来源模块")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "user_impression_log"
        table_description = "用户好感度记录表"
        indexes = [
            ("user_id",),
            ("user_id", "create_time"),
        ]
