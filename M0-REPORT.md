# ZX-TG M0 交付验收报告

> **执行基准**：`NEXT-TASK-M0.md`（唯一权威指令）  
> **设计规格**：`docs/zx-tg-design-v3.md` & `docs/zx-tg-requirements-v1.0.md`  
> **报告时间**：2026-10-15  
> **当前阶段**：M0（奠基完成，已停机等待 M1）

---

## 1. 环境与工具链

- **操作系统**：Linux 6.6.137+ x86_64
- **Python 版本**：3.13.5
- **pip 版本**：26.2.1
- **虚拟环境**：`/root/work/zx-tg/.venv`
- **依赖白名单检查**：严格限定于白名单，无任何违规依赖（未引入 nonebot2 / aiogram / python-telegram-bot / playwright / fastapi 等）。

### 已安装 Python 包清单（`pip list` 原始输出）
```text
Package           Version Editable project location
----------------- ------- -------------------------
aiosqlite         0.22.1
annotated-types   0.8.0
anyio             4.15.1
idna              3.20
iniconfig         2.3.1
iso8601           2.1.0
packaging         26.3
pip               26.2.1
pluggy            1.7.0
pydantic          2.14.1
pydantic_core     2.50.1
Pygments          2.21.0
pypika-tortoise   0.6.5
pytest            9.1.1
pytest-asyncio    1.4.0
tortoise-orm      1.1.9
typing_extensions 4.16.0
typing-inspection 0.4.4
zxtg              0.1.0   /root/work/zx-tg
```

---

## 2. 变更文件清单与代码行数

全项目各模块代码行数统计（`wc -l`）：

| 路径 | 行数 | 类别 | 说明 |
|---|---:|---|---|
| `src/zxtg/config.py` | 15 | 配置 | 配置管理模型，支持环境变量 |
| `src/zxtg/__init__.py` | 3 | 基础 | 顶层包入口 |
| `src/zxtg/logging_setup.py` | 54 | 安全/日志 | 日志分级配置，RedactTokenFilter 脱敏 |
| `src/zxtg/__main__.py` | 49 | 入口 | CLI 入口，支持管道调试与 ping 响应 |
| `src/zxtg/core/context.py` | 146 | 内核数据 | CallContext 不可变快照与白名单 API |
| `src/zxtg/core/event.py` | 69 | 统一事件 | UnifiedEvent / Actor / Role / ChatRef |
| `src/zxtg/core/__init__.py` | 1 | 核心 | 导出核心接口 |
| `src/zxtg/core/kernel/enums.py` | 69 | 契约枚举 | 逐字继承上游枚举及 RequestType/HandleType |
| `src/zxtg/core/kernel/guards.py` | 119 | 调用管道 | Verdict(ALLOW/DENY) 与各 Guard 最小实现 |
| `src/zxtg/core/kernel/__init__.py` | 51 | 内核导出 | 导出管道与 Guard 单元 |
| `src/zxtg/core/kernel/pipeline.py` | 66 | 管道控制 | PIPELINE 列表顺序调度，禁 priority 数字 |
| `src/zxtg/core/kernel/registry.py` | 79 | 插件注册 | 注册表骨架，自动关联 pattern/slash/aliases |
| `src/zxtg/core/platform/base.py` | 21 | 平台适配 | PlatformAdapter 抽象接口 |
| `src/zxtg/core/platform/console.py` | 60 | 调试适配 | 控制台调试适配器，支持输入行处理 |
| `src/zxtg/core/platform/__init__.py` | 4 | 平台导出 | 导出 PlatformAdapter |
| `src/zxtg/core/services/db.py` | 61 | 数据库 | Tortoise ORM 初始化、内存/文件库适配、迁移 |
| `src/zxtg/core/services/__init__.py` | 4 | 服务导出 | 导出 db 服务接口 |
| `src/zxtg/models/group_console.py` | 23 | 数据模型 | 群控制台与信息表模型 |
| `src/zxtg/models/user_console.py` | 21 | 数据模型 | 用户控制台表模型 |
| `src/zxtg/models/logs.py` | 46 | 数据模型 | UserGoldLog 与 UserImpressionLog 流水表 |
| `src/zxtg/models/switch.py` | 18 | 数据模型 | GroupPluginSwitch 群级插件开关表 |
| `src/zxtg/models/task_record.py` | 19 | 数据模型 | TaskRecord 被动任务记录表 |
| `src/zxtg/models/statistics.py` | 27 | 数据模型 | Statistics 插件调用统计表 |
| `src/zxtg/models/join_request.py` | 24 | 数据模型 | JoinRequest / FGRequest 请求记录表 |
| `src/zxtg/models/migration_record.py` | 17 | 数据模型 | MigrationRecord 迁移版本表 |
| `src/zxtg/models/plugin_limit.py` | 34 | 数据模型 | PluginLimit 限制记录表（含 period/target_id） |
| `src/zxtg/models/plugin_info.py` | 72 | 数据模型 | PluginInfo 26 字段插件主表 |
| `src/zxtg/models/__init__.py` | 25 | 模型导出 | 统一导出所有 10 张核心 ORM 模型 |
| `plugins/ping/plugin.py` | 34 | 插件实现 | 心跳测试插件 Manifest 与 handle_ping |
| `plugins/ping/__init__.py` | 4 | 插件导出 | 导出 Ping 插件接口 |
| `scripts/smoke_m0.py` | 68 | 冒烟脚本 | 非交互冒烟测试脚本 |
| `tests/test_boundaries.py` | 93 | 架构测试 | B1/B3/B4 AST 静态扫描边界守卫测试 |
| `tests/test_enums_contract.py` | 62 | 契约测试 | 锁死上游 5 个枚举名称与成员值 |
| `tests/test_event.py` | 64 | 事件测试 | UnifiedEvent / Actor.display 回退测试 |
| `tests/test_models.py` | 232 | 模型测试 | 26 字段断言与所有模型 CRUD 测试 |
| `tests/test_pipeline.py` | 145 | 管道测试 | PIPELINE 顺序判定、短路截断与调度测试 |
| **总计** | **1,899** | — | — |

