# M3 阶段总结报告：核心服务层

> 本报告依据 `NEXT-TASK-M3.md`、设计规格 `docs/zx-tg-design-v3.md`（§2.1 L3 / §3.4）与需求规格 `docs/zx-tg-requirements-v1.0.md`（FR-SVC-01~08、FR-DATA-01~09）编写。
> M3 阶段核心服务层、数据层加固、管道接线与全量自动化断言已完备交付。报告写完即停，未提前进入 M4。

---

## 1. 环境与依赖

- **操作系统**：Linux (x86_64)
- **Python 版本**：Python 3.13.5 (符合 `>=3.11`)
- **既有依赖**：`tortoise-orm==1.1.9`, `aiosqlite==0.22.1`, `pydantic==2.14.1`, `httpx==0.28.1`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`
- **新增第三方依赖**：**无（0 个）**，完全在白名单内，严格禁止引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi/uvicorn。

---

## 2. 变更文件清单及行数

| 文件路径 | 变更属性 | 行数 | 职责说明 |
|---|---|---|---|
| `src/zxtg/models/user_console.py` | 修改 | 22 | 增加 `level` 字段以支持用户独立权限等级读写 (FR-SVC-01) |
| `src/zxtg/models/item.py` | 新增 | 22 | `UserItem` 道具持有、数量与过期时间模型 (FR-SVC-06) |
| `src/zxtg/models/__init__.py` | 修改 | 27 | 导出 `UserItem` 模型符号 |
| `src/zxtg/core/context.py` | 修改 | 198 | `CallContext` 接真实 `gold`, `impression`, `db` DAO 接口 |
| `src/zxtg/core/kernel/guards.py` | 重构 | 296 | ResolveContext 接入服务层，GuardLevel 接权限服务，GuardCost 实现成功才扣费 |
| `src/zxtg/core/kernel/registry.py` | 修改 | 417 | 消除与服务层顶级循环依赖，采用方法内按需加载 |
| `src/zxtg/core/services/user_service.py` | 新增 | 113 | 用户服务：TG 原生 user_id、level/gold/impression 读写、display_name 回退 |
| `src/zxtg/core/services/group_service.py` | 新增 | 131 | 群服务：TG 原生 chat_id、标题/成员/活跃度维护、新群 default_status 开关初始化 |
| `src/zxtg/core/services/gold_service.py` | 新增 | 75 | 金币服务：F 表达式条件更新原子扣费、防透支拒绝、流水审计日志 |
| `src/zxtg/core/services/impression_service.py` | 新增 | 77 | 好感度服务：原子扣费、防超扣、流水日志 |
| `src/zxtg/core/services/permission_service.py` | 新增 | 83 | 权限服务：TG 角色→100/10/0、群级覆盖、超管 limit_superuser 绕过 |
| `src/zxtg/core/services/item_service.py` | 新增 | 108 | 道具服务：持有、使用扣减、过期过滤与清理 (FR-SVC-06) |
| `src/zxtg/core/services/statistics_service.py` | 新增 | 116 | 高频计数服务：内存聚合缓冲、零写库打点、批量落盘 (FR-DATA-03) |
| `src/zxtg/core/services/dao.py` | 新增 | 49 | 插件安全 DAO 接口与裸 SQL 拦截器 `RawSQLError` (FR-DATA-04) |
| `src/zxtg/core/services/db.py` | 修改 | 125 | SQLite WAL 模式、busy_timeout>=5000、损坏检测、显式迁移 |
| `src/zxtg/core/services/__init__.py` | 修改 | 50 | 导出核心服务单例与 DAO 接口 |
| `tests/test_boundaries.py` | 修改 | 165 | 增加 B5 插件层禁止引用底层 SQL 驱动边界检查 |
| `tests/test_services.py` | 新增 | 565 | M3 核心服务层全套测试套件（覆盖 §3 全部验证项） |
| **总计** | - | **2639** | - |

---

## 3. 核心结构与设计落点

1. **用户服务（`user_service.py`）**：
   - 唯一用户标识直接使用 Telegram 原生 `user_id`（字符串化存储，零二次编码，FR-SVC-07）。
   - 统一提供等级（`level`）、金币（`gold`）、好感度（`impression`）的安全读写接口。
   - `get_display_name` 实现用户名为空时向 `full_name` 优雅回退，均缺失时回退为 `user_id`（FR-TG-08）。
   - 恒定 `platform="telegram"`。
2. **群服务（`group_service.py`）**：
   - 群 ID 直接采用 Telegram 原生 `chat_id`（FR-SVC-08）。
   - 维护群标题、成员数、最大成员数记录、群权限等级（`level`）与最后活跃时间戳（`last_active`）。
   - 新群入库时自动遍历已装载插件的 `default_status` 初始化 `GroupPluginSwitch` 记录（FR-PLG-09）；已存在群保持幂等，绝不覆盖管理员既有设置。
3. **金币与好感度经济原子服务（`gold_service.py` / `impression_service.py`）**：
   - 变动操作采用事务（`in_transaction`）结合条件查询与 `F()` 原语更新（如 `UserConsole.filter(user_id=uid, gold__gte=cost).update(gold=F("gold") - cost)`）。
   - 余额不足时立即拒绝并返回明确原因，严禁任何透支或部分扣款。
   - 每次成功变动均原子记录流水日志（`UserGoldLog` / `UserImpressionLog`），保证审计追溯性。
4. **权限服务（`permission_service.py`）**：
   - Telegram 角色严格归一映射：`creator`/`owner` → `OWNER` (100)、`administrator` → `ADMINISTRATOR` (10)、`member`/`restricted` → `MEMBER` (0)。
   - 群权限覆盖（FR-AUTH-11）：群内普通成员的有效权限提升至群级 `GroupConsole.level`（默认 5），管理员及创建者不受降级影响。
   - 超级用户豁免（FR-AUTH-08）：`limit_superuser=False` 时，超级用户（level >= 100）全通透绕过插件开关与频率限制。
5. **道具服务（`item_service.py`）**：
   - 最小可用且完备支持：持有状态查询（`has_item` / `get_items`）、使用与数量扣除（`use_item`，优先扣除即将过期道具）、过期过滤与清理（`clean_expired_items`）。
6. **数据层加固（`db.py` / `statistics_service.py` / `dao.py`）**：
   - SQLite 启动时自动设置 `PRAGMA journal_mode=WAL;` 及 `PRAGMA busy_timeout=5000;`（FR-DATA-01, FR-DATA-02）。
   - 数据库损坏检测（`check_db_integrity`）：启动时通过 SQLite `PRAGMA integrity_check;` 排查文件损坏，非有效 SQLite 文件提供明确诊断（FR-DATA-09）。
   - 高频计数缓冲（`statistics_service`）：调用记录暂存内存字典，100 次调用产生 0 次写库；调用 `flush()` 时按 `(plugin, user, group)` 批量聚合落盘（FR-DATA-03）。
   - 插件防裸 SQL 约束：插件必须经由 `BaseDAO` 访问，直接执行裸 SQL 立即抛出 `RawSQLError`（FR-DATA-04），并通过 AST 静态扫描阻断裸数据库驱动 import。
   - 迁移脚本显式化：结构变更经 `run_explicit_migration` 与 `MigrationRecord` 控制，禁止运行时隐式 ALTER（FR-DATA-05）。
7. **管道接线与扣费绑定（`guards.py` / `pipeline.py`）**：
   - `ResolveContext` 接入 `user_service` 与 `group_service` 实现全自动幂等注册与状态同步。
   - `GuardSwitch` 检查全局及群级插件开关，并对 `limit_superuser=False` 的超管放行。
   - `GuardLevel` 接入 `permission_service.can_execute_detailed` 评估有效权限。
   - `GuardCost` 校验余额并在 Context 挂载扣费快照凭据；扣费逻辑绑定于 `Dispatch` 成功执行 handler 之后：**handler 执行失败或抛出异常时绝对不扣费**（FR-AUTH-09）。

---

## 4. §3 验证原始输出

### 4.1 全量测试套件（98 项测试全绿，原 84 项 + 新增 14 项）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -q
```
**终端原始输出：**
```text
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 1.09s
```

