#!/usr/bin/env bash
# ZX-TG M4 运行器：内置插件层（help/sign_in/shop/admin/info/superuser）
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m4-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M4.md 是当前唯一权威指令，先通读它，严格按它执行。

【前置】M0/M1/M2/M3+M3FIX 已完成并入库（最新 commit 42763da，tests 100 passed）。现有内核 core/kernel（manifest/registry/config/limits/scheduler/commands/guards/pipeline）、平台层 core/platform/tg、服务层 core/services（user/group/gold/impression/permission/item/statistics/dao/db）、模型层 models/、示例插件 plugins/ping。不要回退已通过内容，不要放宽既有断言。

【本轮范围】只做 M4：6 个 Must 级内置插件，全部放 plugins/<key>/plugin.py：
1. plugins/help/ —— 帮助与菜单：按 menu_type 分类、单插件详情、按权限过滤（复用 permission_service，不自己重写等级判断）。
2. plugins/sign_in/ —— 签到与好感度排行：每日签到（同日重复必须拒绝且余额不变）、奖励走 gold_service/impression_service、群内与全局排行榜。签到卡本轮用纯文本 Markdown（图片渲染属 M5，不要假装渲染过）。
3. plugins/shop/ —— 商店：道具上架/下架、购买、库存管理、金币结算。购买必须原子：校验库存与余额 → 扣金币 → 减库存 → 发放 UserItem，任一步失败整体不生效，不得扣了钱没发货。道具定义来自 manifest configs，不硬编码。
4. plugins/admin/ —— 群管理：禁言/解禁/踢出/封禁/解封/设置撤销管理员。只用 ctx.mute/unmute/kick/ban/unban 语义化接口，禁止 import 平台层。平台返回 False 时必须如实报失败并给可读提示，绝不能静默当成功。
5. plugins/info/ —— 信息查询：用户信息/群信息/Bot 状态；username 为 None 时回退 full_name，再没有用 ID。
6. plugins/superuser/ —— 超级用户：全局/群插件开关、广播、退群、数据维护。广播部分失败不中断，但每个失败要记录并可汇总失败数，不得静默吞掉。

【插件契约】插件不得 import core.platform/httpx/telegram；不得裸写 SQL，数据访问走 ctx.db() 的 DAO 或既有 service；不得含任何 fallback/兼容层；manifest 字段只能用已有 PluginManifest/Cmd/Config/Limit 定义，不得私造；key 匹配 ^[a-z][a-z0-9_]{2,31}$；新增命令前检查与 ping 及彼此是否冲突。

【必须真跑真验证】按任务书 §3，每个插件至少 3 个用例。重点：help 的权限过滤与单插件详情；sign_in 首次成功/同日重复被拒且余额不变/排行排序；shop 正常购买/余额不足不动库存/库存不足不动金币/失败回滚；admin 无权限被拒 + 平台返回 False 时必须报失败（fake client 注入 False，断言提示出现且不伪装成功）；info 的 username=None 回退；superuser 全局开关/群级覆盖/广播部分失败仍继续且汇总失败数。边界 B1-B5 必须继续通过；若因新插件导致 B2/B5 失败，改插件不改测试。另外必须对 admin 的 False 处理与 shop 的失败回滚各做一次负向对照（故意写错→测试 FAILED→改回→PASS），原始输出抄进报告。

【硬约束】依赖仍仅 tortoise-orm/aiosqlite/pydantic/httpx/pytest/pytest-asyncio；不得引入任何 fallback/patch/兼容层；特别注意不得出现'数据库没初始化就假装成功'这类分支（M3 已因此被打回一次）；生产代码禁 print；日志不含 token；单文件函数数<=30；权限+限制<=700 行；核心<=6000 行；不接真实 Telegram、不碰真实网络；不改 docs/ 与既有 NEXT-TASK-*.md；不提交 data/.venv/*.db/*.log。

【交付格式】写 M4-REPORT.md：环境与依赖（新增须论证）、变更文件清单含行数、每个插件的命令表（中文 pattern/slash/权限/是否有消耗）、§3 每条验证的原始终端输出（不许编造）、两张负向对照原始输出、边界 B1-B5 结果、代码行数（plugins 各插件行数/核心/权限+限制）、BLOCKED 清单（真实 TG 一律 BLOCKED；图片渲染明确写属 M5 本轮未做）、与设计的偏差、未解决问题。报告写完即停，不要开始 M5。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M4 start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M4 exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M4-REPORT.md ] && [ -f plugins/help/plugin.py ] && [ -f plugins/sign_in/plugin.py ] && [ -f plugins/shop/plugin.py ]; then
    echo "[$(date '+%F %T')] === M4 DONE (report + help/sign_in/shop present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M4 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
