#!/usr/bin/env bash
# ZX-TG 早间结果汇总（6:00 推送用）。只读 + 只读复核，不产生副作用。
set -u
cd /root/work/zx-tg 2>/dev/null || { echo "ZX-TG: 项目目录不存在"; exit 0; }

echo "ZX-TG · 早间结果（$(date '+%m-%d %H:%M')）"
echo

echo "【零重力进程】"
for u in zxtg-m0 zxtg-m1 zxtg-m2; do
  s=$(systemctl --user is-active "$u" 2>/dev/null)
  [ -n "$s" ] && echo "  $u: $s"
done
if pgrep -f "agy --model" >/dev/null 2>&1; then
  pid=$(pgrep -f "agy --model" | head -1)
  echo "  agy 运行中 pid=$pid $(ps -o etime= -p "$pid" 2>/dev/null)"
else
  echo "  agy 已结束"
fi
echo

echo "【里程碑报告产出】"
for f in M0-REPORT.md M1-REPORT.md M2-REPORT.md M3-REPORT.md; do
  [ -f "$f" ] && echo "  OK  $f ($(wc -l < "$f") 行)" || echo "  --  $f"
done
echo

echo "【运行日志尾部】"
for l in zxtg-m1-run zxtg-m0-run; do
  [ -f "/root/work/logs/$l.log" ] || continue
  echo "  --- $l ---"
  tail -4 "/root/work/logs/$l.log" | sed 's/^/    /'
done
echo

echo "【代码规模】"
py=$(find src -name '*.py' 2>/dev/null | wc -l)
ln=$(cat $(find src -name '*.py' 2>/dev/null) 2>/dev/null | wc -l)
echo "  src: ${py} 个 .py, ${ln} 行"
echo

echo "【独立复核：pytest】"
if [ -x .venv/bin/python ]; then
  out=$(timeout 240 .venv/bin/python -m pytest -q 2>&1 | tail -4)
  echo "$out" | sed 's/^/  /'
else
  echo "  无 .venv"
fi
echo

echo "【Git 状态】"
git log --oneline -4 2>/dev/null | sed 's/^/  /'
echo "  --- 未提交 ---"
git status --short 2>/dev/null | head -15 | sed 's/^/  /'
echo

echo "【最新报告摘要】"
latest=""
for f in M3-REPORT.md M2-REPORT.md M1-REPORT.md M0-REPORT.md; do
  [ -f "$f" ] && latest="$f" && break
done
if [ -n "$latest" ]; then
  echo "  ($latest 前 30 行)"
  sed -n '1,30p' "$latest" | sed 's/^/  /'
else
  echo "  暂无报告"
fi