---

### 4.2 原子扣费：并发/交错场景金币不丢不超扣，余额不足拒绝且零扣费

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "atomic" tests/test_services.py
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
collecting ... collected 13 items / 11 deselected / 2 selected                                

tests/test_services.py::test_atomic_gold_deduction_and_rejection PASSED  [ 50%]
tests/test_services.py::test_atomic_impression_deduction_and_rejection PASSED [100%]

======================= 2 passed, 11 deselected in 0.22s =======================
```

---

### 4.3 扣费与成功绑定：handler 失败 → 不扣费（FR-AUTH-09）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_cost_deduction_bound_to_handler_success" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_cost_deduction_bound_to_handler_success PASSED [100%]

======================= 1 passed, 12 deselected in 0.18s =======================
```

---

### 4.4 权限：OWNER=100 / ADMIN=10 / MEMBER=0、群级覆盖与超管绕过（FR-AUTH-08, FR-AUTH-11）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "permission" tests/test_services.py
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
collecting ... collected 13 items / 11 deselected / 2 selected                                

tests/test_services.py::test_permission_service_roles_and_group_override PASSED [ 50%]
tests/test_services.py::test_permission_superuser_bypass_when_limit_superuser_false PASSED [100%]

======================= 2 passed, 11 deselected in 0.19s =======================
```

---

### 4.5 SQLite WAL + busy_timeout 生效（PRAGMA 校验）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_sqlite_wal_and_busy_timeout" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_sqlite_wal_and_busy_timeout PASSED          [100%]

======================= 1 passed, 12 deselected in 0.29s =======================
```

