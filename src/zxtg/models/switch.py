from tortoise import fields
from tortoise.models import Model


class GroupPluginSwitch(Model):
    """群级插件开关表 (SRS v1.0 §8, FR-PLG-08)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    group_id = fields.CharField(max_length=255, description="群组ID")
    plugin_key = fields.CharField(max_length=255, description="插件标识")
    status = fields.BooleanField(default=True, description="群内开关状态")
    updated_at = fields.DatetimeField(auto_now=True, description="最后更新时间")

    class Meta:
        table = "group_plugin_switch"
        table_description = "群级插件开关"
        unique_together = ("group_id", "plugin_key")
        indexes = [("group_id",), ("plugin_key",)]
