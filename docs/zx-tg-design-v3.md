# ZX-TG 设计方案 v3.0：重构路线、轻量化与插件体系

> 上游基线：`zhenxun-org/zhenxun_bot` @ main（本文 §1 数据为本次对上游源码的实测）
> 上一稿：`zhenxun_telegram_port_plan.md` v2.0（功能保真度分析）
> 本稿定位：**回答「怎么重构」「怎么轻量化」，并给出完整插件接入/注册规范**
> 本文不含代码实现，仅为工程设计与规范

---

## 0. 结论先行

**一句话：不要把这件事做成「移植」，要做成「重写」。**

v2.0 证明了「功能能不能保住」——答案是 20 项里 14 项能保住。但 v2.0 没有回答一个更前置的问题：**这套代码值不值得带着走。**

本次对上游源码的实测给出了一个决定性数据：

| 区域 | 实测规模 | 判断 |
|---|---|---|
| `builtin_plugins/hooks/auth*.py` 系列（14 个文件） | **187 KB**，其中 `auth_checker.py` 54 KB、`auth_activation.py` 52 KB | 🔴 单点复杂度失控 |
| 同上，估算行数 | **约 4,600 行** | 🔴 全仓库最重的一块，且是**权限校验**，不是业务 |

一个权限校验系统写到 4,600 行、需要 `auth_patch_guard.py`（补丁守卫）、`auth_legacy_fallback.py`（遗留回退）、`auth_snapshot.py`（快照）、`auth_trace.py`（追踪）、`auth_side_effect.py`（副作用）来互相兜底——这已经不是设计，是**考古层堆叠**。

如果沿用这套代码做 TG 版，你会发现：**你不是在往 TG 移植真寻，你是在给这 4,600 行权限逻辑做第二次考古。** 而且这 4,600 行里绝大多数分支是为 QQ/OneBot 的历史行为写的，迁移到 TG 后全部作废。

### 0.1 三条路线的取舍

| 路线 | 描述 | 结局 |
|---|---|---|
| **A. Fork 减法式** | 复制上游仓库，删 QQ、改 TG | ❌ 不推荐。删到最后剩下一坨互相打补丁的结构，且要持续背 4,600 行权限栈 |
| **B. 完全重写** | 从零写 TG bot，功能逐个重实现 | ⚠️ 不推荐。丢掉真寻最有价值的资产：PluginInfo 数据契约、13 年积累的功能语义、配置项含义 |
| **C. 内核重写 + 契约继承 + 功能平移（推荐）** | 保留**数据模型/配置键/命令名/功能语义**，重写**运行时内核（插件装载、权限、限制、发布）**，功能模块按新契约重写 | ✅ **推荐** |

**路线 C 的核心主张**：

> 真寻真正的资产是「一份共识」——这张表叫什么、这个配置项叫什么、签到给多少金币、什么等级能开什么功能。
> 这些东西是**数据**，不是代码。把数据契约原样继承，把代码换掉，用户感知不到差异，但代码库从 550MB/数万行 变成可以一个人维护。

### 0.2 轻量化目标（数字）

| 维度 | 上游现状 | ZX-TG 目标 | 手段 |
|---|---|---|---|
| Python 依赖体积 | 551 MB | **≤ 95 MB**（无渲染器）/ **≤ 230 MB**（含渲染器） | 移除所有非必需包；**渲染器降级为可选插件** |
| 浏览器二进制 | ~300 MB（Playwright 自带） | **0**（可选，按需装） | 渲染器关闭时不需要任何浏览器 |
| 运行时进程 | 2（bot + 协议端） | **1** | TG 长轮询，无 NapCat/Lagrange |
| 常驻内存 | ~400 MB | **≤ 120 MB** | 无浏览器、无协议端、SQLite |
| 数据库 | PostgreSQL / MySQL | **SQLite**（单文件） | 需 ≥50 并发群时建议换 PostgreSQL |
| 冷启动配置 | 域名+SSL+反代+协议端登录 | **一个 token** | `.env` 填 `TELEGRAM_TOKEN` 即可 |
| 核心运行时代码 | 约 46,000 行（估算） | **≤ 6,000 行** | 见 §1.3 |

### 0.3 已定稿决策（2026-10-15 拍板）

| # | 决策点 | **最终决议** | 影响 |
|---|---|---|---|
| **D1** | 重构路线 | ✅ **C：内核重写 + 数据契约继承 + 功能平移** | §0.1 / §2 / §6 按此展开 |
| **D2** | 图片渲染 | ✅ **可选插件，默认开启**<br>默认引擎 = `pillow`（轻量）；`html` 引擎需显式开启并自备 Chromium | 见下方体积重算 |
| **D3** | WebUI 管理后台 | ✅ **可选插件，默认开启**<br>默认监听 `127.0.0.1`，改公网监听需显式配置 | 同上 |
| **D4** | 数据库 | ✅ **SQLite**（单文件，WAL） | PostgreSQL 仅预留适配，不默认依赖 |
| **D5** | 命令策略 | ✅ **双轨**：中文文本轨 + 英文斜杠轨，同一 handler | §5.4 / §5.5 按此定型 |

> **D5 是本次发现的硬约束**（Telegram 命令不支持中文），直接决定了插件命令契约的形态，见 §5.5。

#### D2/D3 定案后的体积重算

「默认全开」若不加以约束，会把 §0.2 的瘦身成果全部吃回去（渲染器 + WebUI ≈ 恢复到 551 MB）。因此采用**默认开启 + 默认降档**：

| 组合 | 依赖体积 | 浏览器 | 说明 |
|---|---:|---:|---|
| **`zxtg`（默认安装）** | **~150 MB** | 不需要 | 渲染=开（Pillow 引擎）+ WebUI=开。**完整体验，无需额外任何东西** |
| 同上，切换 `render.engine=html` | ~280 MB | +300 MB | 视觉与上游等价，代价是浏览器二进制 |
| **`zxtg[lite]`** | **~95 MB** | 不需要 | 关闭渲染与 WebUI，纯文本。**轻量档** |
| `lite` + 单独装 webui | ~145 MB | 不需要 | 只要后台不要图片 |

要点：**功能可用性由配置项决定，体积由安装 extras 决定。** 二者解耦后，「默认开」不再等于「默认胖」——默认安装的 150 MB 不含 Chromium，只有在明确切换到 Html 渲染引擎时才会付出浏览器二进制的代价。

