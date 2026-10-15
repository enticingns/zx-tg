#!/usr/bin/env bash
# ZX-TG M0 早间结果汇总（6:00 推送用）。只读 + 只做只读验证，不产生副作用。
set -u
cd /root/work/zx-tg 2>/dev/null || { echo "ZX-TG: 项目目录不存在"; exit 0; }

echo "ZX-TG · M0 结果（$(date '+%m-%d %H:%M')）"
echo

echo "【零重力进程】"
if pgrep -f "agy --model" >/dev/null 2>&1; then
  pid=$(pgrep -f "agy --model" | head -1)
  echo "  仍在运行 pid=$pid $(ps -o etime= -p "$pid" 2>/dev/null)"
else
  echo "  已结束"
fi
echo

echo "【运行日志尾部】"
tail -6 /root/work/logs/zxtg-m0-run.log 2>/dev/null || echo "  (无日志)"
echo

echo "【关键产出】"
for f in M0-REPORT.md src/zxtg/core/event.py src/zxtg/core/kernel/pipeline.py \
         src/zxtg/core/context.py src/zxtg/models/plugin_info.py scripts/smoke_m0.py; do
  [ -e "$f" ] && echo "  OK  $f" || echo "  --  $f"
done
echo

echo "【代码规模】"
py=$(find src -name '*.py' 2>/dev/null | wc -l)
ln=$(cat $(find src -name '*.py' 2>/dev/null) 2>/dev/null | wc -l)
echo "  src: ${py} 个 .py, ${ln} 行"
echo

echo "【独立复核：pytest】"
if [ -x .venv/bin/python ]; then
  out=$(timeout 180 .venv/bin/python -m pytest -q 2>&1 | tail -5)
  echo "$out" | sed 's/^/  /'
else
  echo "  无 .venv（未执行本地复核）"
fi
echo

echo "【Git 状态】"
git log --oneline -4 2>/dev/null | sed 's/^/  /'
echo "  --- 未提交 ---"
git status --short 2>/dev/null | head -12 | sed 's/^/  /'
echo

echo "【报告摘要（若有）】"
if [ -f M0-REPORT.md ]; then
  sed -n '1,40p' M0-REPORT.md
else
  echo "  M0-REPORT.md 尚未生成"
fi
