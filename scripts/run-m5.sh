#!/usr/bin/env bash
# ZX-TG M5 运行器：可选层（Pillow 渲染器 + WebUI）
set -u
export PATH="/root/.local/bin:$PATH"
export HTTPS_PROXY=http://127.0.0.1:10809
export HTTP_PROXY=http://127.0.0.1:10809
export PIP_PROXY=http://127.0.0.1:10809
export NO_COLOR=1
cd /root/work/zx-tg || exit 1
LOG=/root/work/logs/zxtg-m5-run.log

PROMPT="你在 /root/work/zx-tg 这个 Python 项目里工作。任务书 NEXT-TASK-M5.md 是当前唯一权威指令，先通读它，严格按它执行。

【前置】M0/M1/M2/M3/M4 已完成并入库（最新 commit f4818df，tests 133 passed）。现有内核 core/kernel、平台层 core/platform/tg、服务层 core/services、模型层 models/、6 个内置插件 plugins/{help,sign_in,shop,admin,info,superuser}。不要回退已通过内容，不要放宽既有断言。

【本轮范围】只做 M5 两个交付物：
A) 渲染器（FR-RND-01~07）：新建 src/zxtg/core/render/{port.py,text.py,pillow_engine.py,html.py,registry.py}。RendererPort 抽象，async render(template,data) -> RenderResult，RenderResult 必须显式携带实际使用的 engine 名与内容类型。TextRenderer 零依赖输出 Markdown（保底档）；PillowRenderer 输出轻量卡片图片；HtmlRenderer 用 jinja2+playwright 可选。CallContext 增加 async render(template,data)，并把 reply_image 从 NotImplementedError 改成真实实现走 renderer。配置键 RENDER_ENGINE 取值 text/pillow/html 默认 pillow。引擎不可用时降级 html->pillow->text，必须：记 warning 日志、在 RenderResult.engine 如实反映实际引擎、首次降级给用户可读安装指引（如 pip install zxtg[render]）。严禁 except pass 或返回 engine=pillow 实际是文本。不得因渲染失败中断业务。未装依赖时给安装指引不要抛原始 ImportError 堆栈。pyproject 增加 optional-dependencies: render=[pillow], html=[jinja2,playwright], webui=[fastapi,uvicorn,pyjwt]，核心 dependencies 保持原 4 项不变；必须证明未装 pillow 时 import zxtg 正常且核心测试全绿（模块顶层不得无条件 import PIL）。把 plugins/sign_in 的签到卡改为调用 ctx.render：pillow 出图片，降级 text 出 Markdown；排行榜同理。
B) WebUI（FR-WEB-01~07）：新建 plugins/webui/。默认开启、默认监听 127.0.0.1，改公网必须显式配置。配置键建议 WEBUI_ENABLED/WEBUI_HOST/WEBUI_PORT/WEBUI_TOKEN_TTL，须符合 ^[A-Z][A-Z0-9_]{1,63}$。账号登录+令牌机制，令牌必须有过期时间，过期/无效必须明确拒绝不得放行。功能：插件开关、配置项查看修改、群管理。配置表单由 FR-CFG 的 JSON Schema 自动渲染（S 级，做不了如实标 BLOCKED 不要假装）。默认安装不得捆绑生产级 ASGI 部署配置（不生成 systemd/nginx/Dockerfile）。关闭 WebUI 后不得残留依赖开销或后台任务，要有测试证明关闭后无残留 task。安全：默认 127.0.0.1，改 0.0.0.0 必须启动警告并记日志；令牌不得写入日志或错误信息；登录失败要有失败计数（不做就如实写未实现）。不接真实 Telegram，WebUI 只读写本地 DB。

【必须真跑真验证】按任务书 §3 共 13 项。重点：text 渲染器在无 pillow 时可用；pillow 输出真实 PNG（断言 \\x89PNG magic）；pillow 缺失时降级不抛异常且 RenderResult.engine=='text' 且有提示；engine 绝不说谎的负向对照（故意让降级后仍返回 engine=pillow → 测试必须 FAILED → 改回 PASSED，贴原始输出）；无可选依赖时 import zxtg 正常；签到卡按引擎切换输出形态；WebUI 默认 host 是 127.0.0.1；过期令牌被拒；关闭后无残留 task/端口；WebUI 改开关与配置生效；未带令牌访问管理端点被拒（401/403 不返回数据）。另外自己再选一处做第二张负向对照。边界 B1-B5 必须继续通过，plugins/webui 也不得 import 平台层。

【硬约束】核心 dependencies 保持不变，新增依赖只能进 optional-dependencies。不得引入 fallback/patch 兼容层（注意：FR-RND-05 的引擎降级是规格要求的功能，不是兼容层，但必须显式可观测可验证，不能变成假装成功——这是本轮复核重点，先自查）。不得出现'数据库没初始化就假装成功'（M3 教训）。不得出现'配置写内存就算持久化'（M4 教训）。插件不得 import 平台层、不得裸写 SQL。权限+限制<=700 行；核心<=6000 行（当前 5551，M5 极易超，务必控制，超了要如实写并说明）；单文件函数数<=30；生产代码禁 print；日志不含 token。不接真实 Telegram。不改 docs/ 与既有 NEXT-TASK-*.md。不提交 data/.venv/*.db/*.log。

【交付格式】写 M5-REPORT.md：环境与依赖（明确列出新增 optional 依赖及各自体积，用 du 实测）、变更文件清单含行数、渲染器架构说明（引擎选择+降级链+engine 如何保证不说谎）、WebUI 端点表（路径/方法/是否需令牌/作用）、§3 每条验证的原始终端输出（不许编造）、两张负向对照原始输出、边界 B1-B5 结果、行数统计（核心/权限+限制/渲染器/WebUI）、BLOCKED 清单（真实 TG 一律 BLOCKED；Chromium HTML 真机渲染无法离线验证则如实标 BLOCKED 并写解锁条件；FR-WEB-05 做不了标 BLOCKED 不许假装）、与设计的偏差、未解决问题（不要为好看写'无'，M4 已因漏报被打回一次）。报告写完即停，不要开始 M6。"

attempt=1
max=20
while [ $attempt -le $max ]; do
  echo "[$(date '+%F %T')] === M5 start (attempt $attempt/$max) ===" | tee -a "$LOG"
  start=$(date +%s)
  agy --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 0 -p "$PROMPT" >> "$LOG" 2>&1
  rc=$?
  dur=$(( $(date +%s) - start ))
  echo "[$(date '+%F %T')] === M5 exit rc=$rc (${dur}s) ===" | tee -a "$LOG"
  if [ -f M5-REPORT.md ] && [ -f src/zxtg/core/render/text.py ] && [ -f plugins/webui/plugin.py ]; then
    echo "[$(date '+%F %T')] === M5 DONE (report + text renderer + webui present) ===" | tee -a "$LOG"
    exit 0
  fi
  echo "[$(date '+%F %T')] not done yet (rc=$rc, ${dur}s) -> retry in 15s" | tee -a "$LOG"
  sleep 15
  attempt=$((attempt+1))
done
echo "[$(date '+%F %T')] === M5 GAVE UP after $max attempts ===" | tee -a "$LOG"
exit 1