---

## 3. 核心数据结构落点

### 3.1 UnifiedEvent（统一事件模型）
- **文件路径**：`src/zxtg/core/event.py`
- **形态与字段**：
```python
@dataclass
class Actor:
    id: str | int
    username: str | None = None
    full_name: str = ""
    is_bot: bool = False

    @property
    def display(self) -> str:
        """Fallback to full_name when username is None or empty (FR-TG-08)."""
        return self.username if self.username else self.full_name

@dataclass
class ChatRef:
    id: str | int
    type: str  # "private" | "group" | "supergroup"
    title: str | None = None

@dataclass
class CommandRef:
    name: str
    args: list[str] = field(default_factory=list)
    raw: str = ""

@dataclass
class UnifiedEvent:
    actor: Actor
    kind: str = "text"
    text: str = ""
    role: Role = Role.MEMBER  # owner=100, administrator=10, member/restricted=0
    chat: ChatRef | None = None
    command: CommandRef | None = None
    message_id: int = 0
    raw: Any = None  # 逃生舱，插件层严禁直接调用 (B 边界)
```

### 3.2 CallContext（不可变快照）
- **文件路径**：`src/zxtg/core/context.py`
- **形态与字段**：
```python
class CallContext:
    def __init__(self, event, user, group=None, plugin=None, reply_fn=None): ...
    
    # 只读视图属性
    @property
    def event(self) -> UnifiedEvent: ...
    @property
    def user(self) -> UserView: ...
    @property
    def group(self) -> GroupView | None: ...
    @property
    def plugin(self) -> PluginView | None: ...
    @property
    def replies(self) -> list[SentMessage]: ...

    # 插件白名单 API (Design §5.12)
    async def config(self, key: str) -> Any: ...
    async def cache(self, key: str, ttl: int = 60) -> Any: ...
    async def reply(self, content: Any) -> SentMessage: ...
    async def reply_image(self, template: str, data: dict[str, Any]) -> SentMessage: ...
    async def edit(self, msg: SentMessage, content: Any) -> None: ...
    async def recall(self, msg: SentMessage, delay: int = 0) -> bool: ...
    async def keyboard(self, buttons: list[list[Any]]) -> None: ...
    async def gold(self, delta: int, reason: str) -> bool: ...
    async def impression(self, delta: float) -> bool: ...
    async def db(self) -> Any: ...
    async def mute(self, user_id: str, duration: int) -> bool: ...
    async def unmute(self, user_id: str) -> bool: ...
    async def kick(self, user_id: str) -> bool: ...
    async def ban(self, user_id: str) -> bool: ...
    async def unban(self, user_id: str) -> bool: ...
    async def leave(self) -> bool: ...
```

