from tortoise import fields
from tortoise.models import Model


class MigrationRecord(Model):
    """插件/核心迁移版本记录表 (SRS v1.0 §8, FR-PLG-10)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    plugin_key = fields.CharField(max_length=255, description="插件标识(核心用core)")
    version = fields.CharField(max_length=64, description="迁移版本")
    applied_time = fields.DatetimeField(auto_now_add=True, description="执行时间")

    class Meta:
        table = "migration_record"
        table_description = "迁移记录"
        unique_together = ("plugin_key", "version")
        indexes = [("plugin_key",)]
