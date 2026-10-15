from tortoise import fields
from tortoise.models import Model


class TaskRecord(Model):
    """被动技能/定时任务群级记录表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    task_key = fields.CharField(max_length=255, description="被动任务标识")
    group_id = fields.CharField(max_length=255, description="群组ID")
    status = fields.BooleanField(default=True, description="任务开启状态")
    last_run = fields.DatetimeField(null=True, description="上次运行时间")
    updated_at = fields.DatetimeField(auto_now=True, description="最后更新时间")

    class Meta:
        table = "task_record"
        table_description = "被动任务记录"
        unique_together = ("task_key", "group_id")
        indexes = [("task_key",), ("group_id",)]