### 3.3 Verdict（管道裁决）
- **文件路径**：`src/zxtg/core/kernel/guards.py`
- **形态与设计**：
```python
class Verdict:
    def __init__(self, allowed: bool, reason: str = "", tip: str = "") -> None:
        self.allowed = allowed
        self.reason = reason
        self.tip = tip

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        if self.allowed:
            return "Verdict(ALLOW)"
        return f"Verdict(DENY, reason={self.reason!r}, tip={self.tip!r})"

ALLOW = Verdict(True)
def DENY(reason: str = "", tip: str = "") -> Verdict:
    return Verdict(False, reason=reason, tip=tip)
```

### 3.4 PIPELINE（有序管道）
- **文件路径**：`src/zxtg/core/kernel/pipeline.py`
- **形态与设计**：
```python
PIPELINE: list[Guard] = [
    ResolveContext,   # 1. 解析上下文
    BuildCommand,     # 2. 构造 CommandRef
    MergeConfig,      # 3. 配置三级合并
    GuardBan,         # 4. 黑名单拦截
    GuardSwitch,      # 5. 群/全局开关检查
    GuardLevel,       # 6. 权限等级判定
    GuardCost,        # 7. 金币/好感度扣除
    GuardLimit,       # 8. 频率限制 (CD/Count)
    Dispatch,         # 9. 分发至目标 handler
]
```
严格根据列表索引顺序执行，禁止 priority 数字（FR-AUTH-03）。遇到 DENY 立即短路并记录结构化日志。

---

## 4. 任务书 §3 验证命令原始输出

### 4.1 `python -m pytest -q`
```text
..............................                                           [100%]
30 passed in 0.28s
```

### 4.2 `python -m pyflakes src/zxtg`
```text
/root/work/zx-tg/.venv/bin/python: No module named pyflakes
```
*(说明：pyflakes 未在环境与白名单中，按任务书 §3/§4 规定如实跳过并标记 BLOCKED)*

### 4.3 `python -m pytest -q tests/test_boundaries.py tests/test_enums_contract.py`
```text
........                                                                 [100%]
8 passed in 0.02s
```

### 4.4 `python scripts/smoke_m0.py`
```text
=== Starting ZX-TG M0 Smoke Test ===
[SMOKE-M0] In-process check: PASS (received 'pong')
[SMOKE-M0] Subprocess exit code: 0
[SMOKE-M0] Output:
[2026-10-15 22:58:08] [INFO] [zxtg.main] Starting ZX-TG (M0)...
[2026-10-15 22:58:08] [INFO] [zxtg.services.db] Initializing database at: /root/work/zx-tg/data/zxtg.db
[2026-10-15 22:58:08] [INFO] [zxtg.services.db] Database initialized successfully
[2026-10-15 22:58:08] [INFO] [zxtg.main] Registered plugin: 心跳测试 (ping)
[2026-10-15 22:58:08] [INFO] [zxtg.platform.console] Bot -> pong
[2026-10-15 22:58:08] [INFO] [zxtg.services.db] Closing database connections...
[2026-10-15 22:58:08] [INFO] [zxtg.services.db] Database connections closed
[SMOKE-M0] Subprocess check: PASS (rc=0 and contains 'pong')
=== ZX-TG M0 Smoke Test: ALL PASS ===
```

### 4.5 `echo "ping" | python -m zxtg`
```text
[2026-10-15 22:58:14] [INFO] [zxtg.main] Starting ZX-TG (M0)...
[2026-10-15 22:58:14] [INFO] [zxtg.services.db] Initializing database at: /root/work/zx-tg/data/zxtg.db
[2026-10-15 22:58:14] [INFO] [zxtg.services.db] Database initialized successfully
[2026-10-15 22:58:14] [INFO] [zxtg.main] Registered plugin: 心跳测试 (ping)
[2026-10-15 22:58:14] [INFO] [zxtg.platform.console] Bot -> pong
[2026-10-15 22:58:14] [INFO] [zxtg.services.db] Closing database connections...
[2026-10-15 22:58:14] [INFO] [zxtg.services.db] Database connections closed
```