---

## 1. 上游现状体检（本次实测）

### 1.1 复杂度地图：钱都花在哪了

实测 `zhenxun/builtin_plugins/hooks/` 目录（含 `auth` 子目录下的 14 个权限相关文件）：

| 文件 | 字节 | 职责（从命名推断） | 处置建议 |
|---|---:|---|---|
| `auth_checker.py` | **54,518** | 权限判定主体 | 🔴 重写为 §5.6 的 Guard 管道 |
| `auth_activation.py` | **52,482** | 插件启用状态判定 | 🔴 与上面耦合，合并重写 |
| `auth_snapshot.py` | 13,324 | 状态快照 | 🔴 删除（复杂性来源，无业务价值） |
| `auth_event_selector.py` | 13,528 | 按事件类型分派 | 🟡 重写为事件路由表 |
| `auth_pipeline.py` | 15,256 | 权限管道 | 🟡 重写为单一中间件链 |
| `auth_policy.py` | 10,293 | 策略 | 🟡 重写为 Guard 列表 |
| `auth_trace.py` | 969 | 追踪 | 🔴 删除 |
| `auth_patch_guard.py` | 1,691 | 补丁守卫 | 🔴 删除（补丁本就不该存在） |
| `auth_legacy_fallback.py` | 1,406 | 遗留回退 | 🔴 删除 |
| `auth_side_effect.py` | 6,866 | 副作用处理 | 🔴 删除（应显式调用，不该隐藏执行） |
| `auth_profile.py` | 4,073 | 用户档案 | 🟡 重写为 Context 构建 |
| `auth_runtime_config.py` | 5,400 | 运行时配置 | 🟡 合并进 §5.7 配置层 |
| `auth_types.py` | 1,549 | 类型 | 🟡 保留精简版 |
| `auth_hook.py` | 6,099 | 入口钩子 | 🟡 重写 |
| `call_hook.py` | 2,046 | 调用统计钩子 | 🟢 保留重写 |
| `chkdsk_hook.py` | 7,963 | 磁盘/健康检查钩子 | 🟢 保留重写 |
| `limiter_hook.py` | 517 | 限制器钩子 | 🟢 保留重写 |
| `withdraw_hook.py` | 775 | 撤回钩子 | 🟢 保留重写 |
| **`auth*` 合计（14 文件）** | **187,454** |  | **→ 目标 ≤ 700 行** |

**这张表就是本文存在的理由。** 它不是一个 bug，它是**架构债务的总账单**：每一个 `_guard` / `_fallback` / `_snapshot` / `_trace` 文件，都是某次为了不破坏旧行为而新加的一层。累积 14 层后，没人敢删任何一层。

### 1.2 上游值得继承的东西（不要丢）

实测 `zhenxun/configs/utils/models.py` 中的插件契约模型，这是真寻真正的资产：

```
PluginExtraData        插件扩展信息（20 个字段）
├── author / version / plugin_type / menu_type / is_show
├── setting: PluginSetting   level / default_status / limit_superuser / cost_gold / impression
├── configs: [RegisterConfig]  key / value / module / help / default_value / type / arg_parser
├── limits:  [BaseBlock | PluginCdBlock | PluginCountBlock]
│            status / check_type / watch_type / result / _type(CD|COUNT|BLOCK) / cd / max_count
├── commands: [Command]  command / params / description / examples
├── tasks:    [Task]     module / name / status / scheduler / run_func / check
├── aliases / superuser_help / ignore_prompt / ignore_statistics / sql_list
├── smart_tools (AI 工具集) / introduction / precautions
└── group_config_model   ← 分群配置模型
```

以及 `models/plugin_info.py` 的 DB 模型（26 个字段）和 `utils/enum.py` 的枚举：

```
PluginType:   SUPERUSER | ADMIN | SUPER_AND_ADMIN | NORMAL | DEPENDANT | HIDDEN | PARENT
BlockType:    PRIVATE | GROUP | ALL
LimitWatchType / LimitCheckType:  USER | GROUP | ALL
PluginLimitType:  CD | COUNT | BLOCK
```

**决策：上述字段名、枚举值、语义，在 ZX-TG 中逐字继承。** 理由：这决定了 WebUI、配置迁移、第三方插件能否复用。代码可以重写，名字不能改。

**例外（建议清理）**：

| 字段 | 处置 | 理由 |
|---|---|---|
| `FuncRule`/`AICallableTag` / `smart_tools` | 延后实现 | AI 工具集与本次 TG 移植无关，但预留槽位 |
| `arg_parser` (Callable) | 弱化为类型提示 | Callable 不可序列化，让 JSON/YAML 配置无法校验 |
| `sql_list` | 删除 | 插件裸写 SQL 是注入面，改为 DAO 接口 |
| `group_config_model` | 保留但要求 JSON Schema 可导出 | 否则 WebUI 无法渲染配置表单 |

### 1.3 应该删掉而不是移植的东西

| 项 | 理由 |
|---|---|
| `auth_snapshot` / `auth_trace` / `auth_side_effect` / `auth_patch_guard` / `auth_legacy_fallback` | 补丁层，纯债务 |
| `services/send_queue.py` 的 monkey-patch `OneBotV11Adapter._call_api` | 侵入式打IFE其他类，改为统一出口包装 |
| `uninfo_patch.py` 对 uninfo 库的 patch | 上游已包一层，TG 版直接读 TG 原生对象即可 |
| `asyncpg` / `aiomysql` / `nonebot-adapter-onebot` | 依赖删除 |
| WebUI 全套（`fastapi`/`uvicorn`/`jwt`） | 降级为可选插件 |
| `playwright` 为首的重渲染层 | 降级为可选插件 |

---

## 2. 目标架构（路线 C）

### 2.1 分层

