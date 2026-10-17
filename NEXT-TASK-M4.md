# NEXT-TASK-M4：内置插件层（FR-BIP-01~06 Must 级）

> 当前唯一权威指令。细节见 `docs/zx-tg-design-v3.md` §4.1/§4.2/§5.12/§5.14 与 `docs/zx-tg-requirements-v1.0.md` §6.9、FR-PLG-*。
> M0/M1/M2/M3+M3FIX 已完成并入库（最新 `42763da`，**100 tests**）。本轮只做 M4，**不接真实 Telegram**。

---

## 1. 本轮交付物：6 个 Must 级内置插件

全部放 `plugins/<key>/plugin.py`，遵循 FR-PLG-01（入口 `plugin.py` 定义 `manifest` 对象）、FR-PLG-02（manifest 为声明式、可静态读取，不靠 import 副作用注册）。

### 1.1 `plugins/help/` — 帮助与菜单（FR-BIP-01）
- 按 `menu_type` 分类展示插件列表；支持查看单插件详情（命令、用法、示例、权限要求）。
- **权限过滤**：只显示当前用户实际可执行的项（复用 `permission_service`，不得自己重写一套等级判断）。
- 双轨命令：中文文本命令 + 英文 slash。

### 1.2 `plugins/sign_in/` — 签到与好感度排行（FR-BIP-02）
- 每日签到，同一天重复签到必须被拒绝（幂等，不得静默加钱两次）。
- 签到奖励写 `gold_service`，好感度写 `impression_service`，**必须走既有服务，禁止插件里裸写 ORM 或 SQL**。
- 群内 / 全局排行榜（按 `UserConsole.impression`）。
- 签到卡渲染：**M4 不接图片渲染器**（属 M5），用纯文本 + Markdown 输出；`reply_image` 调用点在 M5 再接。报告里必须写明这一点，不得假装渲染过。

### 1.3 `plugins/shop/` — 商店（FR-BIP-03）
- 道具上架/下架、购买、库存管理、金币结算。
- 购买必须**原子**：先校验库存与余额 → 扣金币 → 减库存 → 发放到 `UserItem`；任一步失败必须整体不生效（不得出现扣了钱没发货）。
- 库存不足、余额不足、道具不存在，都要返回可读提示。
- 道具定义来自插件配置（`configs`），不硬编码在代码里。

### 1.4 `plugins/admin/` — 群管理（FR-BIP-04）
- 禁言/解禁、踢出、封禁/解封、设置/撤销管理员、管理员变更通知。
- 全部通过 `ctx.mute/unmute/kick/ban/unban` 语义化接口，**禁止插件直接 import 平台层**（B1 边界）。
- **返回 bool 必须被检查并如实反馈**：bot 权限不足时返回 `False` 并给出可读提示，**不得静默当作成功**（设计 §5.12 明确要求，这是上游 QQ 版的坏习惯）。
- 仅管理员可用（`PluginType.ADMIN`）。

### 1.5 `plugins/info/` — 信息查询（FR-BIP-05）
- 用户信息、群信息、Bot 状态。
- `username` 为 None 时显示回退 `full_name`（FR-TG-08），再没有则用 ID。

### 1.6 `plugins/superuser/` — 超级用户（FR-BIP-06）
- 全局/群插件开关、广播、退群、数据维护。
- `PluginType.SUPERUSER`；`limit_superuser=False` 语义必须正确（超管自身不被该插件限制拦住）。
- 广播不得因单个会话失败而中断整体，但**每个失败必须记录并可汇总报告**，不得静默吞掉。

---

## 2. 必须遵守的插件契约

1. **插件不得 import 平台层**（`core.platform*`、`httpx`、`telegram` 等），只能吃 `ctx` 与内核/服务层的公开接口。
2. **插件不得裸写 SQL**；数据访问一律走 `ctx.db()` 的 DAO 或既有 service。
3. 插件不得含业务无关的兜底/兼容层（FR-AUTH-06 / NFR-16）。
4. 所有 manifest 字段必须使用已有 `PluginManifest` / `Cmd` / `Config` / `Limit` 定义，不得私造字段（FR-PLG-12/14）。
5. `key` 必须匹配 `^[a-z][a-z0-9_]{2,31}$`（FR-PLG-03）。
6. 命令冲突（key/slash/pattern 前缀）会被启动期校验拦下——新增命令前先看现有 `plugins/ping` 与彼此之间是否撞车。

---

## 3. 必须真跑真验证（写进报告，抄原始输出）

1. **全量 `pytest -q` 全绿**，基线 100，本轮应显著增加。
2. **每个插件至少 3 个用例**，重点覆盖：
   - `help`：权限过滤（普通用户看不到 ADMIN/SUPERUSER 插件）、单插件详情、无插件时不出错。
   - `sign_in`：首次签到成功、同日重复签到被拒且余额不变、排行榜排序正确。
   - `shop`：正常购买（金币减、库存减、道具到账）、余额不足（金币与库存都不变）、库存不足（不动金币）、**失败路径回滚**。
   - `admin`：无权限用户被拒；**平台返回 False 时必须报失败**（用 fake client 注入 False，断言提示语出现且不伪装成功）。
   - `info`：username=None 时回退 full_name。
   - `superuser`：全局开关生效、群级开关覆盖全局、广播部分失败仍继续且汇总失败数。
3. **边界 B1–B5 必须继续通过**（`tests/test_boundaries.py`）。若你新增插件导致 B2/B5 失败，修的是插件，不是测试。
4. **负向对照自证**（报告里贴输出）：至少对 `admin` 的 False 处理与 `shop` 的失败回滚各做一次"故意写错→测试失败→改回→通过"的证明。

---

## 4. 硬约束（不放松）

- 依赖仍仅 `tortoise-orm` / `aiosqlite` / `pydantic>=2` / `httpx` / `pytest` / `pytest-asyncio`；禁 `nonebot2` / `aiogram` / `python-telegram-bot` / `playwright` / `fastapi` / `uvicorn`。
- **不引入任何 fallback / patch / guard-of-guard 兼容层**（FR-AUTH-06 / NFR-16）。特别注意：**不得出现"数据库没初始化就假装成功"这类分支**（M3 已因此被打回一次）。
- 生产代码禁 `print()`；日志/异常不得含 token。
- 单文件函数数 ≤30；权限+限制逻辑仍 ≤700 行；核心 ≤6000 行（M4 新增的是 `plugins/`，不计入核心，但要报数）。
- **不接真实 Telegram、不碰真实网络**（保持 M2 边界，避免与宿主 bot 争 updates）。
- 不改 `docs/`、`README.md`、既有 `NEXT-TASK-*.md`。
- 不提交 `data/` / `.venv/` / `*.db` / `*.log` / `.env` / `*token*`。

---

## 5. 报告

写 `M4-REPORT.md`，包含：
- 环境与依赖（是否新增依赖，新增须论证）。
- 变更文件清单（含行数）。
- 每个插件的命令表（中文 pattern / slash / 权限要求 / 是否有消耗）。
- §3 每条验证的**原始终端输出**（不许编造）。
- 两张负向对照的原始输出。
- 边界 B1–B5 结果。
- 代码行数（`plugins/` 各插件行数、核心行数、权限+限制行数）。
- BLOCKED 清单（真实 TG 相关一律 BLOCKED；图片渲染明确写"属 M5，本轮未做"）。
- 与设计的偏差、未解决问题。

报告写完即停，**不要开始 M5**。
