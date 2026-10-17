from zxtg.models.config import CoreConfig
from zxtg.models.group_console import GroupConsole
from zxtg.models.join_request import FGRequest, JoinRequest
from zxtg.models.item import UserItem
from zxtg.models.logs import UserGoldLog, UserImpressionLog
from zxtg.models.migration_record import MigrationRecord
from zxtg.models.plugin_info import PluginInfo
from zxtg.models.plugin_limit import PluginLimit
from zxtg.models.statistics import Statistics
from zxtg.models.switch import GroupPluginSwitch
from zxtg.models.task_record import TaskRecord
from zxtg.models.user_console import UserConsole

__all__ = [
    "CoreConfig",
    "FGRequest",
    "GroupConsole",
    "GroupPluginSwitch",
    "JoinRequest",
    "MigrationRecord",
    "PluginInfo",
    "PluginLimit",
    "Statistics",
    "TaskRecord",
    "UserConsole",
    "UserGoldLog",
    "UserImpressionLog",
    "UserItem",
]
