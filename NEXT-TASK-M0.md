# NEXT-TASK-M0：奠基（骨架 / UnifiedEvent / CallContext / 管道骨架 / SQLite 模型）

> 本文件是**当前唯一权威指令**。设计细节以 `docs/zx-tg-design-v3.md` 与 `docs/zx-tg-requirements-v1.0.md` 为准。
> 本轮**只做 M0**。不要提前实现 M1/M2 的功能（不要接真实 Telegram、不要写内置业务插件、不要做渲染器/WebUI）。

---

## 1. 本轮交付物（必须全部落地）

### 1.1 项目骨架
```
zx-tg/
├── pyproject.toml            # 包名 zxtg，Python >=3.11，含 M0 依赖；提供 [project.optional-dependencies] lite
├── README.md                 # 已存在，可补充「快速开始」
├── src/zxtg/
│   ├── __init__.py
│   ├── __main__.py           # 入口：python -m zxtg
│   ├── config.py             # 全局配置：TELEGRAM_TOKEN / DB_PATH / LOG_LEVEL 等，支持环境变量覆盖
│   ├── logging_setup.py      # 分级日志；Token 绝不落日志（NFR-09）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── event.py          # UnifiedEvent / Actor / Role / ChatRef / CommandRef  ★
│   │   ├── context.py        # CallContext（不可变快照）+ 各 View
│   │   ├── kernel/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py   # PIPELINE 列表 + Guard 协议 + Verdict  ★
│   │   │   ├── guards.py     # 各 Guard 的 M0 最小实现（见 §3）
│   │   │   ├── registry.py   # 插件注册表骨架（M0 只需能登记/查询，不做完整校验）
│   │   │   └── enums.py      # PluginType / BlockType / PluginLimitType / LimitWatchType（逐字继承）★
│   │   ├── platform/
│   │   │   ├── __init__.py
│   │   │   ├── base.py       # PlatformAdapter 抽象接口（收发/动作）★
│   │   │   └── console.py    # 控制台调试适配器（M0 冒烟用，非 TG）
│   │   └── services/
│   │       ├── __init__.py
│   │       └── db.py         # Tortoise 初始化 + 迁移执行入口
│   └── models/
│       ├── __init__.py
│       ├── plugin_info.py    # plugin_info（26 字段，字段名逐字继承）★
│       ├── plugin_limit.py
│       ├── group_console.py
│       ├── user_console.py
│       ├── logs.py           # user_gold_log / user_impression_log
│       ├── switch.py         # group_plugin_switch
│       ├── task_record.py
│       ├── statistics.py
│       ├── join_request.py
│       └── migration_record.py
├── plugins/                  # 内置插件目录（M0 只放一个示例：ping）
│   └── ping/
│       ├── plugin.py         # manifest + handler（证明契约可用）
│       └── __init__.py
├── plugins_ext/              # 第三方插件目录（M0 空目录 + .gitkeep）
├── tests/
│   ├── test_event.py
│   ├── test_pipeline.py
│   ├── test_enums_contract.py
│   └── test_models.py
└── scripts/
    └── smoke_m0.py           # 冒烟：构造事件 → 过管道 → 命中 ping → 得到回复
```

### 1.2 核心数据模型（逐字继承上游，见设计 §1.2）
- `core/kernel/enums.py`：`PluginType`(SUPERUSER|ADMIN|SUPER_AND_ADMIN|NORMAL|DEPENDANT|HIDDEN|PARENT)、`BlockType`(PRIVATE|GROUP|ALL)、`LimitWatchType`(USER|GROUP|ALL)、`LimitCheckType`、`PluginLimitType`(CD|COUNT|BLOCK) —— **枚举名字与成员值必须与上游一致**，写测试锁死。
- `models/plugin_info.py`：26 字段（module, module_path, name, status, block_type, load_status, author, version, level, default_status, limit_superuser, menu_type, plugin_type, cost_gold, admin_level, ignore_prompt, is_delete, parent, is_show, ignore_statistics, impression + 上游其余字段），字段名逐字继承。

### 1.3 UnifiedEvent（设计 §2.3）
```
UnifiedEvent
├── actor: Actor(id, username: str|None, full_name, is_bot)
├── role: Role(owner|administrator|member|restricted)   # 带 level 映射：owner=100/admin=10/member=0
├── chat: ChatRef(id, type: private|group|supergroup, title) | None
├── kind: text|command|callback|join|leave|member_update|join_request
├── text: str
├── command: CommandRef(name, args, raw) | None
├── message_id: int
└── raw: object   # 逃生舱；插件层禁用（B 边界）
```
- `Actor.display` 必须在 `username is None` 时回退到 `full_name`（FR-TG-08）。

