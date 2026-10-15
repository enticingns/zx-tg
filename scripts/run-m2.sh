#!/usr/bin/env bash
# ZX-TG M2 运行器：Telegram 平台层（fake transport，不碰真实网络）
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m2-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M2.md 是当前唯一权威指令；docs/zx-tg-design-v3.md（§2.1 L1/§4.1/§4.3/§4.4/§5.5）与 docs/zx-tg-requirements-v1.0.md（FR-TG-01~16、FR-CMD-02/06）是细节规格。先通读 NEXT-TASK-M2.md，严格按它执行。

【前置】M0/M1 已完成并入库（最新 commit 369e947，tests 64 passed）。现有 src/zxtg/ 含 core/kernel（manifest/registry/config/limits/scheduler/commands）、core/platform/{base,console}.py、models/、plugins/ping。不要回退已通过内容，不要放宽既有断言。

【本轮范围】只做 M2：TG 平台层。薄 Bot API 客户端（httpx，可替换）+ 适配器（长轮询默认、退避重连、异常隔离、优雅停机）+ codec（update→UnifiedEvent，6 类 kind、角色 100/10/0、username 回退、message_id）+ per-chat 令牌桶限流器（20/分、Retry-After 退避、所有发送无旁路）+ get_chat_member 60s 缓存 + 群信息事件驱动 + 平台动作返回 bool 且缺权降级告警 + setMyCommands scope 接线 + >4096 分页 + 图片 >10MB 降级。

【最重要限制】**不要用真实 Telegram 网络**。禁止真实 token 发请求；禁止使用宿主 gateway 的 bot（@esmodtnq_bot，会抢更新造成事故）。所有验证走 FakeTelegramClient + fake clock。真实 TG 端到端一律标 BLOCKED（需专用测试 token），不要假装测过。

【硬约束】依赖仅白名单 + 新增 httpx（说明体积与必要性）；不得引入 aiogram/python-telegram-bot/nonebot2/playwright/fastapi/uvicorn；B1/B2/B3 边界继续为真（kernel/services 不得 import core.platform 或平台库；core/platform/tg 不得出现业务语义词汇；plugins 不得 import core.platform），tests/test_boundaries.py 必须继续通过且把 httpx 仅限 platform 层纳入检查；不引入 fallback/patch 层；权限+限制逻辑仍<=700 行、核心<=6000 行；生产代码禁 print；日志不含 token；单文件函数数<=30；不改 docs/ 与既有 NEXT-TASK-*.md；不提交 data/.venv/*.db/*.log。

【必须真跑真验证】按任务书 §3：pytest 全绿（之前 64，现应增加）；新增测试覆盖：codec 6 类 kind + 角色映射 + username 回退；per-chat 令牌桶节流 + Retry-After 退避后最终全送达；所有发送经限流器无旁路（用 client 打点断言）；setMyCommands 按 scope 参数正确 + >100 截断项不进 scope 但仍可 Text 触发；get_chat_member 60s 缓存命中；平台动作返回 bool 且缺权返回 False + 降级告警（不静默）；>4096 分页；图片 >10MB 降级。把原始输出抄进报告，不要编造。

【交付格式】写 M2-REPORT.md（环境含 httpx 版本与体积、变更文件清单含行数、核心结构落点、§3 每条验证原始输出、B1/B2/B3 实现与结果、BLOCKED 清单、与设计的偏差/实现决策、未解决问题）。报告写完即停，不要开始 M3。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M2 start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M2 exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M2-REPORT.md ] && [ -f src/zxtg/core/platform/tg/adapter.py ] && [ -f src/zxtg/core/platform/tg/codec.py ]; then
    echo "[$(date '+%F %T')] === M2 DONE (report + adapter + codec present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M2 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
