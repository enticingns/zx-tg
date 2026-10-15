from tortoise import fields
from tortoise.models import Model


class JoinRequest(Model):
    """加群/入群请求记录表 (SRS v1.0 §8, 对应上游 fg_request)"""

    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    request_id = fields.CharField(max_length=255, unique=True, description="请求ID")
    user_id = fields.CharField(max_length=255, description="用户ID")
    group_id = fields.CharField(max_length=255, null=True, description="群聊ID")
    type = fields.CharField(max_length=32, default="GROUP", description="请求类型")
    handle_type = fields.CharField(max_length=32, default="PENDING", description="处理状态")
    platform = fields.CharField(max_length=255, default="telegram", description="所属平台")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "join_request"
        table_description = "入群请求记录"
        indexes = [("request_id",), ("user_id",), ("group_id",)]


# Alias for upstream compatibility
FGRequest = JoinRequest