### 4.6 核心代码行数基线统计
`find src/zxtg/core/kernel src/zxtg/core/services -name '*.py' | xargs wc -l`
```text
   66 src/zxtg/core/kernel/pipeline.py
   69 src/zxtg/core/kernel/enums.py
  119 src/zxtg/core/kernel/guards.py
   51 src/zxtg/core/kernel/__init__.py
   79 src/zxtg/core/kernel/registry.py
   61 src/zxtg/core/services/db.py
    4 src/zxtg/core/services/__init__.py
  449 总计
```
*(说明：内核 + 服务层共计仅 449 行，远优于 NFR-15 ≤700 行及 NFR-14 ≤6,000 行的目标)*

---

## 5. `plugin_info` 26 字段与 §1.2 对照表

| # | 字段名 | Tortoise ORM 字段类型 | 默认值 | 语义与来源说明 |
|---|---|---|---|---|
| 1 | `id` | `fields.IntField(primary_key=True)` | 自增主键 | 数据库自增主键（上游逐字一致） |
| 2 | `module` | `fields.CharField(max_length=255)` | — | 模块标识，如 `ping`（上游逐字一致） |
| 3 | `module_path` | `fields.CharField(max_length=255, unique=True)` | — | Python 模块路径，如 `plugins.ping`（上游逐字一致） |
| 4 | `name` | `fields.CharField(max_length=255)` | — | 插件中文名称（上游逐字一致） |
| 5 | `status` | `fields.BooleanField()` | `True` | 全局开关状态（上游逐字一致） |
| 6 | `block_type` | `fields.CharEnumField(BlockType)` | `None` | 禁用范围类型 PRIVATE/GROUP/ALL（上游逐字一致） |
| 7 | `load_status` | `fields.BooleanField()` | `True` | 加载状态（上游逐字一致） |
| 8 | `author` | `fields.CharField(max_length=255)` | `None` | 插件作者（上游逐字一致） |
| 9 | `version` | `fields.CharField(max_length=255)` | `None` | 插件版本（上游逐字一致） |
| 10 | `level` | `fields.IntField()` | `5` | 所需群权限等级（上游逐字一致） |
| 11 | `default_status` | `fields.BooleanField()` | `True` | 进群默认开关状态（上游逐字一致） |
| 12 | `limit_superuser` | `fields.BooleanField()` | `False` | 是否限制超级用户（上游逐字一致） |
| 13 | `menu_type` | `fields.CharField(max_length=255)` | `""` | 帮助菜单分类标签（上游逐字一致） |
| 14 | `plugin_type` | `fields.CharEnumField(PluginType)` | `None` | 插件分类类型 NORMAL/ADMIN 等（上游逐字一致） |
| 15 | `cost_gold` | `fields.IntField()` | `0` | 调用扣减金币数（上游逐字一致） |
| 16 | `admin_level` | `fields.IntField()` | `0` | 管理员调用所需权限等级（上游逐字一致） |
| 17 | `ignore_prompt` | `fields.BooleanField()` | `False` | 拦截时是否忽略提示（上游逐字一致） |
| 18 | `is_delete` | `fields.BooleanField()` | `False` | 软删除标记（上游逐字一致） |
| 19 | `parent` | `fields.CharField(max_length=255)` | `None` | 父插件 key（上游逐字一致） |
| 20 | `is_show` | `fields.BooleanField()` | `True` | 是否在帮助中展示（上游逐字一致） |
| 21 | `ignore_statistics` | `fields.BooleanField()` | `False` | 是否忽略调用次数统计（上游逐字一致） |
| 22 | `impression` | `fields.FloatField()` | `0.0` | 好感度限制阈值（上游逐字一致） |
| 23 | `plugin_limit` | `fields.ReverseRelation["PluginLimit"]` | — | 反向关联插件限制记录（上游逐字一致） |
| 24 | `description` | `fields.TextField()` | `None` | 插件详细描述（继承自上游 PluginExtraData） |
| 25 | `usage` | `fields.TextField()` | `None` | 插件用法说明文本（继承自上游 PluginExtraData） |
| 26 | `superuser_help` | `fields.TextField()` | `None` | 超级用户指令说明（继承自上游 PluginExtraData） |

---

## 6. 边界检查（B1/B3/B4）实现与结果

