from enum import StrEnum


class PluginType(StrEnum):
    """插件类型 (逐字继承上游 zhenxun/utils/enum.py)"""

    SUPERUSER = "SUPERUSER"
    """超级用户"""
    ADMIN = "ADMIN"
    """管理员"""
    SUPER_AND_ADMIN = "ADMIN_SUPER"
    """管理员以及超级用户"""
    NORMAL = "NORMAL"
    """普通插件"""
    DEPENDANT = "DEPENDANT"
    """依赖插件，一般为没有主动触发命令的插件，受权限控制"""
    HIDDEN = "HIDDEN"
    """隐藏插件，一般为没有主动触发命令的插件，不受权限控制，如消息统计"""
    PARENT = "PARENT"
    """父插件，仅仅标记"""


class BlockType(StrEnum):
    """禁用状态 (逐字继承上游 zhenxun/utils/enum.py)"""

    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    ALL = "ALL"


class PluginLimitType(StrEnum):
    """插件限制类型 (逐字继承上游 zhenxun/utils/enum.py)"""

    CD = "CD"
    COUNT = "COUNT"
    BLOCK = "BLOCK"


class LimitCheckType(StrEnum):
    """插件限制检查类型 (逐字继承上游 zhenxun/utils/enum.py)"""

    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    ALL = "ALL"


class LimitWatchType(StrEnum):
    """插件限制监听对象 (逐字继承上游 zhenxun/utils/enum.py)"""

    USER = "USER"
    GROUP = "GROUP"
    ALL = "ALL"
