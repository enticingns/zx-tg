# NEXT-TASK-M1：内核（注册 / 校验 / 配置三级 / 限制器 / 任务 / 命令广播）

> 本文件是**当前唯一权威指令**。设计细节以 `docs/zx-tg-design-v3.md`（§5.2–§5.11）与 `docs/zx-tg-requirements-v1.0.md`（FR-PLG / FR-CMD / FR-LIM / FR-CFG / FR-TSK）为准。
> **M0 已完成并入库**（commit `d50cbe2`）。本轮只做 M1，**不要接真实 Telegram**（那是 M2）。

---

## 0. 先修正 M0 遗留的契约问题（必须做）

M0 的 `plugin_info` 与设计口径有偏差，**本轮先修正**：
- 上游实测为 **id + 22 个字段 + 1 个反向关联**；设计稿/任务书写的「26 字段」是**设计文档口径**。
- M0 的模型**多出了 `usage` / `superuser_help`**，超出上游 `plugin_info` schema。
- **处理方式**：把 `usage` / `superuser_help` 从 `PluginInfo` 模型中**移除**（它们属于 Manifest 的**声明式元数据**，不入库），使模型字段与上游逐字一致。在 `M1-REPORT.md` 写明这一修正，并更新 `tests/test_models.py` 的字段断言为**上游实测口径**（id + 22 + 反向关联）。
- 若你认为某字段确需入库，必须先说明理由并在报告中单独列出**契约变更登记**（对照 SRS 附录 A 的格式）。

---

## 1. 本轮交付物

### 1.1 Manifest 契约（设计 §5.3 / FR-PLG-12）
`src/zxtg/core/kernel/manifest.py`：
```python
@dataclass(frozen=True)
class PluginManifest:
    key, name, version, author, description, usage,
    superuser_help=None, introduction=None, precautions=None,
    plugin_type=PluginType.NORMAL, menu_type="功能", is_show=True, parent=None,
    level=5, admin_level=None, default_status=True, limit_superuser=False,
    cost_gold=0, impression=0.0,
    cmds=(), aliases=frozenset(),
    configs=(), limits=(), tasks=(), events=(),
    requires_core=">=1.0,<2.0", requires=(), requires_services=(),
    bot_permissions=frozenset(),
    ignore_prompt=False, ignore_statistics=False,
```
以及 `Cmd` / `Param` / `ConfigSpec` / `LimitSpec` / `TaskSpec` / `EventSpec`（设计 §5.4 / §5.7 / §5.8 / §5.9 / §5.10）。
- `version` 必须 **SemVer**，写校验（FR-PLG-13）。
- `ConfigSpec` 必须含 `type` / `default` / `help` / `scope` / `min_value` / `max_value` / `choices`，**禁止 Callable**（FR-CFG-03/04）。
- `LimitSpec` 必须含 `period`（FR-LIM-02，这是相对上游的补洞）。

### 1.2 注册与校验（§5.11 ① ② / FR-PLG-01~09）
`registry.py` 补齐 `discover → validate → resolve → register`：
- **discover**：扫描 `plugins/*/plugin.py` 与 `plugins_ext/*/plugin.py`。
- **validate（失败即抛，启动失败）**：key 格式 `^[a-z][a-z0-9_]{2,31}$` 且全局唯一；命令 `key`/`slash`/`pattern` 冲突；`requires` 缺失与成环；`requires_core` SemVer 不匹配；配置 key 格式；`callback_data` ≤64 字节（FR-TG-11）；中文 `pattern` 前缀冲突（FR-CMD-09）。
- **降级为 WARN 不失败**：slash 数 >100（FR-CMD-04）、插件目录缺 `plugin.py`、`bot_permissions` 在部分群缺失（M2 才有群，本轮做结构预留）。
- **resolve**：依赖 + 声明顺序拓扑排序。
- **register 写库**：**不得覆盖** `status`/`default_status`/`load_status`，仅 upsert 结构性字段（FR-PLG-08 ★ 易踩坑）。

### 1.3 配置三级（§5.7 / FR-CFG-01~07）
`src/zxtg/core/services/config_service.py`：`default_value → 全局 → 群级` 覆盖；写入前按 `type`/范围/`choices` 校验，非法拒绝并返回明确错误；提供 **JSON Schema 导出**（FR-CFG-05）。

