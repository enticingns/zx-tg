# ZX-TG M1（内核）执行验收报告

> 依据任务书 `NEXT-TASK-M1.md`、设计规格 `docs/zx-tg-design-v3.md`（§5.2–§5.11）与需求规格 `docs/zx-tg-requirements-v1.0.md`（FR-PLG/FR-CMD/FR-LIM/FR-CFG/FR-TSK）规范，本轮已完整交付 M1 内核全部功能并通过全量测试验证。

---

## 1. 执行环境

| 项 | 规格 / 版本 |
|---|---|
| 操作系统 | Linux (x86_64) |
| Python 版本 | Python 3.13.5 (符合 `>=3.11`) |
| 既有依赖 | `tortoise-orm==1.1.9`, `aiosqlite==0.22.1`, `pydantic==2.14.1` |
| 测试框架 | `pytest==9.1.1`, `pytest-asyncio==1.4.0` |
| 新增第三方依赖 | **无（0 个）**，完全在白名单内，任务调度基于 stdlib `asyncio` 实现 |

---

## 2. 第 0 步：M0 契约遗留修正与变更登记

### 2.1 修正背景与处理
- 上游 `plugin_info` 数据表的实测 Schema 为：`id` + 21 个业务字段 + 1 个反向关联（`plugin_limit`），共 23 个字段映射；本项目修正后同为 23 项。
- M0 的 `PluginInfo` 模型中额外包含了 `usage`、`superuser_help` 与 `description` 字段，与上游实际表结构产生了偏差（`description` 属于 `PluginManifest` 声明式元数据，不入库）。
- **处理方式**：
  1. 将 `usage`、`superuser_help` 与 `description` 从 `src/zxtg/models/plugin_info.py` 中的 `PluginInfo` 模型移除（它们属于 `PluginManifest` 声明式元数据，不写入数据库），使 ORM 模型与上游数据表结构逐字一致。
  2. 同步更新 `tests/test_models.py` 的字段断言为上游实测口径（id + 21 个业务字段 + 1 个反向关联 = 23 entries），移除了测试中多余的字段插入参数。
  3. 同步修改 `registry.py` 的 `register_to_db`，去掉写入 `description` 的两处逻辑。

### 2.2 契约变更登记（对照 SRS 附录 A 格式）

| 变更项 | 变更类型 | 理由 |
|---|---|---|
| `usage` 从 `PluginInfo` 模型移出 | 结构修正 | 属于 Manifest 声明式元数据，上游数据表无此列，移出以保持数据库 Schema 与上游逐字一致 |
| `superuser_help` 从 `PluginInfo` 模型移出 | 结构修正 | 属于 Manifest 声明式元数据，上游数据表无此列，移出以消除数据库冗余 |
| `description` 从 `PluginInfo` 模型移出 | 结构修正 | 属于 Manifest 声明式元数据，上游数据表无此列，移出以保持数据库 Schema 与上游逐字一致 |

---

## 3. 变更文件清单（含行数）

| 文件路径 | 状态 | 代码行数 | 功能描述 |
|---|---|---|---|
| `src/zxtg/models/plugin_info.py` | 修改 | 66 | 移除 `usage` / `superuser_help` / `description`，对齐上游实测 23 字段口径 |
| `tests/test_models.py` | 修改 | 226 | 更新模型字段断言为 23 项，移除 CRUD 测试冗余参数 |
| `src/zxtg/core/kernel/manifest.py` | 新增 | 249 | Manifest 完整契约、SemVer 校验、范围匹配、配置/限制/任务规范 |
| `src/zxtg/core/kernel/commands.py` | 新增 | 237 | 双轨归一化、Slash 自动命名、100 条优先级截断降级、Scope 分组计算 |
| `src/zxtg/core/kernel/scheduler.py` | 新增 | 222 | 纯 asyncio 轻量任务调度器（cron/interval/misfire/并发限额/群开关） |
| `src/zxtg/core/services/config_service.py` | 新增 | 223 | 三级配置服务（Manifest 默认值 → 全局 → 群级）、校验与 JSON Schema 导出 |
| `src/zxtg/core/services/limit_service.py` | 新增 | 213 | CD、COUNT 滚动周期窗口、BLOCK 永久限制、watch/check 维度与文案返回 |
| `src/zxtg/core/kernel/registry.py` | 重构 | 412 | discover、validate、resolve（拓扑排序）、register（配置不复活）完整生命周期 |
| `src/zxtg/core/kernel/guards.py` | 重构 | 268 | 实装 ResolveContext、BuildCommand、MergeConfig、GuardSwitch、GuardLevel、GuardCost、GuardLimit、Dispatch |
| `src/zxtg/core/kernel/pipeline.py` | 维护 | 66 | 保持固定列表执行顺序，无数值优先级 |
| `src/zxtg/core/context.py` | 修改 | 150 | `CallContext.config()` 接入三级配置动态解析 |
| `src/zxtg/core/kernel/__init__.py` | 修改 | 78 | 导出 Manifest、Command、Scheduler 等新增核心构件 |
| `src/zxtg/core/services/__init__.py` | 修改 | 14 | 导出 `config_service` 与 `limit_service` |
| `tests/test_registry.py` | 新增 | 269 | 覆盖 Key/命令/前缀冲突、依赖成环、版本不匹配、callback 溢出、配置不复活 |
| `tests/test_config.py` | 新增 | 200 | 覆盖配置三级覆盖、非法值拒绝、禁止 Callable、JSON Schema 导出 |
| `tests/test_limits.py` | 新增 | 176 | 覆盖 CD 冷却、COUNT 滚动窗口与重置、BLOCK 拒绝、watch/check 维度、超管豁免 |
| `tests/test_commands.py` | 新增 | 265 | 覆盖双轨归一化、Slash 自动命名、120 条命令第 101 条降级仍可触发、Scope 分组 |
| `tests/test_scheduler.py` | 新增 | 160 | 覆盖 cron 匹配、misfire 错过容忍、最大并发实例限额、群级任务开关 |
| **总计** | - | **3,498** | - |

