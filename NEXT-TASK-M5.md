# NEXT-TASK-M5：可选层（图片渲染器 + WebUI）

> 当前唯一权威指令。细节见 `docs/zx-tg-design-v3.md` §3.3 / §0.3（D2/D3）/ §5.12，与 `docs/zx-tg-requirements-v1.0.md` §6.10（FR-RND-01~07）、§6.11（FR-WEB-01~07）。
> 基线：`f4818df`，**133 tests passed**。本轮只做 M5，**不接真实 Telegram**。

---

## 0. 本轮两个交付物，必须彼此独立

按设计 D2/D3：渲染器与 WebUI 都是**可选插件、默认开启、默认降档**。两者的共同硬指标是：
**核心安装不得因它们变胖**；未安装其依赖时，核心必须照常运行并给出**明确安装指引**，而不是堆栈错误。

| 组合 | 目标体积 |
|---|---|
| `zxtg` 默认安装（渲染开=Pillow + WebUI 开） | ~150 MB |
| `zxtg[lite]`（都关） | ~95 MB |
| 切 `RENDER_ENGINE=html` | +Chromium ~300 MB，**默认绝不包含** |

---

## 1. 渲染器（FR-RND-01~07）

### 1.1 接口（FR-RND-01，必须可插拔）
新建 `src/zxtg/core/render/`：

- `port.py`：`RendererPort` 抽象（协议/ABC），方法语义统一为 `async def render(template: str, data: dict) -> RenderResult`。
- `text.py`：`TextRenderer` —— **零依赖**，输出 Markdown 文本。它是**保底档**。
- `pillow_engine.py`：`PillowRenderer` —— 轻量卡片图片（签到卡 / 排行榜）。
- `html.py`：`HtmlRenderer` —— `jinja2` + `playwright`，**可选**。
- `registry.py`（或等价）：按配置选择引擎。

`RenderResult` 必须**显式携带实际使用的引擎名**（例如 `engine: str`）与内容类型（text / image bytes）。
这条是硬要求：**不允许出现"降级了但没人知道"**，否则就是静默兜底。

### 1.2 插件侧统一入口（FR-RND-01）
在 `CallContext` 增加 `async def render(template: str, data: dict) -> RenderResult`，插件调用它**不知道背后是哪个引擎**。
同时把 `reply_image(template, data)` 从 `NotImplementedError` 改成真实实现（走 renderer）。
**插件侧不得 import 任何具体引擎**。

### 1.3 引擎选择与降级（FR-RND-05 / FR-RND-07）
配置键（必须符合 `^[A-Z][A-Z0-9_]{1,63}$`）：`RENDER_ENGINE`，取值 `text` / `pillow` / `html`，默认 `pillow`。

- 配置的引擎不可用（依赖缺失）时：**降级到下一档**（html → pillow → text），
  并 **① 记 warning 日志 ② 在 `RenderResult.engine` 里如实反映实际引擎 ③ 首次降级时向用户给出可读提示**（例如"图片渲染不可用，已用文本；安装：pip install zxtg[render]"）。
- 降级链终点是 `text`（零依赖，保证一定成功），因此**不存在"什么都渲染不出来"的情况**。
- **严禁**把降级写成静默成功：不得 `except: pass`，不得返回 `engine="pillow"` 实际却是文本。
- 不得因渲染失败中断业务命令（FR-RND-05）。
- 未安装指定引擎依赖时给安装指引，**不要抛原始 ImportError 堆栈**（FR-RND-07）。

### 1.4 默认安装不含 Chromium（FR-RND-06）
`pyproject.toml` 增加**可选 extras**，核心 `dependencies` 保持现有 4 项不变：

```
[project.optional-dependencies]
render  = ["pillow"]
html    = ["jinja2", "playwright"]
webui   = ["fastapi", "uvicorn", "pyjwt"]
```

必须证明：**未安装 pillow 时 `import zxtg` 正常、核心测试仍全绿**（不得在模块顶层无条件 `import PIL`）。

### 1.5 落地点（把 M4 欠的补上）
`plugins/sign_in/` 的签到卡改为调用 `ctx.render(...)`：
- `RENDER_ENGINE=pillow` → 输出图片（卡片）
- 引擎降级到 text → 输出 Markdown（M4 的纯文本形态保留为 text 渲染器的输出）
排行榜同理。

---

## 2. WebUI（FR-WEB-01~07）

新建可选插件 `plugins/webui/`。

- **默认开启，默认监听 `127.0.0.1`**；改公网监听必须显式配置才生效（FR-WEB-02）。
- 配置键建议：`WEBUI_ENABLED`、`WEBUI_HOST`（默认 `127.0.0.1`）、`WEBUI_PORT`、`WEBUI_TOKEN_TTL`。全部符合键名正则。
- **账号登录 + 令牌机制，令牌具备过期时间**（FR-WEB-03）。令牌校验失败/过期必须明确拒绝，不得放行。
- 功能：插件开关、配置项查看与修改、群管理操作（FR-WEB-04）。
- 配置表单由 FR-CFG 的 **JSON Schema 自动渲染**（FR-WEB-05，S 级；做不了就如实标 BLOCKED，别假装做了）。
- **默认安装不得捆绑生产级 ASGI 部署配置**（FR-WEB-06）：不得生成 systemd/nginx/Dockerfile 之类部署产物。
- **关闭 WebUI 后不得残留依赖开销或后台任务**（FR-WEB-07）：关闭后必须真正停掉监听与后台协程；要有测试证明关闭后无残留 task。

