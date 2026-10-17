from tortoise import fields
from tortoise.models import Model


class CoreConfig(Model):
    """全局持久化配置表 (FR-CFG-01, Design §5.6)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    key = fields.CharField(max_length=64, unique=True, db_index=True, description="配置项键名")
    value_json = fields.TextField(description="配置项JSON序列化值")
    plugin_key = fields.CharField(max_length=64, null=True, description="所属插件标识")
    scope = fields.CharField(max_length=32, default="global", description="配置作用域")
    updated_at = fields.DatetimeField(auto_now=True, description="最后更新时间")

    class Meta:
        table = "core_config"
        table_description = "全局持久化配置"