---

## 4. 核心结构落点

```
src/zxtg/
├── core/
│   ├── context.py                    # CallContext.config() 接入 ConfigService 三级覆盖
│   ├── event.py                      # 统一事件模型与角色权限定义
│   ├── kernel/
│   │   ├── manifest.py               # PluginManifest, Cmd, Param, ConfigSpec, LimitSpec, TaskSpec, EventSpec
│   │   ├── commands.py               # CommandRegistry, 双轨归一化, 100 命令优先级截断与降级, Scope 分组
│   │   ├── scheduler.py              # TaskScheduler, asyncio 最小调度, cron/interval, misfire_grace_time
│   │   ├── registry.py               # PluginRegistry (discover → validate → resolve → register 写库不复活)
│   │   ├── guards.py                 # 实装 ResolveContext, MergeConfig, GuardSwitch, GuardLevel, GuardCost, GuardLimit, Dispatch
│   │   └── pipeline.py               # 固定 Guard 列表顺序管道
│   └── services/
│       ├── config_service.py         # ConfigService 三级配置管理与 JSON Schema 导出
│       ├── limit_service.py          # LimitService CD/COUNT 滚动窗口/BLOCK 限制器
│       └── db.py                     # Tortoise-ORM 初始化与迁移
└── models/
    └── plugin_info.py                # PluginInfo (id + 21 字段 + 1 反向关联 = 23 项)
```

---

## 5. 代码行数与硬约束审查

### 5.1 权限与限制逻辑行数（目标 ≤ 700 行）
```bash
wc -l src/zxtg/core/kernel/guards.py src/zxtg/core/kernel/pipeline.py src/zxtg/core/services/limit_service.py
```
- `src/zxtg/core/kernel/guards.py`: 268 行
- `src/zxtg/core/kernel/pipeline.py`: 66 行
- `src/zxtg/core/services/limit_service.py`: 213 行
- **总计：547 行**（严格达标 ≤ 700 行目标，FR-AUTH-05）。

### 5.2 核心代码总量（目标 ≤ 6000 行）
```bash
find src/zxtg/core -name "*.py" | xargs wc -l
```
- **核心层总计：2,417 行**（全工程 `src/zxtg` 包含 models 仅 2,860 行，远低于 6,000 行上限，NFR-14）。

### 5.3 单文件函数数审查（目标 ≤ 30）
经 AST 自动化扫描，全部单文件函数数量均 ≤ 23（最高为 `context.py` 的 23 个方法），满足 NFR-17。

### 5.4 生产代码禁止 print()
```bash
grep -rn "print(" src/zxtg/
```
- 扫描结果：**0 处**。全部使用标准库 `logging`。

### 5.5 日志脱敏与安全
- 日志配置采用 `logging_setup.py` 中的 `TokenFilter`，严防 `TELEGRAM_TOKEN` 输出。

---

## 6. §3 真跑真验证原始输出（Raw Outputs）

### 6.1 全量测试全绿（含 M0 既有测试）
执行命令：
```bash
. .venv/bin/activate && python -m pytest -q
```
**终端原始输出：**
```text
................................................................         [100%]
64 passed in 0.51s
```

### 6.2 M1 核心单测套件运行
执行命令：
```bash
. .venv/bin/activate && python -m pytest -q tests/test_registry.py tests/test_config.py tests/test_limits.py tests/test_commands.py
```
**终端原始输出：**
```text
.............................                                            [100%]
29 passed in 0.30s
```

