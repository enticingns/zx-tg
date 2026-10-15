from tortoise import fields
from tortoise.models import Model


class UserConsole(Model):
    """用户控制台与信息表 (SRS v1.0 §8)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=255, unique=True, description="用户唯一ID")
    username = fields.CharField(max_length=255, null=True, description="用户名")
    full_name = fields.CharField(max_length=255, default="", description="用户全名")
    gold = fields.IntField(default=100, description="金币数量")
    impression = fields.FloatField(default=0.0, description="好感度")
    platform = fields.CharField(max_length=255, default="telegram", description="所属平台")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "user_console"
        table_description = "用户控制台"
        indexes = [("user_id",)]
