#!/usr/bin/env bash
# ZX-TG M3 运行器：核心服务层（user/group/gold/impression/permission + 数据加固）
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m3-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M3.md 是当前唯一权威指令；docs/zx-tg-design-v3.md（§2.1 L3/§3.4）与 docs/zx-tg-requirements-v1.0.md（FR-SVC-01~08、FR-DATA-01~09）是细节规格。先通读 NEXT-TASK-M3.md，严格按它执行。

【前置】M0/M1/M2 已完成并入库（最新 commit 1b3367c，tests 84 passed）。现有 core/kernel（manifest/registry/config/limits/scheduler/commands/guards/pipeline）、core/platform/tg（client/adapter/codec/rlmgr/cache/fake_client）、models/、plugins/ping。不要回退已通过内容，不要放宽既有断言。

【本轮范围】只做 M3：核心服务层。用户服务(TG 原生 user_id)、群服务(原生 chat_id)、金币服务(增减+流水+原子)、好感度服务(同)、权限服务(TG 角色→level 100/10/0 + 群级 level 覆盖 + limit_superuser 绕过)、道具服务(S 级，最小可用)、数据加固(WAL/busy_timeout>=5000/高频计数内存缓冲批量落盘/DAO 禁裸 SQL/显式迁移/启动损坏检测)。并把管道 GuardCost 接真实扣费(成功才扣、失败不扣)、GuardLevel 接 permission_service、ResolveContext 接真实 user/group 读写。

【硬约束】依赖仍仅 tortoise-orm/aiosqlite/pydantic/httpx/pytest/pytest-asyncio；不得引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi/uvicorn；边界 B1/B2/B3 继续为真——特别注意 core/services 不得 import core.platform 或 core.platform.tg（服务层只能吃内核层的枚举/结构），tests/test_boundaries.py 必须继续通过；不引入 fallback/patch 层；权限+限制逻辑仍<=700 行、核心<=6000 行；生产代码禁 print；日志不含 token；单文件函数数<=30；不改 docs/ 与既有 NEXT-TASK-*.md；不提交 data/.venv/*.db/*.log。

【必须真跑真验证】按任务书 §3：pytest 全绿（之前 84，现应增加）。必须覆盖：原子扣费(并发/交错不丢不超扣、余额不足拒绝且部分不扣)；扣费与成功绑定(handler 失败→不扣费)；每次变动落 gold/impression 流水且 reason 正确；权限 OWNER=100/ADMIN=10/MEMBER=0 + 群级 level 覆盖 + limit_superuser=False 时超管绕过；WAL + busy_timeout 生效(查 PRAGMA)；高频计数缓冲(N 次调用不产生 N 次写库，用打点断言，批量落盘后总数正确)；DAO 之外的裸 SQL 被捕获；群/用户初始化幂等。把原始输出抄进报告，不要编造。

【如实标 BLOCKED】真实 Telegram 相关同 M2 标 BLOCKED；不可行项如实标，不许谎报。

【交付格式】写 M3-REPORT.md（环境、变更文件清单含行数、核心结构落点、§3 每条验证原始输出、B1/B2/B3 结果、代码行数计数、BLOCKED、与设计的偏差/实现决策、未解决问题）。报告写完即停，不要开始 M4。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M3 start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M3 exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M3-REPORT.md ] && [ -f src/zxtg/core/services/user_service.py ] && [ -f src/zxtg/core/services/gold_service.py ]; then
    echo "[$(date '+%F %T')] === M3 DONE (report + user + gold services present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M3 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