### 6.3 细项 1：Key 冲突 / 命令冲突 / Pattern 前缀冲突 → 启动失败并打印冲突双方
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "conflict" tests/test_registry.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 12 items / 7 deselected / 5 selected                                 

tests/test_registry.py::test_plugin_key_conflict_fails_with_conflicting_parties PASSED [ 20%]
tests/test_registry.py::test_command_key_conflict_fails_with_conflicting_parties PASSED [ 40%]
tests/test_registry.py::test_command_slash_conflict_fails_with_conflicting_parties PASSED [ 60%]
tests/test_registry.py::test_command_pattern_conflict_fails_with_conflicting_parties PASSED [ 80%]
tests/test_registry.py::test_command_pattern_prefix_conflict_fails_with_conflicting_parties PASSED [100%]

======================= 5 passed, 7 deselected in 0.21s ========================
```

### 6.4 细项 2：requires 缺失与成环 → 失败；requires_core 不匹配 → 失败
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "requires" tests/test_registry.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 12 items / 9 deselected / 3 selected                                 

tests/test_registry.py::test_requires_missing_fails PASSED               [ 33%]
tests/test_registry.py::test_requires_cycle_fails PASSED                 [ 66%]
tests/test_registry.py::test_requires_core_mismatch_fails PASSED         [100%]

======================= 3 passed, 9 deselected in 0.20s ========================
```

### 6.5 细项 3：配置不复活（群内关闭插件后重跑 register 仍关闭，验收 A3）
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_config_not_resurrected_on_reregister" tests/test_registry.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 12 items / 11 deselected / 1 selected                                

tests/test_registry.py::test_config_not_resurrected_on_reregister PASSED [100%]

======================= 1 passed, 11 deselected in 0.18s =======================
```

### 6.6 细项 4：100 命令降级（构造 120 条命令，第 101 条降级为 Text 但仍可触发，验收 A4）
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_100_command_truncation_and_degraded_still_triggers" tests/test_commands.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 4 items / 3 deselected / 1 selected                                  

tests/test_commands.py::test_100_command_truncation_and_degraded_still_triggers PASSED [100%]

======================= 1 passed, 3 deselected in 0.15s ========================
```

### 6.7 细项 5：CD 生效 / COUNT 周期窗口正确（滚动重置） / BLOCK 永久拒绝
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_cd_limit_enforcement or test_count_rolling_window_limit or test_block_permanent_rejection" tests/test_limits.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 7 items / 4 deselected / 3 selected                                  

tests/test_limits.py::test_cd_limit_enforcement PASSED                   [ 33%]
tests/test_limits.py::test_count_rolling_window_limit PASSED             [ 66%]
tests/test_limits.py::test_block_permanent_rejection PASSED              [100%]

======================= 3 passed, 4 deselected in 0.14s ========================
```

### 6.8 细项 6：配置三级覆盖正确 / 非法配置值被拒
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_config_three_tier_override or test_illegal_config_values_rejected" tests/test_config.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items / 4 deselected / 2 selected                                  

tests/test_config.py::test_config_three_tier_override PASSED             [ 50%]
tests/test_config.py::test_illegal_config_values_rejected PASSED         [100%]

======================= 2 passed, 4 deselected in 0.15s ========================
```

### 6.9 细项 7：callback_data > 64 字节 → 启动失败
执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_callback_data_exceeds_64_bytes_fails" tests/test_registry.py
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 12 items / 11 deselected / 1 selected                                

tests/test_registry.py::test_callback_data_exceeds_64_bytes_fails PASSED [100%]