```
┌────────────────────────────────────────────────────────┐
│  L4  插件层  plugins/<key>/plugin.py                    │  ← 业务，按 §5 契约声明
│      sign_in / shop / admin / help / statistics / ...   │
├────────────────────────────────────────────────────────┤
│  L3  服务层  core/services/                             │  ← 无平台语义，可被插件调用
│      user / gold / impression / config / i18n           │
├────────────────────────────────────────────────────────┤
│  L2  内核层  core/kernel/      ★ 本次重写的核心 ★        │
│      registry   插件注册与冲突检测                       │
│      pipeline   单一调用管道（取代 4,600 行权限栈）      │
│      lifecycle  启动/停止/热重载                         │
│      scheduler  定时任务与被动技能                       │
├────────────────────────────────────────────────────────┤
│  L1  平台适配层  core/platform/tg/   ★ TG 唯一实现 ★     │
│      adapter    长轮询收发                              │
│      codec      Update → UnifiedEvent → RenderSpec      │
│      rlmgr      限流与 retry_after（per-chat 令牌桶）     │
├────────────────────────────────────────────────────────┤
│  L0  持久化  SQLite  +  Tortoise ORM                     │
└────────────────────────────────────────────────────────┘
```

### 2.2 三条硬边界（决定了能不能长期维护）

1. **插件不得 import 平台层。** 插件只能依赖 `core/services` 与 `core/kernel` 提供的 API。违反则注册失败并报错。
   → 这保证将来真要接第二条平台时，插件一行不用改。

2. **平台层不得包含业务语义。** `core/platform/tg/` 只做「TG 概念 ↔ 内部概念」的翻译，不出现"签到""金币"等词。

3. **内核不知道 Telegram 的存在。** `core/kernel` 只认 `UnifiedEvent`（`actor` / `chat` / `text` / `attachments` / `raw`）。

> 上游之所以长出 14 个 auth 文件，根本原因就是这三条边界没有被守住：OneBot 的事件类型一路漏进了权限判定里。

### 2.3 统一事件模型

```python
UnifiedEvent
├── actor:    Actor(id, username, full_name, is_bot)     # ≤ 注：TG 用户名可为 None
├── role:     Role(owner | admin | member | restricted)  # 由 get_chat_member 解析，带缓存
├── chat:     ChatRef(id, type: private|group|supergroup, title) | None
├── kind:     text | command | callback | join | leave | member_update | join_request
├── text:     str
├── command:  CommandRef(name, args, raw) | None
├── message_id: int            # 撤回需要
└── raw:      Update           # 逃生舱，禁止在插件层使用
```

**为什么必须有 `message_id`**：TG 撤回是 `delete_message(chat_id, message_id)`，需要插件能拿到自己发的那条消息的 id。上游把它藏在 `MessageUtils` 内部副作用里，是不可取的。

---

## 3. 轻量化方案

### 3.1 依赖瘦身（分三档）

**第一档：必删（安全，无功能损失）**

| 包 | 体积 | 理由 |
|---|---:|---|
| `nonebot-adapter-onebot` | — | 无 QQ |
| `asyncpg` | ~11 MB | 换 SQLite |
| `aiomysql` | ~1 MB | 换 SQLite |
| `alibabacloud_devops` | ~7 MB | 插件商店阿里云依赖，TG 版商店用 GitHub/本地源 |
| `virtualenv` | ~7 MB | 构建期依赖，不属于运行时 |
| `ray` / `tensorflow` 等（若存在） | — | 核对 `pyproject` |

**第二档：按需（与功能开关绑定）**

| 包 | 体积 | 触发条件 |
|---|---:|---|
| `playwright` | ~130 MB | 仅当 `renderer.enabled = true` |
| `matplotlib` + `numpy` | ~40 MB | 仅统计/图表插件开启 |
| `jieba` | ~37 MB | 仅当启用中文分词相关插件 |
| `scipy` | ~83 MB | ⚠️ **上游用途不明**，需实测是否有插件 import；无则删 |
| `redis` | ~4 MB | 仅当 `cache.backend = redis`（默认 `memory`） |

**第三档：替代（用更轻的库换掉）**

| 组件 | 处置 | 收益/风险 |
|---|---|---|
| `Tortoise ORM` | **保留** | 迁移成本最低，SQLite 支持良好，无需重写 DAO |
| `nonebot2` | 争议项，见 §3.2 | −30~40 MB，但丢失第三方插件生态 |
| `fastapi + uvicorn + pyjwt` | 移入 `webui` 可选插件 | −50 MB |
| `apscheduler` | **保留** | 体积小，被动技能必需 |
| `ruamel.yaml` → `PyYAML` | 可选替换 | −2 MB，但会丢注释保留能力，建议保留原方案 |
| `aerich` | **保留**（仅迁移期） | 运行时不依赖 |

### 3.2 ⚠️ 最大争议：是否继续用 NoneBot2

这是一个需要你拍板的架构决策（我把它并入 **D1 的子问题**）：

| | 保留 NoneBot2 | 移除，直接用 `aiogram` / `python-telegram-bot` |
|---|---|---|
| 插件生态 | ✅ 可直接装 nb 生态插件 | ❌ 生态隔离，第三方插件需适配 |
| 依赖体积 | −30~40 MB | ✅ 更轻（`aiogram` 约 2 MB） |
| 代码量 | 受 matcher 框架约束 | ✅ 管道完全可控，不会被框架语义拖累 |
| 学习/调试成本 | driver / adapter / matcher 三层抽象 | ✅ 一层 |
| 上游兼容 | ✅ `PluginMetadata` 可直接用 `plugin_metadata` | 需自建等价机制 |
| 4,600 行权限栈复发风险 | ⚠️ 较高（matcher priority 的坑会诱使人再打补丁） | ✅ 低 |

**我的推荐：把 NoneBot2 限制在插件层的路由角色（`Matcher` / `Alconna`），不允许这些语义渗透进内核层。**

理由很实际：**真寻最有价值的第三方资产是它的插件生态**，而那个生态建立在 nb 之上。完全脱离意味着所有第三方插件作废。折中方案是——nb 管「路由」，我们管「权限/限制/配置」，两者通过一条明确接口隔开。

> 如果你明确说「不需要任何第三方 nb 插件」→ 那么移除 nb，换来 ~40MB 和彻底的可控性，是更好的选择。**请就此项给出指示。**

### 3.3 渲染器可插拔（轻量化的最大杠杆）

上游 `services/renderer/engine.py` 用 Playwright 做 HTML→PNG，是所有体积问题的根源。

设计成接口：

```
RendererPort (抽象)
├── TextRenderer    默认实现，输出 Markdown 文本      ← 零依赖
├── PillowRenderer  轻量图片（签到卡/排行榜）          ← + Pillow (已装)
└── HtmlRenderer    Jinja2 + Chromium               ← + playwright (可选)
```