---

### 4.6 高频计数缓冲：N 次调用 0 次写库，批量落盘后总数正确（FR-DATA-03）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "test_high_frequency_counter_buffer_and_batch_flush" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_high_frequency_counter_buffer_and_batch_flush PASSED [100%]

======================= 1 passed, 12 deselected in 0.18s =======================
```

---

### 4.7 插件裸 SQL 防护：DAO 外直接访问被测试捕获（FR-DATA-04）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "raw_sql" tests/test_services.py tests/test_boundaries.py
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
collecting ... collected 19 items / 17 deselected / 2 selected                                

tests/test_services.py::test_plugin_raw_sql_protection PASSED            [ 50%]
tests/test_boundaries.py::test_b5_boundary_plugins_no_raw_sql_drivers PASSED [100%]

======================= 2 passed, 17 deselected in 0.18s =======================
```

---

### 4.8 群与用户初始化幂等（重复 ResolveContext 不重复建记录）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "idempotence" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_resolve_context_idempotence PASSED          [100%]

======================= 1 passed, 12 deselected in 0.19s =======================
```

---

### 4.9 数据库损坏检测与明确诊断（FR-DATA-09）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "integrity" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_database_integrity_check PASSED             [100%]

======================= 1 passed, 12 deselected in 0.18s =======================
```

---

### 4.10 道具服务生命周期（FR-SVC-06）

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v -k "item_service" tests/test_services.py
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
collecting ... collected 13 items / 12 deselected / 1 selected                                

tests/test_services.py::test_item_service_holding_using_and_expiration PASSED [100%]

======================= 1 passed, 12 deselected in 0.18s =======================
```

---

## 5. 架构边界（B1 / B2 / B3 / B4 / B5）结果

执行命令：
```bash
. .venv/bin/activate && python -m pytest -v tests/test_boundaries.py
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
collecting ... collected 6 items                                                              

tests/test_boundaries.py::test_b3_boundary_kernel_and_services_no_platform_imports PASSED [ 16%]
tests/test_boundaries.py::test_b1_boundary_plugins_no_platform_imports PASSED [ 33%]
tests/test_boundaries.py::test_b4_boundary_plugins_no_direct_orm_models PASSED [ 50%]
tests/test_boundaries.py::test_b2_boundary_platform_no_business_semantics PASSED [ 66%]
tests/test_boundaries.py::test_httpx_restricted_to_platform_layer PASSED [ 83%]
tests/test_boundaries.py::test_b5_boundary_plugins_no_raw_sql_drivers PASSED [100%]