### 1.4 限制器（§5.8 / FR-LIM-01~06）
`src/zxtg/core/services/limit_service.py`：CD/COUNT/BLOCK 三种；COUNT **必须有周期**（滚动窗口，非定时扫描）；`watch_type` USER/GROUP/ALL；`check_type` PRIVATE/GROUP/ALL；拒绝走 `result` 文案。接到 `GuardLimit`。

### 1.5 任务调度（§5.9 / FR-TSK-01~07）
`src/zxtg/core/kernel/scheduler.py`：cron + interval；`misfire_grace_time` **必填**（防重启雪崩）；`max_instances`；群级开关；触发走统一发送出口（真实限流 M2 才有，本轮留接口）。
> 依赖：`apscheduler` 不在 M0 白名单。**若需引入，先确认其体积与必要性并写进报告**；否则用 stdlib `asyncio` 实现最小调度（推荐，保持轻量）。

### 1.6 命令广播（§5.5 / FR-CMD-01~06）
`src/zxtg/core/kernel/commands.py`：
- 双轨归一化：`pattern`(中文) 与 `slash`(英文) → 同一 `CommandRef(key)`。
- slash 自动命名 `<plugin_key>_<action>`（FR-CMD-05）。
- **100 条截断**：按 `PluginType` 优先级 NORMAL > ADMIN > SUPERUSER > HIDDEN，超出降级为 Text 轨且**功能不丢**，WARN 列出被降级项（FR-CMD-04）。
- `setMyCommands` 的实际调用留 M2，本轮产出**计算好 scope 分组的结果结构**并单测。

### 1.7 管道接线
把 `MergeConfig` / `GuardSwitch` / `GuardLimit` / `GuardCost` 从 M0 的占位替换为真实实现，`ResolveContext` 接真实 DB 读用户/群。

---

## 2. 硬性约束（同 M0，违反即返工）
1. Python ≥ 3.11；依赖仅白名单 `tortoise-orm, aiosqlite, pydantic>=2, pytest, pytest-asyncio`（如需加包，必须在报告里论证，且不得引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi）。
2. 不引入任何 fallback / patch / guard-of-guard 层（FR-AUTH-06 / NFR-16）。
3. 权限与限制逻辑总量目标 **≤700 行**（FR-AUTH-05）；核心 ≤6000 行（NFR-14）。本轮给出计数。
4. 生产代码禁 `print()`；日志不得含 `TELEGRAM_TOKEN`。
5. 单文件函数数 ≤30（NFR-17）。
6. 不改 `docs/` 与 `NEXT-TASK-M1.md`；不要回退 M0 已通过的东西（tests 里的既有断言不得放宽）。
7. 不提交 `data/`、`.venv/`、`*.db`、`*.log`。

---

## 3. 真跑真验证（把原始输出抄进报告）
```bash
. .venv/bin/activate
python -m pytest -q                                   # 全绿，含 M0 的 30 条
python -m pytest -q tests/test_registry.py tests/test_config.py tests/test_limits.py tests/test_commands.py
```
**必须新增并被验证的测试**（每条都要有对应用例）：
- key 冲突 / 命令冲突 / pattern 前缀冲突 → 启动失败且打印冲突双方
- `requires` 成环 → 失败；`requires_core` 不匹配 → 失败
- **配置不复活**：群内关闭插件 → 重跑 register → 该群仍关闭（FR-PLG-08 / 验收 A3）
- **100 命令降级**：构造 120 条命令，第 101 条降级为 Text 但**仍可触发**（验收 A4）
- CD 生效、COUNT 周期窗口正确（过窗口后重置）、BLOCK 永久拒绝
- 配置三级覆盖正确；非法值被拒
- `callback_data` >64 字节 → 启动失败

---

## 4. 如实标 BLOCKED
- 真实 Telegram `setMyCommands` / 收发 → M2。
- 限流器实际退避 → M2。
- 任何装不上/不可行的项，标 BLOCKED 并说明，**不要谎报**。

---

## 5. 交付格式
写 **`M1-REPORT.md`**：环境、变更文件清单（含行数）、核心结构落点、§3 每条验证的**原始输出**、契约修正说明（§0）、权限+限制代码行数计数、BLOCKED、与设计的偏差/实现决策、未解决问题。
报告写完即停，**不要开始 M2**。
