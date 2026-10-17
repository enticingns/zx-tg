#!/usr/bin/env bash
# ZX-TG M5FIX 运行器：补 B3 对 core/render 的边界覆盖 + 报告诚实性
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m5fix-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M5FIX.md 是当前唯一权威指令，先通读它，严格按它执行。只做这 2 项，不要扩大范围。

【问题1 必修：B3 边界测试漏覆盖 core/render】tests/test_boundaries.py 的 test_b3_boundary_kernel_and_services_no_platform_imports() 的 targets 只有 core/kernel 和 core/services，但 M5 新增了 src/zxtg/core/render/（6 个文件），grep -c render tests/test_boundaries.py == 0，等于核心层新增一整个子系统却零边界覆盖，而报告 §5 却宣称 B1-B5 全绿。
要求：(a) 把 src/zxtg/core/render 加进 B3 的 targets，与 kernel/services 同等对待。(b) 允许 playwright/jinja2/PIL 这类可选渲染引擎依赖在 render/ 内出现，但必须是函数内延迟导入——测试里要明确：禁止 render/ 顶层 import httpx / zxtg.core.platform* / telegram / aiogram；允许延迟 import playwright/jinja2/PIL，但必须加独立断言证明它们确实在函数体内而非模块顶层（否则核心安装会被迫装 Chromium）。(c) 不得缩短既有 B3 forbids 列表。
必须验证并贴原始输出：新增 test_b3_covers_render_subsystem 断言 render/ 确实被扫描；负向对照一：往 src/zxtg/core/render/text.py 顶层注入 import httpx → B3 必须 FAILED → 恢复 → PASSED；负向对照二：往 render/ 顶层注入 from zxtg.core.platform.tg.adapter import TgAdapter → 必须 FAILED。两段原始输出都贴。

【问题2 必修：报告漏报覆盖缺口】M5-REPORT.md §5 写'边界 B1-B5 持续全绿'，但 B3 当时不覆盖 render/，这不是全绿是没测。要求修正 §5 表述如实说明盲区已补齐，并新增 '## 11. M5FIX 修正记录'：问题描述与实证、改法关键 diff、新增测试原始输出、两张负向对照原始输出、全量 pytest 原始输出与最终 N 数，并明确回答修正后是否还有已知未解决项（有就列，无就写无，不得为好看写无，M4 已因漏报被打回一次）。

【硬约束】核心 dependencies 仍只有 tortoise-orm/aiosqlite/pydantic/httpx，playwright/jinja2/PIL 只能留在 optional-dependencies。不得引入 fallback/patch/兼容层。既有 146 项测试必须仍全绿，不得放宽任何既有断言（包括不许缩短 B3 的 forbids 列表）。核心<=6000 行（当前 5922，只剩 78 行余量，本次应主要是测试改动，若核心行数增加必须说明理由且仍<=6000）。权限+限制<=700 行（当前 656）；单文件函数数<=30；生产代码禁 print；日志不含 token。不接真实 Telegram。不改 docs/ 与既有 NEXT-TASK-*.md。不提交 data/.venv/*.db/*.log。

报告写完即停，不要开始 M6。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M5FIX start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M5FIX exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if grep -q "## 11. M5FIX 修正记录" M5-REPORT.md 2>/dev/null && grep -q "test_b3_covers_render_subsystem" tests/test_boundaries.py 2>/dev/null; then
    echo "[$(date '+%F %T')] === M5FIX DONE (report section + b3 render test present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M5FIX GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
