#!/usr/bin/env bash
# ZX-TG M1 续跑（契约对齐修正）：只做 NEXT-TASK-M1FIX.md。
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m1fix-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M1FIX.md 是当前唯一权威指令（窄范围修正）。先通读它，严格按它执行。

【背景】M1 已完成（tests 64 passed），但独立复核发现 plugin_info 仍多出一个 description 字段，未与上游逐字对齐。

【本轮只做】按 NEXT-TASK-M1FIX.md：
1) 从 src/zxtg/models/plugin_info.py 移除 description 字段（上游无此列）。
2) 同步去掉 registry.py register_to_db 里写 description 的两处。
3) description 保留在 PluginManifest 中（不入库）。
4) tests/test_models.py 字段断言改为 23 项（id + 21 + 反向关联）。
5) 修正 M1-REPORT.md §2.1 的计数（上游=23，本项目=23）并在 §2.2 补 description 移除一行。
6) 全量复跑 pytest 必须全绿（此前 64 passed）。

【约束】不改 docs/、NEXT-TASK-M1.md、NEXT-TASK-M1FIX.md；不引入新依赖；不放宽既有断言；不引入 fallback/patch；不动 M0/M1 其它已通过内容。

【交付】把 §3 自检命令的原始输出追加到 M1-REPORT.md 末尾（§「M1FIX 复核输出」）。写完即停，不要做 M2。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M1FIX start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M1FIX exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  # done when description gone from model AND report mentions M1FIX
  if ! grep -q "description = fields\." src/zxtg/models/plugin_info.py 2>/dev/null && grep -q "M1FIX" M1-REPORT.md 2>/dev/null; then
    echo "[$(date '+%F %T')] === M1FIX DONE ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M1FIX GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
