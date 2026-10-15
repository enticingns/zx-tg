from tortoise import fields
from tortoise.models import Model


class GroupConsole(Model):
    """群聊控制台与信息表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    group_id = fields.CharField(max_length=255, unique=True, description="群聊ID")
    group_name = fields.TextField(default="", description="群聊名称")
    member_count = fields.IntField(default=0, description="当前成员数")
    max_member_count = fields.IntField(default=0, description="最大成员数")
    level = fields.IntField(default=5, description="群权限等级")
    status = fields.BooleanField(default=True, description="群启用状态")
    last_active = fields.DatetimeField(null=True, description="最后活跃时间")
    platform = fields.CharField(max_length=255, default="telegram", description="所属平台")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "group_console"
        table_description = "群聊控制台"
        indexes = [("group_id",), ("status",)]
