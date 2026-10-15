from typing import TYPE_CHECKING
from tortoise import fields
from tortoise.models import Model

from zxtg.core.kernel.enums import BlockType, PluginType

if TYPE_CHECKING:
    from zxtg.models.plugin_limit import PluginLimit


class PluginInfo(Model):
    """插件主表 (26 字段，字段名逐字继承自上游模型与契约)"""

    # 1. 主键自增 id
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    # 2. 模块名
    module = fields.CharField(max_length=255, description="模块名")
    # 3. 模块路径
    module_path = fields.CharField(max_length=255, unique=True, description="模块路径")
    # 4. 插件名称
    name = fields.CharField(max_length=255, description="插件名称")
    # 5. 全局开关状态
    status = fields.BooleanField(default=True, description="全局开关状态")
    # 6. 禁用类型
    block_type: BlockType | None = fields.CharEnumField(
        BlockType, default=None, null=True, description="禁用类型"
    )
    # 7. 加载状态
    load_status = fields.BooleanField(default=True, description="加载状态")
    # 8. 作者
    author = fields.CharField(max_length=255, null=True, description="作者")
    # 9. 版本
    version = fields.CharField(max_length=255, null=True, description="版本")
    # 10. 所需群权限
    level = fields.IntField(default=5, description="所需群权限")
    # 11. 进群默认开关状态
    default_status = fields.BooleanField(default=True, description="进群默认开关状态")
    # 12. 是否限制超级用户
    limit_superuser = fields.BooleanField(default=False, description="是否限制超级用户")
    # 13. 菜单类型
    menu_type = fields.CharField(max_length=255, default="", description="菜单类型")
    # 14. 插件类型
    plugin_type = fields.CharEnumField(PluginType, null=True, description="插件类型")
    # 15. 调用插件所需金币
    cost_gold = fields.IntField(default=0, description="调用插件所需金币")
    # 16. 调用所需权限等级
    admin_level = fields.IntField(default=0, null=True, description="调用所需权限等级")
    # 17. 是否忽略阻断提示
    ignore_prompt = fields.BooleanField(default=False, description="是否忽略提示")
    # 18. 是否删除
    is_delete = fields.BooleanField(default=False, description="是否删除")
    # 19. 父插件
    parent = fields.CharField(max_length=255, null=True, description="父插件")
    # 20. 是否显示在帮助中
    is_show = fields.BooleanField(default=True, description="是否显示在帮助中")
    # 21. 是否不统计调用次数
    ignore_statistics = fields.BooleanField(default=False, description="是否不统计调用次数")
    # 22. 插件好感度限制
    impression = fields.FloatField(default=0.0, description="插件好感度限制")
    # 23. 反向关联插件限制
    plugin_limit: fields.ReverseRelation["PluginLimit"]
    # 24. 插件描述 (上游 PluginMetadata / PluginExtraData 字段)
    description = fields.TextField(null=True, description="插件描述")
    # 25. 插件使用说明 (上游 PluginMetadata / PluginExtraData 字段)
    usage = fields.TextField(null=True, description="插件使用说明")
    # 26. 超级用户帮助说明 (上游 PluginExtraData 字段)
    superuser_help = fields.TextField(null=True, description="超级用户帮助")

    class Meta:
        table = "plugin_info"
        table_description = "插件基本信息"
        indexes = [("module",), ("module_path",)]
