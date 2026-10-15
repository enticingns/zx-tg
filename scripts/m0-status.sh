#!/usr/bin/env bash
# ZX-TG M0 状态汇总（供 6:00 汇报使用；只读，不产生副作用）
set -u
cd /root/work/zx-tg 2>/dev/null || { echo "项目目录不存在"; exit 1; }

echo "=== ZX-TG M0 状态 ==="
echo "时间: $(date '+%F %T %Z')"
echo

echo "--- 零重力进程 ---"
if pgrep -f "agy --model" >/dev/null 2>&1; then
  pid=$(pgrep -f "agy --model" | head -1)
  echo "运行中 pid=$pid"
  ps -o etime=,time= -p "$pid" 2>/dev/null | sed 's/^/  /'
else
  echo "无 agy 进程（已结束或未启动）"
fi
echo

echo "--- 运行日志尾部 ---"
tail -8 /root/work/logs/zxtg-m0-run.log 2>/dev/null
echo

echo "--- 关键产出 ---"
for f in M0-REPORT.md src/zxtg/core/event.py src/zxtg/core/kernel/pipeline.py \
         src/zxtg/core/context.py src/zxtg/models/plugin_info.py scripts/smoke_m0.py; do
  if [ -e "$f" ]; then echo "  ✔ $f"; else echo "  ✘ $f"; fi
done
echo

echo "--- python 文件数 ---"
find . -path ./.venv -prune -o -path ./.git -prune -o -name '*.py' -print 2>/dev/null | wc -l
echo

echo "--- 未提交改动 ---"
git status --short 2>/dev/null | head -20
echo

echo "--- 最近提交 ---"
git log --oneline -3 2>/dev/null
