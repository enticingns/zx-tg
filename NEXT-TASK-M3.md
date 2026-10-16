# NEXT-TASK-M3：核心服务层（user / group / gold / impression / permission）

> 当前唯一权威指令。细节见 `docs/zx-tg-design-v3.md` §2.1 L3 / §3.4 与 `docs/zx-tg-requirements-v1.0.md` FR-SVC-01~08、FR-DATA-01~09。
> M0/M1/M2 已完成并入库（最新 `1b3367c`，84 tests）。本轮只做 M3，**不接真实 Telegram**（M2 的边界同样适用：不碰真实网络）。

---

## 1. 本轮交付物

### 1.1 用户服务 `core/services/user_service.py`（FR-SVC-01/07）
- 唯一用户标识 = **TG 原生 `user_id`**（不做二次编码，FR-SVC-07）。
- 读/写：level、gold、impression；`username` 可为 None → 显示回退 `full_name`（FR-TG-08 在服务层也要成立）。
- `platform` 字段为常量（单平台，SRS 附录 A 已定）。

### 1.2 群服务 `core/services/group_service.py`（FR-SVC-04/08）
- 群 ID = **TG 原生 `chat_id`**（FR-SVC-08）。
- 维护：`chat_id`、标题、成员数、`last_active`、`level`（群权限等级，配合 FR-AUTH-11）。
- 入群初始化：新群记录按 `default_status` 处理插件开关（注意与 M1 的 FR-PLG-09 一致）。

### 1.3 金币服务 `core/services/gold_service.py`（FR-SVC-02/05）
- 增减 + **流水记录**（`user_gold_log`：user_id / amount / reason / create_time）。
- **原子性**：禁止「读-算-写」非原子序列（FR-SVC-05）；用 `F()` 表达式或事务保证。
- 余额不足时**拒绝并返回明确结果**，不得透支（超出部分不扣）。

### 1.4 好感度服务 `core/services/impression_service.py`（FR-SVC-03/05）
- 同金币：增减 + 流水（`user_impression_log`）+ 原子性。

### 1.5 权限服务 `core/services/permission_service.py`（FR-AUTH-11 / §4.2）
- TG 角色 → 内部 level：`creator→OWNER(100)`、`administrator→ADMINISTRATOR(10)`、`member/restricted→MEMBER(0)`，再叠加群级 `GroupConsole.level` 覆盖（FR-AUTH-11）。
- 提供 `can_execute(user, group, manifest) -> bool` 供 `GuardLevel` 使用。
- `limit_superuser=False` 时超级用户绕过该插件的限制与开关（FR-AUTH-08，与 M1 的 GuardSwitch/GuardLimit 对齐）。

### 1.6 道具服务（FR-SVC-06，优先级 S）
- 持有 / 使用 / 过期处理；若时间不足可先给最小可用实现 + 说明。

### 1.7 数据层加固（FR-DATA-01~09）
- SQLite **WAL** + `busy_timeout>=5000`。
- **高频计数**（调用次数）走**内存缓冲 + 批量落盘**（FR-DATA-03）。
- 禁止插件裸 SQL，全部经 DAO（FR-DATA-04）。
- 迁移显式脚本，禁止运行时自动 ALTER（FR-DATA-05）。
- 启动时检测数据库损坏并给明确诊断（FR-DATA-09，优先级 S）。

### 1.8 管道接线
把 `GuardCost` 接真实金币/好感度扣费（**成功才扣、失败不扣**，FR-AUTH-09），`GuardLevel` 接 permission_service，`ResolveContext` 接 user/group 服务真实读写。

---

## 2. 硬性约束
1. 依赖仍仅 `tortoise-orm, aiosqlite, pydantic>=2, httpx, pytest, pytest-asyncio`。不得引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi/uvicorn。
2. 边界继续为真：B1/B2/B3；`core/services` 不得 import `core.platform` 或平台库（`tests/test_boundaries.py` 必须继续通过）。**注意**：M2 的 TG 平台层提供的是平台语义；服务层若需要角色/权限输入，只能吃**内核层的枚举/结构**，不得 import `core.platform.tg`。
3. 不引入 fallback / patch / guard-of-guard 层。
4. 权限与限制逻辑仍 ≤700 行；核心 ≤6000 行。
5. 生产代码禁 `print()`；日志不含 token；单文件函数数 ≤30。
6. 不改 `docs/` 与既有 `NEXT-TASK-*.md`；不得回退 M0–M2 已通过内容或放宽断言。
7. 不提交 `data/`、`.venv/`、`*.db`、`*.log`。

---

## 3. 真跑真验证（原始输出抄进报告）
```bash
. .venv/bin/activate
python -m pytest -q
```
**必须新增并验证**：
- **原子扣费**：并发/交错场景下金币不丢不超扣；余额不足拒绝且**部分不扣**
- **扣费与成功绑定**：handler 失败 → 不扣费（FR-AUTH-09）
- **流水**：每次变动都落一条 gold/impression log，reason 正确
- **权限**：OWNER=100 / ADMIN=10 / MEMBER=0；群级 level 覆盖生效；`limit_superuser=False` 时超管绕过（FR-AUTH-08）
- **WAL + busy_timeout** 生效（可查 `PRAGMA`）
- **高频计数缓冲**：N 次调用不产生 N 次写库（用计数打点断言），批量落盘后总数正确
- **插件裸 SQL 防护**：验证 DAO 之外的直接访问被测试捕获（边界/接口层）
- 群/用户初始化幂等（重复 ResolveContext 不重复建记录）

---

## 4. 如实标 BLOCKED
- 真实 Telegram 相关（同 M2）→ BLOCKED。
- 任何不可行项标 BLOCKED 并说明，不许谎报。

---

## 5. 交付格式
写 **`M3-REPORT.md`**：环境、变更文件清单（含行数）、核心结构落点、§3 每条验证**原始输出**、边界 B1/B2/B3 结果、代码行数计数、BLOCKED、与设计的偏差/实现决策、未解决问题。报告写完即停，**不要开始 M4**。