插件侧统一调用 `await ctx.render(template, data)`，**不知道背后是哪一种**。配置项 `renderer.engine` 决定。

收益：

| 部署档位 | 依赖体积 | 浏览器 | 能力 |
|---|---:|---|---|
| **默认安装（D2 定案）** | ~150 MB | 不需要 | 渲染开启，引擎 = **Pillow**；卡片/排行榜为轻量图片 |
| 切换 `engine=html` | ~280 MB | 需 300 MB | 视觉与上游完全等价 |
| **关闭渲染**（纯文本） | ~95 MB | 不需要 | 全部功能可用，帮助/排行榜降级为 Markdown |

> **定案**：渲染器默认开启，引擎默认 `pillow`。理由——既满足「开箱就有图片」的体验诉求，又把 Chromium 的 300 MB 变成可选项。想进一步瘦身到 95 MB，关闭渲染即可（见 §0.3）。

### 3.4 存储

| 场景 | 建议 |
|---|---|
| 个人/单群/≤20 群 | **SQLite**，WAL 模式，`busy_timeout=5000` |
| ≥50 活跃群 / 多实例 | PostgreSQL（保留适配，不默认依赖） |
| 缓存 | 内存字典（默认）；可选 Redis |

⚠️ SQLite 注意点（写进规范）：
- 所有写操作走 `core/services` 的 DAO，禁止插件裸写 SQL（对应删掉 `sql_list`）
- 高频计数（如调用次数）用**内存缓冲 + 定时落盘**，避免每次调用写库
- 迁移脚本使用 Tortoise migrations 或 Aerich，禁止运行时自动 `ALTER`

---

## 4. Telegram 语义适配：与 v2.0 的增量

v2.0 已给出 20 项功能的保真度结论，此处不再重复，只补 v2.0 未覆盖、但在 TG 下**会影响插件设计**的部分。

### 4.1 硬约束清单（插件作者必须知道）

| 约束 | 数值/规则 | 对插件的影响 |
|---|---|---|
| 命令语法 | `/[a-z0-9_]{1,32}`，**不支持中文，不支持空格** | 🔴 **见 §5.5，最大的设计冲击** |
| `setMyCommands` 上限 | 100 条/bot | 101+ 命令自动降级为文本匹配 |
| 消息长度 | ≤ 4,096 字符 | 帮助菜单必须分页 |
| 图片大小 | ≤ 10 MB | 渲染产出需检查体积 |
| 群内发送速率 | ~20 条/分钟/群 | ⚠️ **广播类插件必须走内核统一限流器**，否则触发 429 导致全 bot 被限速 |
| 撤回他人消息 | 需管理员权限且 ≤48h | 撤回插件需声明 `required_bot_perm: can_delete_messages` |
| 用户名 | `username` 可为 `None` | 显示逻辑必须有 fallback（用 `full_name`） |
| 私聊发起 | 需用户先点过 `/start` | 广播/主动私信只能发给已交互用户 |

### 4.2 权限模型映射（上游已归一化，零改动）

```
TG ChatMemberStatus     Role(内部)       Level
creator            →    OWNER           100
administrator      →    ADMINISTRATOR    10
member/restricted  →    MEMBER           0  ← 受限于 GroupConsole.level 覆盖
```

per-platform 差异已被 `Role` 吸收。

### 4.3 命令作用域：TG 原生能力反超 QQ

这是 TG 相对 OneBot 的**增强点**，应主动利用：

| `setMyCommands` scope | 对应内部语义 |
|---|---|
| `all_private_chats` | 私聊可见命令，任何用户与我私聊时都能补全 |
| `all_group_chats` | 群内普通用户可见（`PluginType.NORMAL`） |
| `chat_administrators` | 仅群管理员可见（`PluginType.ADMIN`） |
| `chat_member` | 单用户定制（可用于「超级用户专属命令」） |

**设计价值**：QQ 时代权限只能「执行时拦截」，TG 可以「**输入框里就不出现**」。同一套 `PluginType` 数据，在 TG 上能产出比 QQ 更好的体验。这一点写进 §5.5。

### 4.4 事件驱动群同步（继承 v2.0 §2.1）

三层仍在：事件入库 → `get_chat` 按需补全 → `get_chat_administrators` 同步权限。
新增一条规范：**每次 `get_chat_member` 结果写 60 秒缓存**，避免高频插件打爆 API。

---

## 5. 插件系统设计 ★

> 本章是本次文档的主体。**目标：接口小到能画在一张纸上，严格到能让别人写出第三方插件。**

### 5.1 设计原则

1. **声明式优先。** 插件的元数据、命令、配置、限制，写成纯数据结构，可被静态读取，不依赖 import 副作用。
2. **零隐藏副作用。** 不允许「import 时就自动注册」。所有注册经显式 `setup()` 调用。
3. **失败要早。** 命令冲突、依赖缺失在**启动期**报错，不放运行期。
4. **无平台语义。** 插件里不出现 `chat_id` / `message_id` / `restrict_chat_member` 这类平台词。
5. **配置可序列化。** 所有配置项必须能 JSON Schema 表达（废除上游的 `arg_parser: Callable`）。

### 5.2 目录与命名规范

```
plugins/
└── sign_in/                       # 目录名 = plugin key（全小写下划线）
    ├── plugin.py                  # 【必需】入口，含 manifest 与 handler
    ├── models.py                  # 可选，本插件的数据模型
    ├── data_source.py             # 可选，业务逻辑
    ├── templates/                 # 可选，渲染模板
    │   └── sign_card.j2
    ├── migrations/                # 可选，数据库迁移
    └── README.md                  # 可选
```

**命名硬规则**（注册时校验）：

| 对象 | 规则 | 示例 |
|---|---|---|
| plugin key | `^[a-z][a-z0-9_]{2,31}$`，全局唯一 | `sign_in` ❌ `SignIn` ❌ `签到` |
| 配置 key | `^[A-Z][A-Z0-9_]{1,63}$`，插件内唯一 | `MAX_SIGN_GOLD` |
| 命令 key | 全局唯一（跨插件） | `sign` |
| 事件/任务 id | `<plugin_key>:<name>` | `sign_in:daily_reset` |
| 回调数据 callback_data | `k=<key>&a=<action>&p=<param>`，≤64 字节 | `k=sign_in&a=rank` |

> `callback_data` 有 **64 字节上限**（TG 硬限制），必须写进规范并在注册时校验长度，否则运行时才会炸。这是很多 TG bot 的常见坑。

