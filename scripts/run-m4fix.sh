#!/usr/bin/env bash
# ZX-TG M4FIX 运行器：商店库存持久化 + 报告诚实性修正
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m4fix-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M4FIX.md 是当前唯一权威指令，先通读它，严格按它执行。只做这 2 项修正，不要扩大范围。

【问题1 必修：商店库存不持久化】复核方已实证：plugins/shop/plugin.py 的 _save_shop_items() 调 config_service.set_global()，而该方法只是 self._global_configs[key]=value 纯内存字典，config_service 无任何持久化方法。脚本验证：写入库存 7 后清空内存，读回 None。设计 §5.6 要求全局配置落到 core_config.yaml / DB，当前不满足 FR-CFG-01。
要求：(a) 让 SHOP_ITEMS 真正落库，重启后保留——推荐新增 src/zxtg/models/config.py 的 CoreConfig(key,value_json,plugin_key,scope,updated_at)，给 config_service 加异步 save_global()/load_global()，JSON 序列化存值；若用别的既有承载物必须在报告论证且不得塞进语义不符的表。(b) 不要因此把 set_global 改成 async 破坏既有调用方，新增异步方法由插件显式调用。(c) init_db() 之后必须把已存全局配置读回 config_service，否则重启仍是默认值。(d) 落库失败必须报错，不得静默返回成功。(e) 建表走既有 generate_schemas 或显式迁移，不写裸 SQL。
必须新增测试并贴原始输出：test_shop_stock_persists_across_restart（写库存→close_db→重新init_db→读回断言相等）、test_shop_purchase_decrements_persisted_stock（购买后库存-1，重开库仍是减后的值）。并做负向对照：把落库调用注释掉→上述测试必须 FAILED→改回→PASSED，两段原始输出都贴。

【问题2 必修：报告漏报】M4-REPORT.md 末尾写'与设计的偏差：无偏差'、'未解决问题：无'，但库存不持久化是真实偏差，属漏报。要求修正该段如实列出，并新增 '## 11. M4FIX 修正记录'：问题描述与实证输出、根因、改法关键 diff、新增测试原始输出、全量 pytest 原始输出与最终 N 数，并明确回答修正后是否还有已知未解决项（有就列，无就写无，不得为好看写无）。

【硬约束】依赖仍仅 tortoise-orm/aiosqlite/pydantic/httpx/pytest/pytest-asyncio。不得引入 fallback/patch/兼容层，不得有'库没初始化就假装成功'分支。插件不得 import 平台层、不得裸写 SQL，边界 B1-B5 必须继续通过。既有 131 项测试必须仍全绿，不得放宽任何断言。权限+限制<=700 行、核心<=6000 行（当前 5457 注意别超）、单文件函数数<=30、生产代码禁 print。不接真实 Telegram。不改 docs/ 与 NEXT-TASK-*.md。不提交 data/.venv/*.db/*.log。

报告写完即停，不要开始 M5。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M4FIX start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M4FIX exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if grep -q "## 11. M4FIX 修正记录" M4-REPORT.md 2>/dev/null && grep -q "test_shop_stock_persists_across_restart" tests/*.py 2>/dev/null; then
    echo "[$(date '+%F %T')] === M4FIX DONE (report section + persistence test present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M4FIX GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
