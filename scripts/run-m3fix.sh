#!/usr/bin/env bash
# ZX-TG M3FIX 运行器：清除 M3 引入的静默兜底（窄范围修正）
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m3fix-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M3FIX.md 是当前唯一权威指令，先通读它，严格按它执行。

【背景】M3 已完成（工作区有产出，98 tests passed），但复核发现 3 处 M3 新引入的静默兜底，违反 FR-AUTH-06 与 NFR-16。本轮只清除这 3 处，不要扩大范围，不要重构其它模块。

【三项修正要点】
1. src/zxtg/core/kernel/guards.py 的 Dispatch()：pending_cost 存在时，若 Tortoise._inited 为 False，现在走 else 分支用 max(0, gold - cost) 伪造扣费并写回 ctx._user（已实证：无 DB 时 gold 500->450 却零写库）。必须删除整个 else 分支；不得用 pass / try-except 吞掉 / 日志后继续等任何等价形式；改为直接抛 RuntimeError，消息说明扣费需要已初始化的数据库。真扣费路径逻辑保持不变。
2. src/zxtg/core/services/group_service.py 的 get_group_level()：群不存在时 return ... else 5，凭空授予等级 5，无规格依据（设计 §4.2 是 member->0）。该方法当前无调用方，优先直接删除；若坚持保留则未知群必须返回 0，并在报告说明。
3. 同文件 _init_group_switches()：except Exception as e: logger.warning(...) 吞掉异常，导致群初始化看起来成功但开关缺失（违反 FR-PLG-09 与不静默原则）。删除 try/except 包裹，让异常向上传播；不得改 logger.error 后继续。

【必须新增测试】在 tests/test_services.py：
- test_dispatch_cost_requires_initialized_db：不初始化 DB、带 cost_gold 的插件跑 run_pipeline，断言抛 RuntimeError，且 ctx.user.gold 未被人为改写。
- test_group_init_switch_failure_propagates：monkeypatch 让 PluginInfo.all() 或 GroupPluginSwitch.create() 抛异常，断言 get_or_create_group 抛出而非静默返回。
- 若选择保留 get_group_level，加 test_get_group_level_unknown_group_returns_zero。
若 test_pipeline.py 因删除 else 分支受影响，改的是测试 setup（补 DB 初始化），不得把产品代码退回去。

【硬约束】不得放宽任何既有断言，原有 98 项必须仍全绿。依赖仍仅 tortoise-orm/aiosqlite/pydantic/httpx/pytest/pytest-asyncio。边界 B1-B5 继续通过。权限+限制 <=700 行、核心 <=6000 行、单文件函数数 <=30、生产代码禁 print、日志不含 token。不接真实 Telegram。不改 docs/ 与 NEXT-TASK-*.md。不提交 data/.venv/*.db/*.log。

【报告】在 M3-REPORT.md 末尾追加 '## 10. M3FIX 复核修正记录'：三项问题各自位置/原写法/新写法（贴关键 diff）、新增测试的原始 pytest 输出、全量 pytest -q 原始输出与最终 N passed 数字，并明确回答还有无其它 fallback/静默兜底残留（无则写'无'）。原始输出要抄终端，不要编造。

写完后即停，不要开始 M4。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M3FIX start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M3FIX exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if grep -q "## 10. M3FIX 复核修正记录" M3-REPORT.md 2>/dev/null && grep -q "test_dispatch_cost_requires_initialized_db" tests/test_services.py 2>/dev/null; then
    echo "[$(date '+%F %T')] === M3FIX DONE (report section + new tests present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M3FIX GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