### 5.3 插件契约：Manifest（完整定义）

继承上游 `PluginExtraData` 的字段名与语义，重组织为严格 schema：

```python
@dataclass(frozen=True)
class PluginManifest:
    # ---- 身份 ----
    key: str                        # sign_in
    name: str                       # 签到            （继承 upstream `name`）
    version: str                    # 1.0.0            （建议 SemVer，上游为裸字符串）
    author: str                     # HibiKier
    description: str
    usage: str                      # 帮助文本主体
    superuser_help: str | None = None
    introduction: str | None = None # BOT 自我介绍时的自我介绍
    precautions: list[str] | None = None

    # ---- 分类（继承 PluginType / menu_type） ----
    plugin_type: PluginType = PluginType.NORMAL
    menu_type: str = "功能"
    is_show: bool = True            # 是否显示在帮助
    parent: str | None = None       # 父插件 key（对应 PARENT）

    # ---- 权限与经济（继承 PluginSetting，扁平化） ----
    level: int = 5                  # 所需群权限
    admin_level: int | None = None  # 管理员插件所需等级
    default_status: bool = True     # 进群默认开关
    limit_superuser: bool = False   # 是否受限 superuser（False=超级用户不受此插件限制）
    cost_gold: int = 0
    impression: float = 0.0

    # ---- 命令 ----
    cmds: list[Cmd] = ()
    aliases: set[str] = frozenset()

    # ---- 声明式资源 ----
    configs: list[ConfigSpec] = ()
    limits: list[LimitSpec] = ()
    tasks: list[TaskSpec] = ()
    events: list[EventSpec] = ()

    # ---- 依赖 ----
    requires_core: str = ">=1.0,<2.0"    # 声明核心版本范围 ★ 新增
    requires: list[str] = ()             # 依赖的其他插件 key ★ 新增
    requires_services: list[str] = ()    # 依赖的服务，如 ["gold","impression"]
    bot_permissions: set[BotPerm] = frozenset()   # ★ 新增，TG 需要
    #   BotPerm ∈ {can_delete_messages, can_restrict_members,
    #              can_promote_members, can_invite_users, can_pin_messages}

    ignore_prompt: bool = False
    ignore_statistics: bool = False
```

**相对上游的新增/变更及其理由**：

| 变更 | 理由 |
|---|---|
| `requires_core`（SemVer 范围） | 上游无。第三方插件作者无法知道自己的插件兼容哪个版本，这是生态的前提 |
| `requires`（插件间依赖） | 上游依赖靠隐式 import 顺序，脆弱 |
| `bot_permissions` | TG 特有：撤回/禁言需要 bot 有对应管理员权限，可在启动时自检并告警 |
| `PluginSetting` 扁平化 | 上游嵌套一层没啥收益，扁平后注册器代码更短 |
| `version` 改 SemVer | 便于 `requires_core` 做范围比较 |

### 5.4 命令契约 `Cmd` ★ 受 TG 约束最重的一项

```python
@dataclass(frozen=True)
class Param:
    name: str           # num
    type: Literal["int","str","bool","word","greedy"]
    required: bool = False
    default: Any = None
    help: str = ""

@dataclass(frozen=True)
class Cmd:
    key: str                       # sign_rank        全局唯一，内部标识
    pattern: str                   # "签到排行"  ★ 中文/文本匹配模式（主）
    slash: str | None = None       # "rank"      ★ TG 原生斜杠命令（补全入口）
    aliases: list[str] = ()        # ["好感度排行","签到排行榜"]
    params: list[Param] = ()
    scope: PluginType = PluginType.NORMAL   # 决定 setMyCommands 的 scope
    help: str = ""
    examples: list[Example] = ()
```

### 5.5 🔴 硬约束：中文命令在 Telegram 上不能注册为原生命令

这是本次新发现、且**直接决定插件 API 形态**的问题，必须单列。

**事实**：

```
Telegram Bot API 官方约束：
  命令格式  /command
  command ∈ [a-z0-9_]{1,32}    ← 只允许小写 + 数字 + 下划线
  /签到  → BotFather 拒绝注册
```

而真寻的全部命令是**中文**的（签到、我的签到、好感度排行…）。

**因此采用「双轨命令模型」**：

| 轨道 | 载体 | 触发方式 | 注册到 `setMyCommands` | 用途 |
|---|---|---|---|---|
| **Slash 轨** | `Cmd.slash`（英文） | Telegram 自动补全 + 点击 | ✅ 注册（受 100 条限制） | **发现性**：用户点 `/` 就知道有什么 |
| **Text 轨** | `Cmd.pattern` + `aliases`（中文） | 文本消息前缀匹配 | ❌ 不注册 | **习惯**：老用户继续打中文 |

两条轨道指向**同一个 handler**，内核负责归一化：

```
用户发送 "签到"           → Text 轨命中 → CommandRef(key=sign)
用户点击 /sign            → Slash 轨命中 → CommandRef(key=sign)
                                             ↓
                                       同一个 handler
```

**Slash 命令自动生成规则**（当作者未提供 `slash` 时）：

```
key = sign_rank   →  slash = "sign_rank"        （直接用 key，保证唯一、合法）
```

建议：**斜杠命令采用 `<plugin>_<action>` 命名空间式命名**。理由：
- 天然避开跨插件冲突（这是 100 条限制下最宝贵的资源）
- 补全列表里 `/sign_` 一打 E，就把签到插件的所有子命令全列出来，体验比 `\签到` 更结构化
- 不需要为每个命令想一个英文单词

**100 条限制的处理策略**（写进内核规范）：

```
1. 按优先级排序：NORMAL > ADMIN > SUPERUSER > HIDDEN
2. 仅前 100 条写入 setMyCommands
3. 超出部分：仍走 Text 轨，功能完整，仅失去自动补全
4. 启动日志 WARN 列出被降级的命令，管理员可通过残缺配置文件 `degraded_commands` 手动调整
```

> **待确认 D5**：你也可以选择「完全放弃中文，全端用英文斜杠命令」。好处是完全贴合 TG 原生范式、无双轨复杂度；代价是不再是"真寻"，老用户习惯全部作废。**我推荐双轨。**

### 5.6 调用管道：用 ≤700 行取代 4,600 行

