#!/usr/bin/env bash
# ZX-TG M0 运行器：把 NEXT-TASK-M0.md 交给零重力（agy）执行。
# 依据 workshop-skill: antigravity-headless-delegation（重试穿透代理地区 400）。
set -u

export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
# Python 侧走同一代理
export PIP_PROXY=http://127.0.0.1:10809

cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m0-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M0.md 是当前唯一权威指令；docs/zx-tg-design-v3.md 与 docs/zx-tg-requirements-v1.0.md 是设计/需求规格。先通读 NEXT-TASK-M0.md，严格按它执行。

【本轮范围】只做 M0（奠基）：项目骨架、UnifiedEvent/CallContext/管道骨架、SQLite 模型、契约枚举、边界检查、冒烟脚本。不要做 M1/M2 的功能。

【硬约束】Python>=3.11（宿主 3.13.5，venv 里跑）；依赖只用白名单（tortoise-orm, aiosqlite, pydantic>=2, pytest, pytest-asyncio）；不要引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi；不得编造上游字段（枚举与 plugin_info 字段名必须与设计文档 §1.2 逐字一致）；不引入任何 fallback/patch 兼容层；生产代码禁 print（走 logging）；日志绝不含 TELEGRAM_TOKEN；单文件函数数<=30；不要改动 docs/ 与 NEXT-TASK-M0.md。

【必须真跑真验证】按任务书 §3 逐条执行：建 venv、pip install -e '.[dev]'、pytest 全绿、边界与契约测试通过、scripts/smoke_m0.py 输出含 pong 且退出码 0、'echo ping | python -m zxtg' 可读演示、wc -l 代码量基线。把原始输出写进报告。

【如实标 BLOCKED】真实 Telegram 收发属 M2，本轮不测、不要假装测过；工具装不上就标 BLOCKED。

【交付格式】写完 M0-REPORT.md（含环境、变更文件清单与行数、核心结构落点、验证命令原始输出、plugin_info 26 字段对照表、B1/B3 边界检查实现与结果、BLOCKED、与设计的偏差/实现决策、未解决问题）。报告写完即停，不要开始 M1。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M0 run start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M0 run exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M0-REPORT.md ] && [ -f src/zxtg/core/event.py ] && [ -f src/zxtg/core/kernel/pipeline.py ]; then
    echo "[$(date '+%F %T')] === M0 DONE: report + event.py + pipeline.py present ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M0 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
