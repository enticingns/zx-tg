# NEXT-TASK-M3FIX：M3 静默兜底清除（窄范围修正）

> 当前唯一权威指令。**只做下面 3 项修正 + 配套测试 + 报告补充**，不得扩大范围，不得动其它已通过代码。
> 基线：`5beaa61` + M3 工作区产出（98 tests passed）。

---

## 0. 背景：为什么打回

M3 交付的多数内容已通过复核（98 tests、B1–B5、WAL/busy_timeout、原子扣费、缓冲计数、权限映射均真实有效）。但发现 **3 处 M3 新引入的静默兜底**，违反 `FR-AUTH-06`（禁止任何 fallback / patch / guard-of-guard 兼容层）与 `NFR-16`（不存在任何 fallback / patch 兼容层文件），也违反设计 §5.12「不静默」原则。

已实证的问题（复核方脚本输出）：

```
verdict: Verdict(ALLOW)
gold after: 450          ← 金币被"扣"了
Tortoise._inited: False  ← 但数据库根本没初始化，一分钱没真扣
```

---

## 1. 必须修正的三项

### 1.1 `Dispatch` 的假扣费 else 分支（**最高优先级**）

位置：`src/zxtg/core/kernel/guards.py`，`Dispatch()` 内 `if pending_cost:` 块。

现状：`if Tortoise._inited:` 走真扣费；**`else:` 分支用 `max(0, ctx.user.gold - cost_gold)` 伪造一个"已扣费"的 `UserView` 写回 `ctx._user`**。这在无数据库时让调用方以为扣费成功，实际没有任何流水、没有持久化——是典型的"假装成功"。

要求：
1. **删除整个 `else` 分支**，不得用任何等价形式代替（不得改为 try/except 吞掉、不得改为 `pass`、不得改为日志后继续）。
2. 若 `_pending_cost` 存在且 `Tortoise._inited` 为 False，**直接抛 `RuntimeError`**，消息明确说明"扣费需要已初始化的数据库"，让问题当场暴露。
3. 真扣费路径逻辑保持不变（成功才扣、余额不足 DENY、失败不扣）。
4. 报告 §8 新增一条偏差登记，说明该 else 分支已移除及原因。

### 1.2 `group_service.get_group_level` 的静默默认值 5

位置：`src/zxtg/core/services/group_service.py`。

现状：群不存在时 `return group.level if group else 5`——凭空返回权限等级 5，等于给未知群静默授予等级。设计 §4.2 明确 `member/restricted → MEMBER 0 ← 受限于 GroupConsole.level 覆盖`，没有任何"未知群默认 5"的规格依据。

要求：
1. 该方法当前**无任何调用方**（已核实），直接**删除**该方法，消除这个静默默认。
2. 如你判断必须保留（例如为后续里程碑预留），则群不存在时必须返回 `0`，并在报告 §8 说明理由。**但优先选择删除**。
3. 不得留下 `or 5` / `else 5` / `getattr(..., 5)` 之类等价写法。

### 1.3 `_init_group_switches` 吞异常

位置：`src/zxtg/core/services/group_service.py`，`_init_group_switches()`。

现状：`except Exception as e: logger.warning(...)` —— 群初始化时若插件开关批量创建失败，**入口函数仍然返回成功**，群看起来建好了但开关是缺的。违反 `FR-PLG-09`（入群按 `default_status` 初始化开关）与设计「不静默失败」。

要求：
1. **删除 try/except 包裹**，让异常向上传播（`get_or_create_group` 的调用方能感知失败）。
2. 不得改为 `logger.error` 后继续，不得返回部分成功。

---

## 2. 配套测试（必须新增，并真跑）

在 `tests/test_services.py` 新增，命名清晰：

1. `test_dispatch_cost_requires_initialized_db`：不初始化 DB、构造带 `cost_gold` 的插件跑 `run_pipeline`，断言 **抛 `RuntimeError`**（或你定义的具体异常类型），且**不得**出现"ALLOW 且金币变化"的旧行为。跑前后断言 `ctx.user.gold` 未被人为改写。
2. `test_group_init_switch_failure_propagates`：用 monkeypatch 让 `PluginInfo.all()` 或 `GroupPluginSwitch.create()` 抛异常，断言 `get_or_create_group` **抛出**而不是静默返回。
3. 若 1.2 选择保留方法，则加 `test_get_group_level_unknown_group_returns_zero`。

同时确保：
- 原有 98 项测试**全部仍然通过**，不得放宽任何既有断言。
- 若 `test_pipeline.py` 因删除 else 分支而受影响，修的是**测试的 setup**（补 DB 初始化），不是把产品代码退回去。

---

## 3. 报告更新

在 `M3-REPORT.md` 末尾新增 `## 10. M3FIX 复核修正记录`，包含：
- 三项问题各自的位置、原写法、新写法（贴关键 diff 片段）。
- 新增测试的**原始 pytest 输出**（不要编造，直接抄终端）。
- 全量 `pytest -q` 的原始输出与最终 `N passed` 数字。
- 明确写一句：还有无其它 fallback / 静默兜底残留（如无则写"无"）。

---

## 4. 硬约束（与 M3 相同，不放松）

- 依赖仍仅 `tortoise-orm` / `aiosqlite` / `pydantic>=2` / `httpx` / `pytest` / `pytest-asyncio`；禁 `nonebot2` / `aiogram` / `python-telegram-bot` / `playwright` / `fastapi` / `uvicorn`。
- 边界 B1/B2/B3/B4/B5 必须继续通过（`tests/test_boundaries.py`）。
- 权限+限制逻辑 ≤700 行；核心 ≤6000 行；单文件函数数 ≤30；生产代码禁 `print()`；日志不含 token。
- 不接真实 Telegram、不碰真实网络。
- 不改 `docs/`、`README.md`、任何 `NEXT-TASK-*.md` 既有内容。
- 不提交 `data/` / `.venv/` / `*.db` / `*.log` / `.env` / `*token*`。

---

## 5. 完成标准

全部满足才算完成：
1. 三处静默兜底已按上面要求消除（`grep` 不到旧写法）。
2. 新增测试 3 条（或 2 条，取决于 1.2 的选择）存在且通过。
3. 全量 `pytest -q` 全绿，数字 ≥ 100（98 + 新增），原始输出已抄进报告。
4. `M3-REPORT.md` 有 `## 10. M3FIX 复核修正记录`，含真实输出。
5. 报告写完即停，**不要开始 M4**。