这是本次重构的核心收益点。上游 14 个 auth 文件做的事，本质就是**顺序执行一串判定**。我们不把它做成流水线框架，做成一个**显式的 Guard 列表**。

```python
# core/kernel/pipeline.py
PIPELINE: list[Guard] = [
    ResolveContext,   # 解析 actor / chat / role / 群记录（带缓存）
    BuildCommand,     # 文本或斜杠 → CommandRef
    MergeConfig,      # 全局配置 ⊕ 群级配置 → 本次生效配置
    GuardBan,         # 黑名单/封禁用户
    GuardSwitch,      # 全局开关 & 群开关
    GuardLevel,       # 权限等级（Role → level）
    GuardCost,        # 金币 / 好感度扣除（原子）
    GuardLimit,       # CD / 次数 / BLOCK
    Dispatch,         # → handler
]
```

每个 Guard 是一个纯函数：

```python
async def guard(ctx: CallContext) -> Verdict:
    return ALLOW | DENY(reason="插件已在群内关闭", tip="发送 /enable sign_in 开启")
```

**关键决策：不用优先级数字，用列表顺序。**

> 上游之所以长出 priority/cascade/trace 那套东西，是因为 `matcher priority` 是一个**分散在各处、无全景**的数字。改成一处列表后，执行顺序肉眼可见，调试时打一行 `logger.debug(pipeline_trace)` 就够了——而不需要 `auth_trace.py`。

配套：

| 设施 | 说明 | 替代了上游的 |
|---|---|---|
| `CallContext`（不可变快照） | 一次调用的全部输入 | `auth_snapshot.py` |
| 单一插件开关表（全局/群二级） | `plugin_switch(plugin_key, chat_id, enabled)` | `auth_activation.py` 52KB |
| 统一判定出口返回 `Verdict` | 只有允许/拒绝两种结果 | `auth_checker.py` 54KB |
| `CostGuard` 原子扣费 | 成功才扣，失败不扣 | `auth_side_effect.py` |
| 无 fallback 机制 | 不兼容就直接报错 | `auth_legacy_fallback.py` / `auth_patch_guard.py` |

### 5.7 配置层

三级覆盖，优先级从低到高：

```
default_value（Manifest 声明）
    ↓ 被覆盖
全局配置 core_config.yaml / DB
    ↓ 被覆盖
群级配置 group_config:<chat_id>
```

```python
@dataclass(frozen=True)
class ConfigSpec:
    key: str                # MAX_SIGN_GOLD
    type: CFGType           # int | float | str | bool | list[T] | json
    default: Any
    help: str
    scope: Literal["global","group"] = "global"
    min_value / max_value: float | None = None    # ★ 新增，避免脏值炸业务逻辑
    choices: list[Any] | None = None              # ★ 新增
```

**相对上游的改动**：`arg_parser: Callable` → 删除，改为 `type` + `choices` + 范围。理由：Callable 不可序列化，WebUI 无法渲染表单、也无法校验 YAML。

访问方式（插件侧）：

```python
gold_cap = await ctx.config("MAX_SIGN_GOLD")   # 自动三级覆盖
```

### 5.8 限制器

继承上游 `BaseBlock` 语义，字段沿用：

```python
@dataclass(frozen=True)
class LimitSpec:
    type: PluginLimitType        # CD | COUNT | BLOCK
    status: bool = True
    check_type: BlockType = BlockType.ALL        # PRIVATE | GROUP | ALL
    watch_type: LimitWatchType = LimitWatchType.USER   # USER | GROUP | ALL
    result: str | None = None    # 拒绝时回复
    cd: int | None = None                 # type=CD，秒
    max_count: int | None = None          # type=COUNT
    period: str | None = None             # type=COUNT，"1d" | "1h"  ★ 新增（上游未定义周期）
   # type=BLOCK: 永久阻断，由管理面拉黑
```

> **上游的一个语义空洞**：`PluginCountBlock` 只有 `max_count`，没有「多久之内」。计数窗口在哪定义，在下游实现里是隐式的。此处显式补 `period`。

存储：`plugin_limit` 表保留，键为 `(plugin_key, watch_type, target_id)`，COUNT 的窗口用**滚动过期键**而非定时扫描。

### 5.9 被动任务 / 定时任务

继承上游 `Task` 语义并收紧：

```python
@dataclass(frozen=True)
class TaskSpec:
    key: str                     # 全局唯一 "<plugin>:<name>"
    name: str                    # 显示名
    func: Callable               # async (ctx: TaskContext) -> None
    trigger: Literal["cron","interval"]
    cron: str | None = None      # "0 8 * * *"
    seconds: int | None = None
    default_status: bool = True  # 进群默认开关（继承 create_status 语义）
    check: Callable | None = None      # 可选，运行前置条件
    max_instances: int = 1       # ★ 防止积压
    misfire_grace_time: int = 60 # ★ 错过多久就不补跑（防止重启雪崩）
```

**必须遵守**：任务默认关闭广播；`misfire_grace_time` 必填，否则机器人重启时会一次性补跑几十个群的任务，直接触发 TG 限流。

### 5.10 事件订阅

```python
@dataclass(frozen=True)
class EventSpec:
    kind: Literal["join","leave","member_update","join_request","text","callback"]
    func: Callable
    priority: int = 50
```

TG 相关：

| kind | TG 来源 | 备注 |
|---|---|---|
| `join` | `message.new_chat_members` | 群欢迎插件用 |
| `join_request` | `chat_join_request` | 对应上游 `fg_request` 模型，语义可直接复用 |
| `member_update` | `chat_member` updated | 管理员变更监控，对应上游管理员监听 |

### 5.11 生命周期与注册流程

```
[启动] discover → validate → resolve → register → migrate → activate → broadcast_commands
[运行] (pipeline)
[停止] deactivate → close
```

**① discover**：扫描 `plugins/*/plugin.py`，动态 import。

**② validate**（全部失败都在此步抛出，快速失败）：

