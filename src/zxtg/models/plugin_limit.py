from tortoise import fields
from tortoise.models import Model

from zxtg.core.kernel.enums import LimitCheckType, LimitWatchType, PluginLimitType


class PluginLimit(Model):
    """插件限制表 (继承自上游 plugin_limit 并补充显式周期 period 与 target_id)"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    module = fields.CharField(max_length=255, description="模块名")
    module_path = fields.CharField(max_length=255, null=True, description="模块路径")
    plugin = fields.ForeignKeyField(
        "models.PluginInfo",
        related_name="plugin_limit",
        on_delete=fields.CASCADE,
        description="所属插件",
    )
    limit_type = fields.CharEnumField(PluginLimitType, description="限制类型")
    watch_type = fields.CharEnumField(LimitWatchType, description="监听类型")
    status = fields.BooleanField(default=True, description="限制开关状态")
    check_type = fields.CharEnumField(
        LimitCheckType, default=LimitCheckType.ALL, description="检查类型"
    )
    result = fields.CharField(max_length=255, null=True, description="拒绝时返回信息")
    cd = fields.IntField(null=True, description="冷却时间(秒)")
    max_count = fields.IntField(null=True, description="周期内最大调用次数")
    period = fields.CharField(max_length=32, null=True, description="计数周期(如1d/1h)")
    target_id = fields.CharField(max_length=255, null=True, description="限制目标标识")

    class Meta:
        table = "plugin_limit"
        table_description = "插件限制"
        indexes = [("module", "status")]