============================== 6 passed in 0.07s ===============================
```

| 边界 | 规则要求 | 实现与自动检查方式 | 检查结果 |
|---|---|---|---|
| **B1** | `plugins/` 不得引用平台层符号 | AST 静态扫描 `plugins/`，禁止 import `core.platform`、`httpx` 及平台底层库 | **PASSED** |
| **B2** | 平台层不得出现业务语义词汇 | 静态扫描 `src/zxtg/core/platform/tg/`，禁止出现“签到/金币/checkin/sign_in/coin/gold/impression/好感度” | **PASSED** |
| **B3** | 内核/服务层不得感知 Telegram 平台 | AST 静态扫描 `core/kernel` 与 `core/services`，禁止 import `core.platform`、`httpx`、`telegram` 等 | **PASSED** |
| **B4** | 插件不得直接操作 ORM 模型 | AST 静态扫描 `plugins/`，禁止 direct import `zxtg.models` 或 `tortoise.models` | **PASSED** |
| **B5** | 插件不得直接引用底层数据库驱动 | AST 静态扫描 `plugins/`，禁止 import `sqlite3`, `aiosqlite`, `tortoise.transactions` 等 | **PASSED** |
| **HTTPX** | `httpx` 仅允许在 platform 层使用 | AST 静态扫描全仓库非平台层，禁止在平台层外 import `httpx` | **PASSED** |

---

## 6. 代码行数与质量约束检查

1. **权限与限制逻辑代码量（硬约束 <= 700 行）**：
   ```bash
   wc -l src/zxtg/core/kernel/guards.py \
         src/zxtg/core/kernel/pipeline.py \
         src/zxtg/core/services/limit_service.py \
         src/zxtg/core/services/permission_service.py
   ```
   **输出结果：**
   - `guards.py`: 296 行
   - `pipeline.py`: 66 行
   - `limit_service.py`: 213 行
   - `permission_service.py`: 83 行
   - **合计：658 行**（完全满足 `<= 700 行` 要求，安全余量 42 行）。
2. **核心库总代码量（硬约束 <= 6000 行）**：
   - `src/zxtg` 目录下所有 `.py` 文件行数总计为 **5,380 行**（完全满足 `<= 6000 行` 要求，安全余量 620 行）。
3. **单文件函数数约束（硬约束 <= 30）**：
   - 全库单个文件函数/方法数峰值为 **23 个**（位于 `src/zxtg/core/context.py`），全库满足 `<= 30`。
4. **代码无 print 约束**：
   - `grep -rn "print(" src/` 输出为 **0 处**。
5. **日志无 Token 泄露**：
   - 遵循 M2 的脱敏规范，脱敏过滤层处于最底层，全库日志均不含 token 片段。

---

## 7. BLOCKED 清单

依据任务书与 M2 边界要求，本轮**禁止接触真实 Telegram 网络**（避免与宿主 gateway bot `@esmodtnq_bot` 争夺 updates 产生事故）。以下涉及真实外部环境的项目如实标记为 BLOCKED：

| 项目 | 状态 | 阻塞原因 | 解锁条件 |
|---|---|---|---|
| 真实 Telegram 用户/群数据联调 | **BLOCKED** | 离线开发阶段无真实网络交互，防止与宿主 bot 冲突 | 用户提供独立测试 Bot Token 并在隔离实机部署 |
| 真实 Telegram 群管理员权限同步探测 | **BLOCKED** | 需向真实 Telegram 群添加 Bot 并实测管理员权限回显 | 待真实联调环境具备 |

---

## 8. 与设计的偏差与实现决策

1. **扣费与成功绑定架构落地（`GuardCost` 凭据 + `Dispatch` 扣除）**：
   - 管道次序严格遵守 `test_pipeline_order_and_absence_of_priorities`（`GuardCost` 必须在位置 6，`Dispatch` 在位置 8）。
   - 实现决策：`GuardCost` 执行余额充裕度校验，若不足立即短路 `DENY`；若充裕则在 `CallContext` 挂载 `_pending_cost` 快照凭据。实际原子扣除推迟至 `Dispatch` 调用 `handler` 成功返回后执行。如若 `handler` 执行中途抛出异常或后续 Guard 拦截，扣费绝不发生，严格保证了 FR-AUTH-09（“成功才扣、失败不扣”）。
2. **高频计数内存聚合与双轨查询**：
   - 统计写入仅更新内存 `_buffer[(plugin, user, group)] += count`，实现完全的内存 O(1) 聚集，避免单次调用即触发 SQLite 事务。
   - 查询时提供 `get_total_count` 双轨透视（数据库落盘数 + 内存缓冲数），保证数据在落盘前后的一致性。
3. **`UserConsole` 扩展 `level` 字段**：
   - 满足 FR-SVC-01 对用户个人等级的读写需求，默认值设为 0。与 Telegram 角色（OWNER=100/ADMIN=10/MEMBER=0）在 `permission_service` 中融合计算。
4. **移除 `Dispatch` 伪造扣费 `else` 分支与无调用方 `get_group_level`（M3FIX）**：
   - 原 `Dispatch` 中无 DB 时用 `max(0, gold - cost)` 内存修改 `ctx._user` 属于静默假扣费，违反 FR-AUTH-06 与 NFR-16，现已彻底删除该 else 分支，改为在无数据库时直接抛出 `RuntimeError`，杜绝假装成功。
   - 原 `get_group_level` 缺失时静默返回 5 无规格依据，且全仓无任何调用方，直接删除以清除隐式默认值。

---

## 9. 未解决问题

- **无**。M3 阶段所要求的用户服务、群服务、金币原子服务、好感度原子服务、权限映射与覆盖、道具最小可用服务、数据加固（WAL/busy_timeout/ integrity_check/高频缓冲/DAO 裸 SQL 防护/幂等性）全部交付，98 项测试全绿。

---

## 10. M3FIX 复核修正记录

### 10.1 三项静默兜底问题修正与关键 diff

#### 1. `Dispatch` 假扣费 `else` 分支彻底清除
- **位置**：`src/zxtg/core/kernel/guards.py`，`Dispatch()`
- **原写法**：当 `_pending_cost` 存在但 `Tortoise._inited` 为 False 时，走 `else` 分支通过 `max(0, ctx.user.gold - cost_gold)` 伪造内存中的 `UserView` 写回 `ctx._user`，造成无 DB 写入却假装扣费成功（实证：无 DB 时 gold 500->450 却零写库）。
- **新写法**：彻底删除整个 `else` 分支；若 `pending_cost` 存在且 `not Tortoise._inited`，直接抛出 `RuntimeError("扣费需要已初始化的数据库")`，不留任何 try-except、pass 或日志兜底。
- **关键 diff**：
```diff
@@ -259,33 +259,27 @@ async def Dispatch(ctx: CallContext) -> Verdict:
     # If handler succeeds without exception, apply pending cost deduction (FR-AUTH-09)
     pending_cost = getattr(ctx, "_pending_cost", None)
     if pending_cost:
+        if not Tortoise._inited:
+            raise RuntimeError("扣费需要已初始化的数据库")
         cost_gold, cost_imp, plugin_key = pending_cost
-        if Tortoise._inited:
-            from zxtg.core.services.gold_service import gold_service
-            from zxtg.core.services.impression_service import impression_service
-
-            if cost_gold > 0:
-                ok, msg = await gold_service.change_gold(ctx.user.id, -cost_gold, f"cost_{plugin_key}")
-                if not ok:
-                    return DENY(reason=msg, tip="金币扣除失败")
-
-            if cost_imp > 0.0:
-                ok, msg = await impression_service.change_impression(ctx.user.id, -cost_imp, f"cost_{plugin_key}")
-                if not ok:
-                    return DENY(reason=msg, tip="好感度扣除失败")
-
-            current_gold = await gold_service.get_gold(ctx.user.id)
-            current_imp = await impression_service.get_impression(ctx.user.id)
-            ctx._user = UserView(
-                id=ctx.user.id, level=ctx.user.level, gold=current_gold, impression=current_imp
-            )
-        else:
-            ctx._user = UserView(
-                id=ctx.user.id,
-                level=ctx.user.level,
-                gold=max(0, ctx.user.gold - cost_gold),
-                impression=max(0.0, ctx.user.impression - cost_imp),
-            )
+        from zxtg.core.services.gold_service import gold_service
+        from zxtg.core.services.impression_service import impression_service
+
+        if cost_gold > 0:
+            ok, msg = await gold_service.change_gold(ctx.user.id, -cost_gold, f"cost_{plugin_key}")
+            if not ok:
+                return DENY(reason=msg, tip="金币扣除失败")
+
+        if cost_imp > 0.0:
+            ok, msg = await impression_service.change_impression(ctx.user.id, -cost_imp, f"cost_{plugin_key}")
+            if not ok:
+                return DENY(reason=msg, tip="好感度扣除失败")
+
+        current_gold = await gold_service.get_gold(ctx.user.id)
+        current_imp = await impression_service.get_impression(ctx.user.id)
+        ctx._user = UserView(
+            id=ctx.user.id, level=ctx.user.level, gold=current_gold, impression=current_imp
+        )
```

#### 2. `group_service.get_group_level` 静默默认值 5 清除
- **位置**：`src/zxtg/core/services/group_service.py`
- **原写法**：`return group.level if group else 5`，凭空赋予未知群等级 5，无设计规格依据。
- **新写法**：全工程经搜索核实无任何调用方，直接彻底删除该方法，不留任何 `or 5` / `else 5` / `getattr(..., 5)`。
- **关键 diff**：
```diff
@@ -89,5 +81,0 @@ class GroupService:
-    async def get_group_level(self, chat_id: str | int) -> int:
-        """Read group permission level (default 5 if not found)."""
-        group = await self.get_group(chat_id)
-        return group.level if group else 5
-
```

#### 3. `_init_group_switches` 吞异常包裹清除
- **位置**：`src/zxtg/core/services/group_service.py`，`_init_group_switches()`
- **原写法**：`except Exception as e: logger.warning(...)` 吞掉异常，导致开关创建失败时群仍静默创建成功，违反 FR-PLG-09 与不静默失败原则。
- **新写法**：完全移除 `try/except` 包裹，让异常直接向上传播到 `get_or_create_group` 调用方。
- **关键 diff**：
```diff
@@ -74,15 +74,11 @@ class GroupService:
     async def _init_group_switches(self, group_id: str) -> None:
         """Populate default group plugin switches for registered plugins."""