### 2.1 安全的硬要求
- 默认 `127.0.0.1`；若用户改成 `0.0.0.0`，启动时必须**警告**并记录日志。
- 令牌不得写入日志、不得出现在错误信息里（沿用 NFR-09）。
- 登录失败要有速率/次数限制或至少明确的失败计数（不做也行，但要如实写"未实现"）。
- **不接真实 Telegram**：WebUI 只读写本地 DB，不做真实 TG 调用。

---

## 3. 必须真跑真验证（原始输出抄进报告）

### 3.1 渲染器
1. `test_text_renderer_zero_dependency`：text 引擎在**无 pillow 环境下**可用。
2. `test_pillow_renderer_produces_image`：pillow 可用时输出真实 PNG bytes（断言 PNG magic header `\x89PNG`，不是空 bytes）。
3. `test_render_degrades_when_pillow_missing`：**隐藏/模拟 pillow 不可用**（monkeypatch 让 import 失败），断言：不抛异常、降级到 text、`RenderResult.engine == "text"`、有可读提示。
4. `test_render_engine_never_lies`：**负向对照**——故意让降级后仍返回 `engine="pillow"`，测试必须 FAILED；改回 PASSED。贴原始输出。
5. `test_core_import_without_optional_deps`：模拟 pillow/fastapi 都不可用时 `import zxtg` 与核心命令仍正常。
6. `test_signin_card_uses_renderer`：`RENDER_ENGINE=pillow` 时签到返回图片；`text` 时返回 Markdown。

### 3.2 WebUI
7. `test_webui_default_host_is_loopback`：默认配置下 host == `127.0.0.1`。
8. `test_webui_token_expiry_rejects_expired`：过期令牌被拒（不得放行）。
9. `test_webui_disabled_leaves_no_tasks`：关闭后断言无残留 asyncio task / 端口不再监听（FR-WEB-07）。
10. `test_webui_plugin_toggle_and_config`：通过 WebUI 端点改插件开关与配置，读回生效。
11. `test_webui_requires_auth`：未带令牌访问管理端点被拒（401/403），**不得**返回数据。

### 3.3 全局
12. 全量 `pytest -q` 全绿，基线 133，本轮应显著增加。
13. 边界 B1–B5 继续通过（插件不得 import 平台层；`plugins/webui` 也不得）。
14. 权限+限制逻辑 ≤700 行；核心 ≤6000 行（**当前 5551，M5 新增渲染/WebUI 极易超，务必控制；超了就要在报告里如实写并说明**）。
15. 单文件函数数 ≤30；生产代码禁 `print()`；日志不含 token。

---

## 4. 硬约束（不放松）

- 核心 `dependencies` **保持不变**（tortoise-orm / aiosqlite / pydantic / httpx）；新增依赖只能进 `optional-dependencies`。
- **不得引入 fallback / patch / guard-of-guard 兼容层**（FR-AUTH-06 / NFR-16）。
  注意区分：**FR-RND-05 的引擎降级是规格要求的功能，不是兼容层**——但它必须显式、可观测、可验证，绝不能变成"假装成功"。这条是本次复核的重点，请自己先自查。
- 不得出现"数据库没初始化就假装成功"这类分支（M3 教训）。
- 不得出现"配置写内存就算持久化"这类分支（M4 教训）。
- 插件不得 import 平台层；不得裸写 SQL。
- 不接真实 Telegram。
- 不改 `docs/`、`README.md`、既有 `NEXT-TASK-*.md`。
- 不提交 `data/` / `.venv/` / `*.db` / `*.log` / `.env` / `*token*`。

---

## 5. 报告 `M5-REPORT.md`

包含：
- 环境与依赖：**明确列出新增了哪些 optional 依赖、各多少体积**（用 `du` 实测）。
- 变更文件清单（含行数）。
- 渲染器架构说明（引擎选择 + 降级链 + `RenderResult.engine` 如何保证不说谎）。
- WebUI 端点表（路径 / 方法 / 是否需要令牌 / 作用）。
- §3 每条验证的**原始终端输出**（不许编造）。
- 两张负向对照原始输出（`engine` 说谎、以及你自选的另一处）。
- 边界 B1–B5 结果。
- 行数统计（核心 / 权限+限制 / 渲染器 / WebUI）。
- **BLOCKED 清单**：真实 TG 一律 BLOCKED；Chromium HTML 真机渲染若无法离线验证，如实标 BLOCKED 并说明解锁条件；FR-WEB-05（JSON Schema 表单）做不了就标 BLOCKED，不许假装。
- 与设计的偏差、未解决问题（**不要为好看写"无"**，M4 已因漏报被打回一次）。

报告写完即停，**不要开始 M6**。