| 检查 | 失败行为 |
|---|---|
| key 格式 & 全局唯一 | ❌ 启动失败 |
| `requires_core` 与当前内核 SemVer 匹配 | ❌ 启动失败，提示版本不符 |
| `requires` 依赖插件存在且已加载 | ❌ 启动失败（并有环检测） |
| 命令 `key` / `slash` / `pattern` 全局无冲突 | ❌ 启动失败，打印冲突双方 |
| 配置 key 格式、类型与 `default` 一致 | ❌ 启动失败 |
| `callback_data` ≤ 64 字节 | ❌ 启动失败 |
| `bot_permissions` 声明，但实测 bot 在部分群缺权 | ⚠️ WARN + 该群自动降级关闭该命令 |
| `slash` 计数 > 100 | ⚠️ WARN，超出的降级为文本匹配（功能不丢，仅失去补全） |
| 中文 `pattern` 与其他命令互为前缀 | ❌ 启动失败，要求显式声明优先级或改名 |
| 插件目录缺少 `plugin.py` | ⚠️ WARN 并跳过，不记为插件 |

**③ resolve**：拓扑排序（依赖 + priority），确定 pipeline 与 handler 注册顺序。

**④ register**：写 `plugin_info` 表。

```sql
INSERT INTO plugin_info (module, module_path, name, version, level, ...)
ON CONFLICT(module) DO UPDATE SET version=?, name=?
-- ★ 关键：不覆盖 status / default_status / load_status
```

> **这是移植最容易踩的坑**：重启时如果 upsert 覆盖了 `status`，管理员在群里关掉的插件会被"复活"。上游此点需复核，**本版明确写在规范里**。

**⑤ migrate**：执行插件自己的 `migrations/`，每个插件一张 `_plugin_migrations` 记录版本号。

**⑥ activate**：注册 matcher、定时任务、事件订阅，调用插件的 `setup()`。

**⑦ broadcast_commands**：向 TG 发 `setMyCommands`，按 scope 分组，见 §5.5 的 100 条策略。

### 5.12 插件对外可用 API（白名单）

插件**只允许**通过 `ctx` 使用下列能力，禁止直接引用平台层：

```python
class CallContext:
    # 读取
    event: UnifiedEvent
    user: UserView            # id / level / gold / impression
    group: GroupView | None
    plugin: PluginView        # 本插件运行时配置（已三级覆盖）

    async def config(self, key: str) -> Any
    async def cache(self, key: str, ttl: int = 60) -> CacheView

    # 输出  ★ 返回值统一携带 message_id
    async def reply(self, content: Renderable) -> SentMessage
    async def reply_image(self, template: str, data: dict) -> SentMessage
    async def edit(self, msg: SentMessage, content: Renderable) -> None
    async def recall(self, msg: SentMessage, delay: int = 0) -> bool
    async def keyboard(self, buttons: list[list[Button]]) -> None   # TG InlineKeyboard

    # 数据
    async def gold(self, delta: int, reason: str) -> bool
    async def impression(self, delta: float) -> bool
    async def db(self) -> DAO

    # 平台动作（语义化，不含 TG 词汇）
    async def mute(self, user_id: str, duration: int) -> bool
    async def unmute(self, user_id: str) -> bool
    async def kick(self, user_id: str) -> bool
    async def ban(self, user_id: str) -> bool
    async def unban(self, user_id: str) -> bool
    async def leave(self) -> bool
```

**注意 `mute/kick/ban/leave` 都是「请求」，返回 bool 表示是否成功**——因为 TG 下 bot 权限不足会静默失败。上游 QQ 版在非 qq 平台下是静默 no-op（v2.0 §2.3 已指出），这个坏习惯不能在 TG 版延续。

### 5.13 第三方插件接入协议

目录： `plugins_ext/`（外部插件，不随主仓库发布）

一个第三方插件最小集合：

```
my_plugin/
├── plugin.py      # 含 manifest 与 handler
└── plugin.toml    # 可选元信息：author / repo / license / core_range
```

安装流程：

```
1. 放入 plugins_ext/<key>/
2. （若含依赖）写入 requirements-lock，提示 pip install
3. 重启 → discover 自动装载
4. 首次出现的新插件：status=True, default_status=True
```

启动日志示例（规范输出格式）：

```
[plugin] ✔ sign_in        v1.0.0    commands=6   scope=normal
[plugin] ✔ shop           v0.9.2    commands=4   scope=normal
[plugin] ⚠ fun_plugin     v0.1.0    slash 冲突: /rank 已被 sign_in 占用
[plugin] ✘ bad_plugin     v0.1.0    requires_core=">=2.0" 不满足 (current 1.4.0)
```

### 5.14 一个完整插件示例（形态参考，非最终代码）

```python
# plugins/sign_in/plugin.py
from core.kernel import PluginManifest, Cmd, Param, ConfigSpec, LimitSpec, PluginType

manifest = PluginManifest(
    key="sign_in",
    name="签到",
    version="1.0.0",
    author="HibiKier",
    description="每日签到，证明你在这里",
    usage="每日签到会影响色图概率和开箱次数…",
    plugin_type=PluginType.NORMAL,
    requires_core=">=1.0,<2.0",
    requires_services=["gold", "impression"],
    cmds=[
        Cmd(
            key="sign",
            pattern="签到",                    # 中文主轨
            slash="sign_in",                   # TG 补全轨
            aliases=["每日签到"],
            help="每日签到",
        ),
        Cmd(
            key="sign_rank",
            pattern="好感度排行",
            slash="sign_in_rank",
            aliases=["签到排行", "好感度总排行"],
            params=[Param("num", "int", default=10, help="显示人数")],
            help="显示好感度排行榜",
        ),
    ],
    configs=[
        ConfigSpec("MAX_SIGN_GOLD", int, 200, "签到好感度加成额外获得的最大金币数", min_value=0),
        ConfigSpec("SIGN_CARD1_PROB", float, 0.2, "双倍加持卡Ⅰ掉落概率", min_value=0, max_value=1),
    ],
    limits=[LimitSpec.cd(cd=5, watch_type="USER")],
)

async def setup(ctx):
    """可选：注册事件/任务/初始化资源（不做 matcher 注册，那是框架的事）"""

async def handle_sign(ctx): ...
async def handle_rank(ctx): ...
```

对照上游同一个插件：上游需要 `on_alconna` + 6 个 `shortcut()` + `AlconnaArparma` 注入，本设计用 `pattern` + `aliases` + `params` 一个列表表达，且**中文/斜杠/别名三件事在同一处可见**。

---

## 6. 实施路线（路线 C）