-        try:
-            plugins = await PluginInfo.all()
-            for p in plugins:
-                existing = await GroupPluginSwitch.get_or_none(
-                    group_id=group_id, plugin_key=p.module
-                )
-                if existing is None:
-                    await GroupPluginSwitch.create(
-                        group_id=group_id,
-                        plugin_key=p.module,
-                        status=p.default_status,
-                    )
-        except Exception as e:
-            logger.warning("Failed to initialize switches for group %s: %s", group_id, e)
+        plugins = await PluginInfo.all()
+        for p in plugins:
+            existing = await GroupPluginSwitch.get_or_none(
+                group_id=group_id, plugin_key=p.module
+            )
+            if existing is None:
+                await GroupPluginSwitch.create(
+                    group_id=group_id,
+                    plugin_key=p.module,
+                    status=p.default_status,
+                )
```

---

### 10.2 新增测试原始 pytest 输出

执行命令：
```bash
.venv/bin/pytest tests/test_services.py -k "test_dispatch_cost_requires_initialized_db or test_group_init_switch_failure_propagates" -v
```
**终端原始输出：**
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 15 items / 13 deselected / 2 selected                                

tests/test_services.py::test_dispatch_cost_requires_initialized_db PASSED [ 50%]
tests/test_services.py::test_group_init_switch_failure_propagates PASSED [100%]

======================= 2 passed, 13 deselected in 0.17s =======================
```

---

### 10.3 全量 `pytest -q` 原始输出

执行命令：
```bash
.venv/bin/pytest -q
```
**终端原始输出：**
```text
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 1.12s
```
**最终 passed 数字**：**100 passed**（原 98 项 + 新增 2 项，全部通过）。

---

### 10.4 其它 fallback / 静默兜底残留核查结论

还有无其它 fallback / 静默兜底残留：**无**。
（全工程经 AST 及正则扫描，除规格明确要求的 TG 用户名缺失向全名/ID 规范回退 FR-TG-08 外，无任何兜底兼容层、伪造成功或吞异常行为）。