### 1.4 CallContext（设计 §5.6 / FR-AUTH-10）
不可变快照，含：`event`、`user: UserView`、`group: GroupView | None`、`plugin: PluginView | None`、以及给插件用的白名单 API 占位（`config/cache/reply/...` 可先抛 NotImplemented，但**接口签名必须定死**，见设计 §5.12）。

### 1.5 管道骨架（设计 §5.6 / FR-AUTH-01/02/03/04）
```python
PIPELINE = [ResolveContext, BuildCommand, MergeConfig, GuardBan,
            GuardSwitch, GuardLevel, GuardCost, GuardLimit, Dispatch]
```
- `Verdict`：只有 ALLOW / DENY(reason, tip)。
- 顺序**由列表位置决定**，禁止 priority 数字（FR-AUTH-03）。
- M0 允许各 Guard 是最小实现（如 GuardBan 直接 ALLOW），但**形状必须正确**，且 Dispatch 真的能调到 handler。
- 每次调用可 `repr` 完整打印（FR-AUTH-10）。

### 1.6 硬边界（FR §5 / B1–B4）——必须有自动检查
- **B3**：`core/kernel/` 与 `core/services/` **不得 import telegram / aiogram / 任何平台库**。写一个测试 `test_boundaries.py` 静态扫描源码，违规即失败。
- **B1**：`plugins/` 不得 import `core.platform`。同样静态扫描。
- **B4**：插件不得直接 import Tortoise 模型，须经 DAO/服务层（M0 允许先只做测试占位）。

### 1.7 冒烟：`python -m zxtg` + `/ping`
- 用 `console.py` 适配器：从 stdin 读一行文本，走管道，命中 `plugins/ping` 的 handler，打印回复后退出。
- `scripts/smoke_m0.py` 必须能**非交互**跑通并断言输出包含 `pong`。

---

## 2. 硬性约束（违反即返工）

1. **Python ≥ 3.11**。宿主是 3.13.5。
2. **依赖只用白名单**：`tortoise-orm`、`aiosqlite`、`pydantic>=2`、`pytest`、`pytest-asyncio`。**不要**引入 nonebot2 / aiogram / python-telegram-bot / playwright / fastapi（M0 不需要；平台库选择留到 M2）。
3. **不得编造上游字段**。`plugin_info` / 枚举的字段名与值必须与 `docs/zx-tg-design-v3.md` §1.2 一致。
4. **不要引入任何 fallback / patch / guard-of-guard 兼容层**（FR-AUTH-06 / NFR-16）。
5. **禁裸输出**：生产代码不使用 `print()`，一律走 logger。`scripts/` 与 `tests/` 例外。
6. **Token 安全**：任何日志/异常/导出中不得出现 `TELEGRAM_TOKEN` 或其片段（NFR-09）。
7. **单文件函数数 ≤ 30**（NFR-17）。
8. **不要碰** `docs/`、`README.md` 的既有内容；不要修改 `NEXT-TASK-M0.md`。
9. **不要提交** `data/`、`.venv/`、`*.db`、`*.log`（`.gitignore` 已挡，确认之）。

---

## 3. 真跑真验证（必须在本轮真的执行，并把原始输出写进报告）

```bash
# 环境（宿主已装 python3.13；venv 自带 pip）
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"          # 或 pip install -e . + 手动装 dev 依赖

# 1) 静态检查
python -m pytest -q               # 全绿
python -m pyflakes src/zxtg       # 若可用；无则跳过并说明

# 2) 边界与契约测试必须存在且通过
python -m pytest -q tests/test_boundaries.py tests/test_enums_contract.py

# 3) 冒烟
python scripts/smoke_m0.py        # 输出须含 pong，退出码 0
echo "ping" | python -m zxtg       # 人工可读的收发演示

# 4) 代码量基线（NFR-14/15 的起点）
find src/zxtg/core/kernel src/zxtg/core/services -name '*.py' | xargs wc -l
```

异步测试用 `pytest-asyncio`（`asyncio_mode = auto`）。

---

## 4. 如实标 BLOCKED
- 真实 Telegram 收发 → M2，**本轮不测，不要假装测过**。
- WebUI / 渲染器 → M5。
- 若某项因环境不可行（如 pyflakes 装不上），**标 BLOCKED 并说明**，不要谎报通过。

---

## 5. 交付格式
完成后写 **`M0-REPORT.md`**，含：
1. 环境与工具链（python / pip / 已装包及版本）
2. 变更文件清单（含行数）
3. 核心数据结构落点（UnifiedEvent / CallContext / Verdict / PIPELINE 各在哪、长什么样）
4. §3 各条验证命令的**原始输出**
5. `plugin_info` 26 字段与 §1.2 的对照表
6. 边界检查（B1/B3）如何实现与结果
7. BLOCKED 项
8. 与设计文档的偏差 / 你的实现决策（含为何这样决定）
9. 未解决问题 / 下一轮建议

报告写完即停。不要开始 M1。