| 阶段 | 内容 | 产出物 | 人日 |
|---|---|---|---:|
| **P0 奠基** | UnifiedEvent、Context、pipeline 骨架、SQLite+models 迁移 | 空壳机器人可回 `/ping` | 3 |
| **P1 内核** | registry / validate / config 三级 / limits / tasks / 命令广播 | 插件可装载，配置可读改 | 5 |
| **P2 平台适配** | TG adapter / codec / 限流器 / setMyCommands 作用域 | 双轨命令跑通 | 4 |
| **P3 核心服务** | user / group / gold / impression / permission | 业务地基 | 4 |
| **P4 内置插件** | 帮每/签到/商店/好感度/权限管理/群管理/统计（逐个重写一个） | 每插件 0.5~1.5 天 | 10–14 |
| **P5 可选层** | TextRenderer（默认）+ 可选 Pillow/HtmlRenderer；可选 WebUI | 功能开关生效 | 3 |
| **P6 收尾** | 依赖瘦身验收、冒烟、文档 | 可交付 | 3 |
| | | **合计** | **32–36 人日** |

> 比 v2.0 的 10–14 人日**高**，原因是 v2.0 假设的是「路线 A：Fork 减法」。路线 C 前期成本高，但**不带技术债尾巴**。这是用 3 周时间，换未来不必再对着 4,600 行权限栈做考古。

**里程碑检查点**：P2 结束时应能回答「中文命令能不能跑通 + 自动补全出不出来」。这是整个方案的风险集中点，必须先验证。

---

## 7. 验收标准（可量化）

| 项 | 标准 |
|---|---|
| 冷启动 | `TELEGRAM_TOKEN=xxx python -m zxtg` 即可运行，无需其它外部服务 |
| 依赖体积 | `du -sh .venv` ≤ 95 MB（text-only 档） |
| 启动耗时 | ≤ 3 秒进入 ready（SQLite + ≤40 插件） |
| 常驻内存 | ≤ 120 MB（无浏览器） |
| 命令冲突 | 构造冲突插件，必须启动失败且打印冲突双方 |
| 配置不复活 | 在群内关闭某插件 → 重启 → 该群仍处于关闭状态 |
| 100 命令降级 | 构造 120 个命令，第 101 个必须降级但仍可用文本触发 |
| 限流保护 | 群内连发 50 条，不得出现 429；应自动退避 |
| 回溯式核对 | 撤回/禁言在 bot 无权限的群里，必须返回 `False` + 可读提示，不静默 |
| 插件泊岸 | 第三方按 §5.13 放入目录，重启即可用，无需改主仓库任何代码 |

---

## 8. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| **命令 100 条上限** | 插件多时补全列表被截断 | 命名空间命名 + 降级为文本 + 配置 `priority` 排序 |
| **中文 `pattern` 误命中** | 群里有插件 `pattern` 前缀是别人的命令 | 前缀匹配用「词边界」，注册期做前缀冲突检测 |
| SQLite 写竞争 | 高并发签到丢数据 | WAL + busy_timeout + 内存缓冲批量落盘 |
| 广播触发 TG 限流 | bot 被限流数分钟 | 强制所有广播走同一个 per-chat 令牌桶，`retry_after` 自动退避 |
| 误 username | 用户名 None 导致渲染崩溃 | `Actor.display` 属性内建 fallback 到 `full_name` |
| 渲染器依赖膨胀 | 体积回到 550MB | text-only 为默认，安装渲染器是显式动作 |
| 路线 C 前期无产出 | 前 2 周看不到「能用的机器人」 | P2 结束必须做 milestone 演示 |
| 与上游 diverge | 上游更新无法合并 | **明确接受**：本方案是 fork 而非 upstream 分支，不再同步上游代码，仅同步数据契约 |

---

## 9. 开放问题

| # | 问题 | 当前假设 |
|---|---|---|
| Q1 | 是否继续依赖 NoneBot2（§3.2） | 假设：保留给插件层，内核层隔离 |
| Q2 | 是否需要保留第三方 nb 插件生态兼容 | 假设：需要（这是保留 nb 的唯一理由） |
| Q3 | `scipy` 在上游的真实用途 | 未实测，需在移植前 `grep` 确认 |
| Q4 | WebUI 是否要做 | 假设：可选插件，默认关 |
| Q5 | 是否需要多语言 / i18n | 假设：默认中文，结构预留 |
| Q6 | 是否需要 AI / LLM 相关（`smart_tools`） | 假设：延后，槽位预留 |
| Q7 | 目标部署形态：自建 Docker 还是本地跑 | 假设：本地 / 单容器 |

---

## 附录 A：本次实测数据来源

| 数据 | 来源 |
|---|---|
| hooks 目录文件大小表 | GitHub Contents API `contents/zhenxun/builtin_plugins/hooks`，main 分支 |
| `PluginExtraData` / `RegisterConfig` / `Command` / `Task` / 各 Block 字段 | `zhenxun/configs/utils/models.py` |
| `PluginType` / `BlockType` / `PluginLimitType` / `LimitWatchType` 枚举值 | `zhenxun/utils/enum.py` |
| `plugin_info` 表 26 字段 | `zhenxun/models/plugin_info.py` |
| 插件元数据写法（`__plugin_meta__` + `PluginExtraData(...).to_dict()`） | `zhenxun/builtin_plugins/sign_in/__init__.py` |
| `PluginInit` install/remove 生命周期机制 | `zhenxun/services/plugin_init.py` |
| 其余功能保真度结论 | 继承 `zhenxun_telegram_port_plan.md` v2.0 |

## 附录 B：本版相对 v2.0 的增量

1. **新增实测**：hooks/auth 系列 187KB / ~4,600 行的复杂度账单（§1.1）
2. **新增判断**：把「移植」改为「重写」，给出三条路线取舍（§0.1）
3. **新增硬约束**：Telegram 命令不支持中文 → 双轨命令模型（§5.5）——这条改变了插件 API 形态
4. **新增发现**：`setMyCommands` scope 可用于复现 PluginType 权限（§4.3，TG 反超 QQ）
5. **新增发现**：`callback_data` 64 字节上限、`PluginCountBlock` 缺周期字段两个上游空洞（§5.2 / §5.8）
6. **新增规范**：完整插件体系 §5（契约/命令/配置/限制/任务/事件/生命周期/API 白名单/第三方协议）
7. **新增决策**：渲染器与 WebUI 降级为可选插件，把体积从 551MB 降到 ~95MB（§3.3）
8. **新增提醒**：插件注册不得覆盖用户已设置的 status（§5.11 ④）
