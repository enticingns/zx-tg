#!/usr/bin/env bash
# ZX-TG M0 续跑：承接已落盘的部分实现，只做补齐 + 真跑验证 + 报告。
# 注意：本脚本由 systemd-run 启动，不依赖发起它的 shell 存活。
set -u

export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1

cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m0-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M0.md 是当前唯一权威指令；docs/zx-tg-design-v3.md 与 docs/zx-tg-requirements-v1.0.md 是设计/需求规格。先通读 NEXT-TASK-M0.md，严格按它执行。

【这是续跑】上一轮被中断，以下已存在，**先核对再补齐，不要推倒重写**：
- src/zxtg/{__init__,config,logging_setup}.py
- src/zxtg/core/{__init__,event,context}.py
- src/zxtg/core/kernel/{__init__,enums,pipeline,guards,registry}.py
- src/zxtg/core/platform/{__init__,base,console}.py
- src/zxtg/core/services/__init__.py
- src/zxtg/models/{plugin_info,plugin_limit}.py
- pyproject.toml、.venv/（依赖已装好：tortoise-orm/aiosqlite/pydantic/pytest）
- plugins/ping/ 目录已建（可能不完整）

【本轮必须补齐（任务书 §1.1 清单里尚缺的）】
1. src/zxtg/__main__.py（入口，支持 'echo ping | python -m zxtg'）
2. src/zxtg/core/services/db.py（Tortoise 初始化 + 迁移执行入口）
3. src/zxtg/models/ 其余 8 个：group_console.py、user_console.py、logs.py(user_gold_log/user_impression_log)、switch.py(group_plugin_switch)、task_record.py、statistics.py、join_request.py、migration_record.py
4. plugins/ping/plugin.py + __init__.py（manifest + handler，证明契约可用）
5. tests/：test_event.py、test_pipeline.py、test_enums_contract.py、test_models.py、test_boundaries.py（B1/B3 静态扫描，见任务书 §1.6）
6. scripts/smoke_m0.py（非交互，断言输出含 pong，退出码 0）
7. pyproject.toml 补 [project.optional-dependencies] dev/lite
8. M0-REPORT.md

【关键：先核对已有实现是否正确】逐字对照 docs/zx-tg-design-v3.md §1.2：
- enums.py 的 PluginType/BlockType/LimitWatchType/LimitCheckType/PluginLimitType 成员名与值
- plugin_info.py 的 26 字段名
若有偏差，改正并说明。

【硬约束】Python>=3.11；依赖只用白名单（tortoise-orm, aiosqlite, pydantic>=2, pytest, pytest-asyncio）；不要引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi；不引入任何 fallback/patch 兼容层；生产代码禁 print（走 logging）；日志绝不含 TELEGRAM_TOKEN；单文件函数数<=30；不要改动 docs/ 与 NEXT-TASK-M0.md。

【必须真跑真验证】按任务书 §3 逐条执行（venv 已存在于 .venv，直接 . .venv/bin/activate）：
python -m pytest -q 全绿；tests/test_boundaries.py 与 tests/test_enums_contract.py 通过；python scripts/smoke_m0.py 输出含 pong 且 rc=0；echo ping | python -m zxtg 可读演示；wc -l 代码量基线。把原始输出抄进报告（不要编造）。

【如实标 BLOCKED】真实 Telegram 收发属 M2，本轮不测、不要假装测过；工具装不上就标 BLOCKED。

【交付格式】写完 M0-REPORT.md（含环境、变更文件清单与行数、核心结构落点、验证命令原始输出、plugin_info 26 字段对照表、B1/B3 边界检查实现与结果、BLOCKED、与设计的偏差/实现决策、未解决问题）。报告写完即停，不要开始 M1。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M0 resume start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M0 resume exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M0-REPORT.md ] && [ -f src/zxtg/__main__.py ] && [ -f scripts/smoke_m0.py ] && [ -d tests ]; then
    echo "[$(date '+%F %T')] === M0 DONE (report + main + smoke + tests present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M0 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
