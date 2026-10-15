#!/usr/bin/env bash
# ZX-TG M1 运行器：内核（注册/校验/配置三级/限制器/任务/命令广播）
# 由 systemd-run 启动，不依赖发起 shell 存活。
set -u

export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1

cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m1-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M1.md 是当前唯一权威指令；docs/zx-tg-design-v3.md（§5.2–§5.11）与 docs/zx-tg-requirements-v1.0.md（FR-PLG/FR-CMD/FR-LIM/FR-CFG/FR-TSK）是细节规格。先通读 NEXT-TASK-M1.md，严格按它执行。

【前置：M0 已完成并入库（commit d50cbe2）】现有 src/zxtg/（core/{event,context}.py、core/kernel/{enums,pipeline,guards,registry}.py、core/platform/{base,console}.py、core/services/db.py、models/ 10 张表）、plugins/ping、tests/（30 条测试全绿）、scripts/smoke_m0.py、.venv（依赖已装）。**不要回退 M0 已通过的东西，不要放宽既有断言。**

【本轮范围】只做 M1（内核）：修 M0 契约遗留 → Manifest 契约 → 注册与校验 → 配置三级 → 限制器 → 任务调度 → 命令双轨与 100 条截断 → 把管道的 MergeConfig/GuardSwitch/GuardLimit/GuardCost 换成真实实现。不要接真实 Telegram（那是 M2）。

【第 0 步（必做）】修正 M0 契约偏差：把 usage / superuser_help 从 PluginInfo 模型移除（它们属 Manifest 声明式元数据，不入库），使模型与上游逐字一致；更新 tests/test_models.py 的字段断言为上游实测口径。理由写进报告。

【硬约束】Python>=3.11；依赖仅白名单（tortoise-orm, aiosqlite, pydantic>=2, pytest, pytest-asyncio），如需加包必须论证且不得引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi；不引入任何 fallback/patch/guard-of-guard 层；权限与限制逻辑目标<=700 行、核心<=6000 行，给出计数；生产代码禁 print；日志不含 TELEGRAM_TOKEN；单文件函数数<=30；不改 docs/ 与 NEXT-TASK-M1.md；不提交 data/.venv/*.db/*.log。

【必须真跑真验证】按任务书 §3：pytest 全绿（含 M0 的 30 条）；新增 test_registry/test_config/test_limits/test_commands 并全部通过。必须覆盖：key 冲突 / 命令冲突 / pattern 前缀冲突 → 启动失败并打印冲突双方；requires 成环 → 失败；requires_core 不匹配 → 失败；**配置不复活**（群内关闭插件后重跑 register 仍关闭）；**100 命令降级**（120 条命令，第 101 条降级为 Text 仍可触发）；CD 生效 / COUNT 周期窗口正确 / BLOCK 永久拒绝；配置三级覆盖；非法配置值被拒；callback_data>64 字节 → 启动失败。把原始输出抄进报告，不要编造。

【如实标 BLOCKED】真实 Telegram setMyCommands/收发、限流器实际退避均属 M2；装不上的工具标 BLOCKED。

【交付格式】写 M1-REPORT.md（环境、变更文件清单含行数、核心结构落点、§3 每条验证原始输出、契约修正说明、权限+限制代码行数计数、BLOCKED、与设计的偏差/实现决策、未解决问题）。报告写完即停，不要开始 M2。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M1 start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M1 exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M1-REPORT.md ] && [ -f src/zxtg/core/kernel/manifest.py ] && [ -f src/zxtg/core/kernel/commands.py ]; then
    echo "[$(date '+%F %T')] === M1 DONE (report + manifest + commands present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M1 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