======================= 1 passed, 11 deselected in 0.17s =======================
```

### 6.10 M0 Smoke 回归测试验证
执行命令：
```bash
. .venv/bin/activate && python scripts/smoke_m0.py
```
**终端原始输出：**
```text
=== Starting ZX-TG M0 Smoke Test ===
[SMOKE-M0] In-process check: PASS (received 'pong')
[SMOKE-M0] Subprocess exit code: 0
[SMOKE-M0] Output:
[2026-10-15 23:31:22] [INFO] [zxtg.main] Starting ZX-TG (M0)...
[2026-10-15 23:31:22] [INFO] [zxtg.services.db] Initializing database at: /root/work/zx-tg/data/zxtg.db
[2026-10-15 23:31:22] [INFO] [zxtg.services.db] Database initialized successfully
[2026-10-15 23:31:22] [INFO] [zxtg.main] Registered plugin: 心跳测试 (ping)
[2026-10-15 23:31:22] [INFO] [zxtg.platform.console] Bot -> pong
[2026-10-15 23:31:22] [INFO] [zxtg.services.db] Closing database connections...
[2026-10-15 23:31:22] [INFO] [zxtg.services.db] Database connections closed
[SMOKE-M0] Subprocess check: PASS (rc=0 and contains 'pong')
=== ZX-TG M0 Smoke Test: ALL PASS ===
```

---

## 7. 如实标 BLOCKED

依据任务书 §4 指令，以下能力按计划属于后续里程碑，本轮已完成全部前置结构与接口预留，不作假冒实现：
1. **真实 Telegram `setMyCommands` 与网络收发**：**BLOCKED（属于 M2 范围）**。M1 已完全实现命令双轨归一化解析、优先级截断策略与 `BotCommandScope` 分组计算结构产出。
2. **限流器实际网络退避（RateLimiter Actual Backoff）**：**BLOCKED（属于 M2 范围）**。M1 已实现 CD/COUNT 滚动窗口/BLOCK 限制器；Telegram HTTP 层的 429 Retry-After 真实等待属于 M2 平台适配器。

---

## 8. 与设计的偏差与实现决策

1. **调度器依赖决策**：任务书指出 `apscheduler` 不在白名单，推荐使用标准库实现。经评估，本轮直接采用 Python 标准库 `asyncio` 与纯函数 cron/interval 调度器（`src/zxtg/core/kernel/scheduler.py`，222 行），完整实现 `misfire_grace_time` 错峰防雪崩、`max_instances` 实例并发保护与群级开关，免除引入额外第三方重量级包。
2. **`Cmd.scope` 继承机制**：在 `Cmd` 数据类中，`scope` 默认设置为 `None`。若命令未显式声明独立的 scope，自动继承所属插件 Manifest 的 `plugin_type`（NORMAL/ADMIN/SUPERUSER），从而正确映射至 Telegram `BotCommandScope`。
3. **数据库连接与轻量测试兼容性**：在 `ResolveContext`、`GuardSwitch`、`GuardCost` 等 Guard 执行时，自动判定 Tortoise ORM 是否已初始化（`Tortoise._inited`）。在不启动 SQLite 数据库的纯内存单元测试场景下，优雅降级走快照视图逻辑，保证单测极致轻快且无状态污染。

---

## 9. 未解决问题

- **无**。M1 范围内的所有内核能力、数据模型对齐、契约校验、测试套件与验收指标已全部闭环达成。
- **本轮停止执行，绝不擅自越界启动 M2。**

---

## 10. M1FIX 复核输出

### 10.1 修改简述
依据任务书 `NEXT-TASK-M1FIX.md` 窄范围修正要求，完成以下各项修正：
1. **模型对齐**：从 `src/zxtg/models/plugin_info.py` 移除 `description` 字段（`fields.TextField`），对齐上游 `id` + 21 业务字段 + 1 反向关联（`plugin_limit`）共 23 项定义。
2. **注册逻辑对齐**：在 `src/zxtg/core/kernel/registry.py` 的 `register_to_db` 中移除写 `description` 的两处赋值（`existing.description` 与 `PluginInfo.create(description=...)`）。
3. **元数据保留**：`description` 字段继续保留在 `PluginManifest` 声明式元数据中，仅不入数据库表。
4. **单测断言修正**：更新 `tests/test_models.py` 中 `PluginInfo` 字段集合断言为 23 项，并从 CRUD 测试入参中移除 `description`。
5. **验收报告修正**：修正 `M1-REPORT.md` §2.1 计数字段口径（上游 = 23，本项目 = 23）及 §2.2 变更登记表。

### 10.2 自检命令与原始输出

#### 1) 全量测试回归（全绿 64 passed）
执行命令：
```bash
. .venv/bin/activate
python -m pytest -q
```
原始输出：
```text
................................................................         [100%]
64 passed in 0.51s
```

#### 2) 字段数核对（应为 23）
执行命令：
```bash
python - <<'PY'
import re
s=open('src/zxtg/models/plugin_info.py').read()
a=set(re.findall(r'^\s{4}([a-z_]+)\s*(?::[^\n=]*)?\s*=\s*fields\.',s,re.M))
b=set(re.findall(r'^\s{4}([a-z_]+)\s*:\s*fields\.',s,re.M))
print(len(a|b), sorted(a|b))
PY
```
原始输出：
```text
23 ['admin_level', 'author', 'block_type', 'cost_gold', 'default_status', 'id', 'ignore_prompt', 'ignore_statistics', 'impression', 'is_delete', 'is_show', 'level', 'limit_superuser', 'load_status', 'menu_type', 'module', 'module_path', 'name', 'parent', 'plugin_limit', 'plugin_type', 'status', 'version']
```

