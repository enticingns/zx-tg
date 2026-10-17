# NEXT-TASK-M5FIX：M5 边界覆盖缺口修正（窄范围）

> 当前唯一权威指令。基线：`f4818df` + M5 工作区产出（**146 tests passed**）。
> **只做下面 2 项**，不得扩大范围、不得重构已通过模块。

---

## 1. 问题 1（必修，真实缺口）：B3 边界测试未覆盖新增的 `core/render`

### 实证
`tests/test_boundaries.py` 的 `test_b3_boundary_kernel_and_services_no_platform_imports()` 只扫两个目录：

```python
targets = [
    PROJECT_ROOT / "src" / "zxtg" / "core" / "kernel",
    PROJECT_ROOT / "src" / "zxtg" / "core" / "services",
]
scanned_files = 0
```

而 M5 新增了 `src/zxtg/core/render/`（6 个文件）。`grep -c "render" tests/test_boundaries.py` → **0**。
也就是说：M5 往核心层加了一整个新子系统，**边界测试对它零覆盖**，报告 §5 却宣称「B1–B5 持续全绿」。

### 为什么这真的危险
本轮 `core/render/html.py` 里就有 `import playwright`（延迟导入，本身合法——它属于可选引擎）。
问题不在于这一处，而在于：**如果哪天有人往 `render/` 里塞一个 `import httpx` 或 `from zxtg.core.platform...`，B3 会毫无反应。**

### 要求
1. 把 `src/zxtg/core/render` 加进 B3 的 `targets` 列表（与 kernel/services 同等对待）。
2. **允许** `playwright` / `jinja2` / `PIL` 这类**可选渲染引擎依赖**在 `render/` 内出现——但必须是**函数内延迟导入**。请在测试里明确：
   - 禁止 `render/` 顶层（模块级）import `httpx` / `zxtg.core.platform*` / `telegram` / `aiogram`；
   - 允许延迟 import `playwright` / `jinja2` / `PIL`，但**加一条独立断言**证明它们确实在函数体内而非模块顶层（否则又会变成"核心安装被迫装 Chromium"）。
3. 不要为了让测试过而放宽既有 B3 规则（kernel/services 的 forbids 一条都不能少）。

### 必须的验证（原始输出抄进报告）
- `test_b3_covers_render_subsystem`：断言 `render/` 确实被扫描（例如扫描文件数 > 0，或直接断言 target 列表包含该目录）。
- **负向对照**：往 `src/zxtg/core/render/text.py` **顶层**注入 `import httpx` → B3 必须 FAILED → 恢复 → PASSED。贴两段原始输出。
- 第二个负向对照：往 `render/` 顶层注入 `from zxtg.core.platform.tg.adapter import TgAdapter` → 必须 FAILED。

---

## 2. 问题 2（必修，报告诚实性）：报告未披露此覆盖缺口

`M5-REPORT.md` §5 写「边界 B1–B5 持续全绿」，但 B3 当时并不覆盖 `render/`——这不是"全绿"，是"没测"。

要求：
1. 修正 §5 的表述，如实说明 B3 原只覆盖 kernel/services、M5 新增 render 后存在覆盖盲区，现已补齐。
2. 新增 `## 11. M5FIX 修正记录`：问题描述与实证、改法（贴关键 diff）、新增测试原始输出、两张负向对照原始输出、全量 pytest 原始输出与最终 N 数。
3. 明确回答：**修正后是否还有已知未解决项**。有就列，没有写"无"——但不得为好看写"无"（M4 已因漏报被打回一次）。

---

## 3. 硬约束（不放松）

- 依赖不变：核心 `dependencies` 仍只有 tortoise-orm / aiosqlite / pydantic / httpx；`playwright`/`jinja2`/`PIL` 只能留在 `optional-dependencies`。
- 不得引入 fallback / patch / 兼容层；不得有"库没初始化就假装成功"分支；不得有"写内存就算持久化"分支。
- 既有 146 项测试必须仍全绿，**不得放宽任何既有断言**（包括不许把 B3 的 forbids 列表缩短）。
- **核心 ≤6000 行**：当前 5922，只剩 78 行余量。本次修正应主要是测试改动，若核心行数增加必须说明理由且仍 ≤6000。
- 权限+限制 ≤700 行（当前 656）；单文件函数数 ≤30；生产代码禁 `print()`；日志不含 token。
- 不接真实 Telegram。
- 不改 `docs/`、`README.md`、既有 `NEXT-TASK-*.md`。
- 不提交 `data/` / `.venv/` / `*.db` / `*.log` / `.env` / `*token*`。

---

## 4. 完成标准

1. `core/render` 已被 B3 覆盖，且有测试明确断言这一点。
2. 两张负向对照都已做（顶层 httpx、顶层 platform import），贴原始输出。
3. 报告 §5 已如实修正，且有 §11 修正记录含真实输出。
4. 全量 `pytest -q` 全绿，数字 > 146。
5. 报告写完即停，**不要开始 M6**。
