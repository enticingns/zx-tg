from tortoise import fields
from tortoise.models import Model


class Statistics(Model):
    """插件调用统计表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    plugin_key = fields.CharField(max_length=255, description="插件标识")
    user_id = fields.CharField(max_length=255, description="用户ID")
    group_id = fields.CharField(max_length=255, null=True, description="群聊ID")
    count = fields.IntField(default=1, description="调用次数")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    @property
    def plugin_name(self) -> str:
        return self.plugin_key

    class Meta:
        table = "statistics"
        table_description = "插件调用统计"
        indexes = [
            ("plugin_key",),
            ("user_id", "plugin_key"),
            ("group_id", "plugin_key"),
            ("create_time",),
        ]