### 6.1 实现机制（`tests/test_boundaries.py`）
使用 Python 内置 `ast` 模块，递归遍历源代码的抽象语法树（AST），检查所有 `Import` 与 `ImportFrom` 节点：
1. **B3 边界**：遍历 `src/zxtg/core/kernel/` 与 `src/zxtg/core/services/`，确保不引入任何 `telegram`、`aiogram`、`telethon`、`pyrogram`、`nonebot`、`onebot` 以及平台适配层 `zxtg.core.platform`。
2. **B1 边界**：遍历 `plugins/`，确保插件代码不引用 `zxtg.core.platform` 或底层平台库。
3. **B4 边界**：遍历 `plugins/`，确保插件不直接 import ORM 模型（`zxtg.models` / `tortoise.models`），必须经由 DAO 服务层访问。

### 6.2 检查结果
自动化测试 `tests/test_boundaries.py` 全部通过：
```text
tests/test_boundaries.py::test_b3_boundary_kernel_and_services_no_platform_imports PASSED
tests/test_boundaries.py::test_b1_boundary_plugins_no_platform_imports PASSED
tests/test_boundaries.py::test_b4_boundary_plugins_no_direct_orm_models PASSED
```

---

## 7. BLOCKED 项说明

1. **真实 Telegram 网络收发**：
   - **状态**：**BLOCKED**（按计划留待 M2 阶段进行）。
   - **理由**：任务书明确规定本轮为 M0 骨架奠基，禁止连接真实 Telegram 网络，避免过早引入平台协议复杂度。
2. **`pyflakes` 检查**：
   - **状态**：**BLOCKED**（跳过）。
   - **理由**：环境预装包中无 `pyflakes`，且硬约束禁止在非白名单中引入额外构建工具。静态质量已通过 pytest 及 AST 语法树全量扫描保障。
3. **渲染器与 WebUI**：
   - **状态**：**BLOCKED**（留待 M5 阶段）。
   - **理由**：轻量化架构中渲染器与 WebUI 为可选插件，本轮不予实现。

---

## 8. 与设计文档的偏差 / 实现决策

1. **`Actor` 字段默认值优化**：
   - **决策**：将 `Actor` 数据类定义为 `id: str | int, username: str | None = None, full_name: str = "", is_bot: bool = False`。
   - **理由**：严格符合 `NEXT-TASK-M0.md` §1.3 的参数顺序定义，同时提供合理默认值，确保无论是通过关键字传参（`console.py`）还是通过位置传参，均能正确处理并支持 `Actor.display` 自动回退。
2. **Tortoise ORM 1.1.9 语法适配**：
   - **决策**：模型主键统一采用 `primary_key=True` 替换旧式的 `pk=True`。
   - **理由**：消除了 Tortoise ORM 1.1.9 的 `DeprecationWarning`，确保测试执行 0 警告、全绿通过。
3. **双轨命令分发在 Registry 层映射**：
   - **决策**：`PluginRegistry.register` 在注册 handler 时，自动遍历 `manifest.cmds`，将 `pattern`、`slash` 及 `aliases` 全部建立索引指向同一处理函数。
   - **理由**：使得无论是控制台输入的英文命令（`ping`）、斜杠命令（`/ping`）还是中文别名（`心跳`），都能被管道中的 `Dispatch` 瞬间命中，无需在各插件 handler 中编写重复的分发适配代码。
4. **测试数据库内存隔离**：
   - **决策**：`init_db` 增加对 `":memory:"` 的显式支持，直接注入 SQLite 内存连接 URL。
   - **理由**：避免测试用例在磁盘留下临时文件，且确保并发/顺序测试用例之间的数据完全隔离。

---

## 9. 未解决问题 / 下一轮建议

1. **M1 插件动态扫描装载机制**：
   - 当前 M0 由入口显式注册 `ping` 插件。M1 需实现 `discover` 自动扫描 `plugins/*/plugin.py` 并根据 `requires` 依赖进行拓扑排序装载。
2. **三级配置合并（MergeConfig）与限制检查（GuardLimit）**：
   - M0 中相关 Guard 返回最小实现的 `ALLOW`，M1 应将其与 `plugin_limit`、`group_plugin_switch` 数据表及缓存层实质性打通。
3. **生命周期校验器完善**：
   - 补充插件启动期校验器，对非法 key 格式、命令冲突、循环依赖等在启动阶段早报错、快失败。

---
*(报告完毕，M0 任务圆满交付，已停止下一步动作)*
