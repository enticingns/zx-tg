# ZX-TG 需求规格说明书（SRS）v1.0

| 项 | 内容 |
|---|---|
| 项目代号 | **ZX-TG**（绪山真寻 Telegram 版） |
| 文档版本 | v1.0 |
| 创建日期 | 2026-10-15 |
| 上游参考 | `zhenxun-org/zhenxun_bot` @ main |
| 关联文档 | `zx-tg-design-v3.md`（架构与插件体系设计） |
| 文档状态 | 已评审决策，待实施 |

**修订记录**

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-15 | 基于 D1–D5 决策定稿，首次发布 |

---

## 1. 项目背景与目标

### 1.1 背景

上游 `zhenxun_bot` 是一个功能丰富的 QQ 机器人，基于 NoneBot2 + OneBot 协议实现。本项目目标为**将其移植到 Telegram 平台并同时进行轻量化重构**。

对上游源码的实测发现了一个决定性问题：

| 区域 | 实测规模 | 判断 |
|---|---:|---|
| `builtin_plugins/hooks/` 下 14 个 auth 相关文件 | **187,454 字节 ≈ 4,600 行** | 权限校验系统复杂度失控 |
| 其中 `auth_checker.py` / `auth_activation.py` | 54,518 / 52,482 字节 | 单体过大 |
| 补丁类文件 | `auth_patch_guard` / `auth_legacy_fallback` / `auth_snapshot` / `auth_trace` / `auth_side_effect` | 考古层堆叠，无业务价值 |

这套权限逻辑的绝大多数分支是为 QQ/OneBot 的历史行为编写的，迁移到 Telegram 后全部作废。**沿用这套代码意味着要为已作废的分支承担永久维护成本。**

### 1.2 目标

| # | 目标 | 衡量方式 |
|---|---|---|
| G1 | 在 Telegram 平台上复现真寻的核心业务功能 | 见 §8 内置插件需求矩阵 |
| G2 | 运行时体积与复杂度大幅下降 | 默认安装 ≤150 MB；核心代码 ≤6,000 行（上游约 46,000 行） |
| G3 | 权限/限制/配置逻辑可被单人理解与维护 | 替代实现 ≤700 行，单一调用管道 |
| G4 | 数据契约与上游保持一致，降低认知与迁移成本 | `PluginExtraData` / `plugin_info` / 枚举值逐字继承 |
| G5 | 提供可被第三方使用的插件开发规范 | 第三方按规范投放目录，重启即可用，无需改动主仓库 |
| G6 | 部署门槛降至最低 | 仅需一个 Telegram Token，单进程，无需公网 IP/域名/SSL |

### 1.3 不在本期范围内（Out of Scope）

| 项 | 说明 |
|---|---|
| QQ / OneBot 支持 | 不保留任何 QQ 协议代码 |
| 多平台抽象层 | 仅通过内部边界隔离预留，不实现第二平台 |
| LLM / AI 对话能力 | 上游 `llm_manager`、`smart_tools` 延后，仅预留 Manifest 槽位 |
| 自动更新 | 容器化场景下不需要，改为手动升级流程 |
| 集群 / 多实例部署 | 单实例设计，SQLite 写竞争由缓冲队列缓解 |
| 与上游代码同步 | 本项目为**契约级 fork**，不同步上游代码，仅同步数据契约 |

---

## 2. 术语与缩略语

| 术语 | 含义 |
|---|---|
| **ZX-TG** | 本项目代号 |
| **上游** | `zhenxun-org/zhenxun_bot` |
| **契约** | 数据模型字段名、枚举值、配置项键名的集合，跨版本保持不变的部分 |
| **双轨命令** | 同一功能同时支持「中文文本触发」与「英文斜杠命令触发」的机制，见 FR-CMD |
| **Slash 轨** | 注册到 `setMyCommands`、可在 TG 输入框自动补全的英文命令轨 |
| **Text 轨** | 通过中文文本前缀匹配触发的命令轨 |
| **Guard** | 调用管道中的单个判定单元，返回允许/拒绝 |
| **Pipeline** | 由 Guard 组成的有序调用管道，取代上游分散的权限钩子 |
| **UnifiedEvent** | 平台无关的统一事件模型，内核唯一输入 |
| **被动技能 / Task** | 无需用户触发、由定时或事件驱动的群级功能开关项 |
| **PluginType** | 插件类型枚举（NORMAL / ADMIN / SUPERUSER / DEPENDANT / HIDDEN / PARENT） |
| **MoSCoW** | 需求优先级：Must / Should / Could / Won't |

---

## 3. 已定稿决策（约束性前提）

本需求文档以下述已拍板决策为前提，**后续需求不得与之冲突**。

| # | 决策点 | 决议 |
|---|---|---|
| **D1** | 重构路线 | **C：内核重写 + 数据契约继承 + 功能平移** |
| **D2** | 图片渲染 | **可选插件，默认开启**；默认引擎 `pillow`，`html` 引擎需显式配置 |
| **D3** | WebUI 管理后台 | **可选插件，默认开启**；默认监听 `127.0.0.1` |
| **D4** | 数据库 | **SQLite**（单文件，WAL 模式） |
| **D5** | 命令策略 | **双轨**：中文 Text 轨 + 英文 Slash 轨，同一 handler |

**D2/D3 的约束实现**：「默认开启」不得导致默认安装体积回退到上游水平，因此采用**默认开启 + 默认降档**：

- 渲染功能开启，但默认引擎为轻量 Pillow，不含 Chromium 二进制
- WebUI 开启，但默认仅本地回环监听，且不捆绑 `uvicorn` 生产级配置

参考体积矩阵：

| 安装档 | 依赖体积 | 浏览器 | 说明 |
|---|---:|---|---|
| `zxtg`（**默认**） | ~150 MB | 不需要 | 渲染开（Pillow）+ WebUI 开 |
| 切换 `render.engine=html` | ~280 MB | +300 MB | 视觉与上游等价 |
| `zxtg[lite]` | ~95 MB | 不需要 | 关闭渲染与 WebUI，纯文本 |

---

## 4. 用户与角色

| 角色 | 描述 | 主要诉求 |
|---|---|---|
| **普通群成员** | 群内使用功能的用户 | 签到、查询、娱乐功能，易发现命令 |
| **群管理员** | 管理单个群的用户 | 开关插件、设置权限、查看本群配置 |
| **超级用户** | Bot 所有者，跨群最高权限 | 全局插件管理、广播、退群、数据维护 |
| **插件开发者** | 编写第三方插件的人 | 清晰的契约、明确的报错、热重载 |
| **运维人员** | 部署与日常维护 | 单命令启动、可读日志、可诊断状态 |

**Telegram 角色映射**（FR 中统一以此为准）：

| TG `ChatMemberStatus` | 内部 Role | Level |
|---|---|---:|
| `creator` | OWNER | 100 |
| `administrator` | ADMINISTRATOR | 10 |
| `member` / `restricted` | MEMBER | 0 |

---

## 5. 系统范围

```
┌──────────────────────────────────────────────────┐
│ L4 插件层   plugins/ + plugins_ext/              │  业务
├──────────────────────────────────────────────────┤
│ L3 服务层   user / gold / impression / config    │  平台无关业务 │
├──────────────────────────────────────────────────┤
│ L2 内核层   registry / pipeline / lifecycle      │  ★ 重写核心
├──────────────────────────────────────────────────┤
│ L1 平台层   Telegram adapter / codec / rlmgr     │  TG 唯一实现
├──────────────────────────────────────────────────┤
│ L0 持久层   SQLite + Tortoise ORM                │
└──────────────────────────────────────────────────┘
```

**硬性边界（FR 层面强制）**：

| # | 边界 | 验证方式 |
|---|---|---|
| B1 | 插件不得引用平台层符号 | 静态导入检查，违规启动失败 |
| B2 | 平台层不得含业务语义词汇（签到/金币等） | 代码评审清单 |
| B3 | 内核不感知 Telegram 存在，仅认 `UnifiedEvent` | 无 `telegram` 相关 import |
| B4 | 插件不得直接访问数据库，须经 DAO | API 白名单约束 |

---

## 6. 功能性需求

> 优先级：**M** = Must（本期必须） / **S** = Should（重要但可延） / **C** = Could（锦上添花） / **W** = Won't（本期不做）

### 6.1 内核与生命周期 `FR-CORE`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-CORE-01 | 系统须支持单进程、长轮询模式启动，无需公网 IP / 域名 / SSL / 反向代理 | **M** |
| FR-CORE-02 | 仅通过环境变量或配置文件中的 `TELEGRAM_TOKEN` 即可完成最小启动 | **M** |
| FR-CORE-03 | 启动流程须划分为 discover → validate → resolve → register → migrate → activate → broadcast_commands 七个阶段，各阶段可单独输出日志 | **M** |
| FR-CORE-04 | 若 Telegram 长轮询连接断开，须自动退避重连，退避上限 60 秒 | **M** |
| FR-CORE-05 | 单个插件 Handler 抛出未捕获异常时，不得导致整个 Bot 进程退出 | **M** |
| FR-CORE-06 | 须提供优雅停机：停止接收新消息、完成队列任务、关闭数据库连接 | **M** |
| FR-CORE-07 | 须提供统一的 `UnifiedEvent` 模型，字段含 actor / role / chat / kind / text / command / message_id / raw | **M** |
| FR-CORE-08 | `UnifiedEvent.raw` 仅供平台层与逃生排查使用，插件层禁止使用 | **M** |
| FR-CORE-09 | 须支持插件热重载（不重启进程重新装载单个插件） | **S** |
| FR-CORE-10 | 启动时须输出插件装载汇总表，含名称、版本、命令数、状态（✔/⚠/✘） | **M** |

### 6.2 插件注册与校验 `FR-PLG`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-PLG-01 | 插件入口须为 `plugins/<key>/plugin.py`，其中定义 `manifest` 对象 | **M** |
| FR-PLG-02 | `manifest` 须以声明式数据结构表达，可被静态读取，不得依赖 import 副作用完成注册 | **M** |
| FR-PLG-03 | 插件 key 须匹配 `^[a-z][a-z0-9_]{2,31}$` 且全局唯一 | **M** |
| FR-PLG-04 | 以下校验失败须导致**启动失败**并明确指出冲突双方：key 重复、命令 key/slash/pattern 冲突、依赖缺失、依赖成环、配置键格式非法、`callback_data` > 64 字节 | **M** |
| FR-PLG-05 | 以下情况须降级为**警告**并继续启动：声明的 bot 权限在部分群缺失、Slash 命令数超过 100、插件目录缺少 `plugin.py` | **M** |
| FR-PLG-06 | `manifest` 须支持声明 `requires_core`（SemVer 范围），不满足时拒绝加载 | **M** |
| FR-PLG-07 | `manifest` 须支持声明 `requires`（依赖的其他插件 key），加载前完成拓扑排序 | **M** |
| FR-PLG-08 | 注册写库时**不得覆盖**用户已设置的 `status` / `default_status` / `load_status`，仅更新结构性字段（name/version/module_path 等） | **M** |
| FR-PLG-09 | 插件首次出现时，默认 `status=True`、`default_status=True` | **M** |
| FR-PLG-10 | 每个插件须拥有独立的迁移记录，记录已执行的迁移版本 | **M** |
| FR-PLG-11 | 第三方插件目录 `plugins_ext/` 中的插件，放入后重启即可生效，无需修改主仓库代码 | **M** |
| FR-PLG-12 | 支持的 Manifest 字段须包含：key/name/version/author/description/usage/plugin_type/menu_type/is_show/parent/level/admin_level/default_status/limit_superuser/cost_gold/impression/cmds/aliases/configs/limits/tasks/events/requires_core/requires/requires_services/bot_permissions/ignore_prompt/ignore_statistics | **M** |
| FR-PLG-13 | `version` 须采用 SemVer 格式 | **M** |
| FR-PLG-14 | Manifest 字段名与语义须与上游 `PluginExtraData` 保持一致，变更须在附录记录 | **M** |

### 6.3 命令系统 `FR-CMD`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-CMD-01 | 系统须支持**双轨命令**：中文 Text 轨与英文 Slash 轨指向同一 handler | **M** |
| FR-CMD-02 | Slash 轨命令须注册到 Telegram `setMyCommands`，支持输入框自动补全 | **M** |
| FR-CMD-03 | Slash 命令格式须符合 TG 约束 `^[a-z0-9_]{1,32}$` | **M** |
| FR-CMD-04 | 当 Slash 命令总数超过 100 条时，须按 `PluginType` 优先级截断（NORMAL > ADMIN > SUPERUSER > HIDDEN），超出部分降级为 Text 轨，**功能不得丢失** | **M** |
| FR-CMD-05 | Slash 命令自动命名规则应为 `<plugin_key>_<action>`，保证跨插件唯一 | **M** |
| FR-CMD-06 | Slash 命令须按 `PluginType` 映射到对应的 `setMyCommands` scope（群/管理员/私聊） | **S** |
| FR-CMD-07 | 命令须支持参数声明（名称/类型/是否必填/默认值/说明），类型支持 int/str/bool/word/greedy | **M** |
| FR-CMD-08 | 命令须支持别名（aliases），别名与 Text 轨共用同一 handler | **M** |
| FR-CMD-09 | 中文 `pattern` 若与其他命令存在前缀包含关系，须在注册期报错并要求显式处理 | **M** |
| FR-CMD-10 | 超过 4096 字符的输出须自动分页或改为分段发送 | **M** |

### 6.4 权限与调用管道 `FR-AUTH`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-AUTH-01 | 全部调用判定须收敛到**单一有序 Guard 管道**，禁止分散的权限钩子 | **M** |
| FR-AUTH-02 | 管道顺序须为：ResolveContext → BuildCommand → MergeConfig → GuardBan → GuardSwitch → GuardLevel → GuardCost → GuardLimit → Dispatch | **M** |
| FR-AUTH-03 | Guard 执行顺序由**列表中位置**决定，不得引入分散在各处的 priority 数字 | **M** |
| FR-AUTH-04 | 单个 Guard 返回值仅为允许或拒绝（拒绝携带原因与可选提示文案） | **M** |
| FR-AUTH-05 | 替代实现的全部代码量须 ≤700 行 | **M** |
| FR-AUTH-06 | 禁止引入任何 fallback / patch / guard-of-guard 兼容层 | **M** |
| FR-AUTH-07 | 插件开关须支持全局与群两级，群级覆盖全局 | **M** |
| FR-AUTH-08 | `limit_superuser=False` 时，超级用户须绕过该插件的限制与开关 | **M** |
| FR-AUTH-09 | 金币/好感度扣费须在实现上与调用成功绑定，失败不得扣费 | **M** |
| FR-AUTH-10 | 须提供一次性调用快照 `CallContext`，包含本次调用全部输入，可完整打印用于调试 | **M** |
| FR-AUTH-11 | 权限 Level 判定须结合 TG 角色与群级 `GroupConsole.level` 覆盖 | **M** |

### 6.5 限制器 `FR-LIM`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-LIM-01 | 须支持 CD（冷却时间）限制，单位秒 | **M** |
| FR-LIM-02 | 须支持 COUNT（次数）限制，且**必须显式声明周期**（如 `1d`/`1h`），不得使用隐式窗口 | **M** |
| FR-LIM-03 | 须支持 BLOCK（永久阻断） | **M** |
| FR-LIM-04 | 限制对象须支持 USER / GROUP / ALL 三种 watch 维度 | **M** |
| FR-LIM-05 | 限制生效范围须支持 PRIVATE / GROUP / ALL 三种 check 维度 | **M** |
| FR-LIM-06 | 拒绝时须返回可配置的提示文案（`result` 字段） | **M** |

### 6.6 配置管理 `FR-CFG`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-CFG-01 | 配置须为三级：Manifest 默认值 → 全局配置 → 群级配置，后者覆盖前者 | **M** |
| FR-CFG-02 | 配置键须匹配 `^[A-Z][A-Z0-9_]{1,63}$`，插件内唯一 | **M** |
| FR-CFG-03 | 配置项须支持 `type` / `help` / `default` / `min_value` / `max_value` / `choices` 约束 | **M** |
| FR-CFG-04 | **禁止**使用不可序列化的 Callable 作为参数解析器 | **M** |
| FR-CFG-05 | 所有配置项须可导出为 JSON Schema | **M** |
| FR-CFG-06 | 须支持 `global` 与 `group` 两种作用域的配置项 | **M** |
| FR-CFG-07 | 配置值写入前须按 `type`/范围/枚举校验，非法值拒绝写入并返回明确错误 | **M** |
| FR-CFG-08 | 须支持运行时重载配置且不丢失用户已改的值 | **S** |

### 6.7 Telegram 平台适配 `FR-TG`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-TG-01 | 须支持长轮询与 Webhook 两种收发模式，**默认长轮询** | **M** |
| FR-TG-02 | 须实现 per-chat 令牌桶限流，群内约 20 条/分钟 | **M** |
| FR-TG-03 | 收到 `Retry-After` 时须自动退避并按其指示时间等待后重试 | **M** |
| FR-TG-04 | 所有主动发送（含广播）须经过同一限流器，禁止绕过 | **M** |
| FR-TG-05 | 群成员的 `get_chat_member` 查询结果须带 ≤60 秒缓存，避免高频打爆 API | **M** |
| FR-TG-06 | 群信息须通过「事件驱动入库 + `get_chat` 按需补全」维护，不得尝试枚举全量群 | **M** |
| FR-TG-07 | 群管理员列表须通过 `get_chat_administrators` 按需同步 | **M** |
| FR-TG-08 | 用户 `username` 可能为空，展示逻辑须回退到 `full_name` | **M** |
| FR-TG-09 | 须支持 `ChatJoinRequest` 事件，用于入群申请审批 | **S** |
| FR-TG-10 | 须支持 Inline Keyboard 与 Callback Query 交互 | **S** |
| FR-TG-11 | 回调数据 `callback_data` 不得超过 64 字节 | **M** |
| FR-TG-12 | 平台动作（禁言/解禁/踢出/封禁/解封/退群）须返回布尔结果表示是否成功，**禁止静默 no-op** | **M** |
| FR-TG-13 | Bot 缺少所需管理员权限时，相关命令须在该群自动降级关闭并警告 | **M** |
| FR-TG-14 | 私聊消息仅可发送给已与 Bot 交互过的用户 | **M** |
| FR-TG-15 | 撤回他人消息须在 Bot 具备权限且消息未超过 48 小时时才成功 | **M** |
| FR-TG-16 | 图片发送前须检查 ≤10 MB 限制，超限须压缩或降级 | **S** |

### 6.8 业务服务 `FR-SVC`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-SVC-01 | 须提供用户服务：唯一用户标识、等级、金币、好感度的读写 | **M** |
| FR-SVC-02 | 须提供金币服务，支持增减并记录流水原因 | **M** |
| FR-SVC-03 | 须提供好感度服务，支持增减并记录流水原因 | **M** |
| FR-SVC-04 | 须提供群服务，维护群 ID、标题、成员数、最后一次活跃时间 | **M** |
| FR-SVC-05 | 金币/好感度变动须具备原子性，禁止读取-计算-写回的非原子序列 | **M** |
| FR-SVC-06 | 须提供道具服务，支持持有、使用与过期处理 | **S** |
| FR-SVC-07 | 用户 ID 须使用 Telegram 原生 `user_id`，不做任何跨平台的二次编码 | **M** |
| FR-SVC-08 | 群 ID 须使用 Telegram 原生 `chat_id` | **M** |

### 6.9 内置插件需求矩阵 `FR-BIP`

> 需求来源为上游 `builtin_plugins/` 目录 20 个子目录 + 5 个平铺文件的平移取舍。

| ID | 上游来源 | 需求 | 优先级 |
|---|---|---|---|
| FR-BIP-01 | `help` | 帮助与菜单：按 `menu_type` 分类展示插件列表、单插件详情、权限过滤（仅显示当前用户可用项） | **M** |
| FR-BIP-02 | `sign_in` | 签到与好感度排行：每日签到、签到卡渲染、群内/全局排行榜 | **M** |
| FR-BIP-03 | `shop` | 商店：道具上架/下架、购买、库存管理、金币结算 | **M** |
| FR-BIP-04 | `admin` | 群管理：禁言/解禁、踢出、封禁/解封、设置/撤销管理员、管理员变更通知 | **M** |
| FR-BIP-05 | `info` | 信息查询：用户信息、群信息、Bot 状态 | **M** |
| FR-BIP-06 | `superuser` | 超级用户：全局/群插件开关、广播、退群、数据维护 | **M** |
| FR-BIP-07 | `statistics` | 调用统计：按插件/用户/群统计调用次数与趋势查看 | **S** |
| FR-BIP-08 | `chat_history` | 聊天记录存储与查询 | **S** |
| FR-BIP-09 | `withdraw` | 撤回：延时自动撤回、管理员手动撤回 | **S** |
| FR-BIP-10 | `check` | 健康检查：磁盘、数据库、Bot 连通性自检 | **S** |
| FR-BIP-11 | `record_request` | 入群申请记录与审批（对接 `ChatJoinRequest`） | **S** |
| FR-BIP-12 | `scheduler` / `scheduler_admin` | 被动技能与定时任务：群级开关、任务列表展示、手动调整 | **S** |
| FR-BIP-13 | `about` | 关于：版本、作者、许可信息 | **C** |
| FR-BIP-14 | `bot_profile` | Bot 资料与自我介绍 | **C** |
| FR-BIP-15 | `catchphrase` | 快捷回复 / 语录 | **C** |
| FR-BIP-16 | `mahiro_bank` | 银行：存款/取款/贷款/还款/利息 | **C** |
| FR-BIP-17 | `plugin_store` | 插件商店：浏览与安装第三方插件（改为 GitHub/本地源，移除阿里云依赖） | **C** |
| FR-BIP-18 | `hooks/*` | 上述 auth 系列**不作为插件**，其功能由 FR-AUTH 单一管道实现 | **M** |
| FR-BIP-19 | `init` | 群与用户的初始化不设独立插件，由内核 `ResolveContext` Guard 承担 | **M** |
| FR-BIP-20 | `platform/qq` | 删除，不移植 | — |
| FR-BIP-21 | `llm_manager` | 延后，仅在 Manifest 保留 `smart_tools` 槽位 | **W** |
| FR-BIP-22 | `restart` / `auto_update` | 本期不做 | **W** |

### 6.10 渲染 `FR-RND`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-RND-01 | 渲染须抽象为可插拔接口，插件侧统一调用，不感知具体实现 | **M** |
| FR-RND-02 | 须提供纯文本渲染器，输出 Markdown | **M** |
| FR-RND-03 | 须提供 Pillow 渲染器，输出轻量卡片图片，**作为默认引擎** | **M** |
| FR-RND-04 | 须提供 HTML 渲染器（Chromium），作为可选引擎 | **S** |
| FR-RND-05 | 渲染引擎不可用时须自动降级到下一档，不得报错中断业务 | **M** |
| FR-RND-06 | 默认安装不得包含 Chromium 二进制 | **M** |
| FR-RND-07 | 未安装指定引擎依赖时，须给出明确的安装指引而非堆栈错误 | **M** |

### 6.11 WebUI `FR-WEB`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-WEB-01 | 须提供可选的管理后台插件，**默认开启** | **S** |
| FR-WEB-02 | 默认监听 `127.0.0.1`，改为公网监听须显式配置 | **M** |
| FR-WEB-03 | 须提供账号登录与令牌机制，令牌具备过期时间 | **M** |
| FR-WEB-04 | 须支持插件开关、配置项查看与修改、群管理操作 | **S** |
| FR-WEB-05 | 管理后台配置表单须由 FR-CFG 的 JSON Schema 自动渲染 | **S** |
| FR-WEB-06 | 默认安装不得捆绑生产级 ASGI 服务器部署配置 | **M** |
| FR-WEB-07 | 关闭 WebUI 后不得残留相关依赖开销或后台任务 | **M** |

### 6.12 数据与持久化 `FR-DATA`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-DATA-01 | 默认数据库为 SQLite 单文件，启用 WAL 模式 | **M** |
| FR-DATA-02 | 须设置 `busy_timeout` 不小于 5000 毫秒 | **M** |
| FR-DATA-03 | 高频计数类写入（如调用次数）须走内存缓冲并批量落盘 | **S** |
| FR-DATA-04 | 禁止插件执行裸 SQL，全部数据访问经 DAO 接口 | **M** |
| FR-DATA-05 | 表结构变更须通过显式迁移脚本，禁止运行时自动 ALTER | **M** |
| FR-DATA-06 | 数据模型须继承上游 `plugin_info` 的 26 个字段名与语义 | **M** |
| FR-DATA-07 | 须保留 PostgreSQL 适配能力，但不作为默认依赖 | **C** |
| FR-DATA-08 | 缓存默认使用内存实现，Redis 作为可选后端 | **C** |
| FR-DATA-09 | 启动时须检测数据库文件损坏并给出明确诊断 | **S** |

### 6.13 运维与可观测 `FR-OPS`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-OPS-01 | 日志不得输出 Bot Token 或其片段 | **M** |
| FR-OPS-02 | 须提供分级日志，管道判定可通过 debug 级完整打印 | **M** |
| FR-OPS-03 | 须记录每次插件调用的耗时与结果 | **S** |
| FR-OPS-04 | 须提供 `/diagnose` 类的自检命令输出环境状态 | **S** |
| FR-OPS-05 | 须提供数据备份与恢复工具 | **S** |
| FR-OPS-06 | 须支持以环境变量覆盖全部关键配置 | **M** |

### 6.14 定时任务 `FR-TSK`

| ID | 需求 | 优先级 |
|---|---|---|
| FR-TSK-01 | 任务须支持 cron 与 interval 两种触发器 | **M** |
| FR-TSK-02 | 须支持群级任务开关 | **M** |
| FR-TSK-03 | 须设置 `misfire_grace_time`，防止重启后补跑雪崩 | **M** |
| FR-TSK-04 | 须限制单任务最大并发实例数 | **M** |
| FR-TSK-05 | 任务触发的群发消息须走统一限流器 | **M** |
| FR-TSK-06 | 须支持任务前置检查函数，不满足条件跳过执行 | **S** |
| FR-TSK-07 | 须支持运行前置检查的输入参数配置 | **C** |

---

## 7. 非功能性需求 `NFR`

| ID | 类别 | 需求 | 验收方式 |
|---|---|---|---|
| NFR-01 | 性能 | 冷启动至就绪 ≤ 3 秒（SQLite + ≤40 插件） | 计时脚本 |
| NFR-02 | 性能 | 命令响应 P95 ≤ 800 毫秒（不含外部网络请求） | 压力脚本采样 |
| NFR-03 | 性能 | 常驻内存 ≤ 150 MB（默认档，无浏览器） | 进程 RSS 采样 |
| NFR-04 | 性能 | 依赖安装体积 ≤ 150 MB（默认 extras） | `du -sh .venv` |
| NFR-05 | 性能 | 轻量档 `zxtg[lite]` 体积 ≤ 95 MB | 同上 |
| NFR-06 | 可靠 | Bot 进程连续运行 7 天无内存泄漏增长 >20% | 长跑监控 |
| NFR-07 | 可靠 | 网络中断恢复后 ≤ 60 秒内自动恢复接收消息 | 断网演练 |
| NFR-08 | 可靠 | 单插件异常不得影响其他插件 | 注入异常测试 |
| NFR-09 | 安全 | Token 不得出现在任何日志、错误信息、导出文件中 | 全局搜索 |
| NFR-10 | 安全 | WebUI 未显式配置时不得监听公网网卡 | 端口扫描 |
| NFR-11 | 安全 | WebUI 令牌须有过期时间，默认不超过 24 小时 | 配置项核查 |
| NFR-12 | 安全 | 插件仅可访问自身 data 目录，不得读写任意路径 | 越权测试 |
| NFR-13 | 安全 | 危险群管操作（全员禁言/踢出/退群）须二次确认 | 交互走查 |
| NFR-14 | 可维护 | 核心运行时代码总量 ≤ 6,000 行（不含插件与第三方） | 代码统计 |
| NFR-15 | 可维护 | 权限与限制逻辑 ≤ 700 行 | 代码统计 |
| NFR-16 | 可维护 | 不存在任何 fallback / patch 兼容层文件 | 目录评审 |
| NFR-17 | 可维护 | 单个源文件的函数数量不得超过 30 个 | 静态检查 |
| NFR-18 | 易用 | 完成部署所需配置项 ≤ 1 个（Token） | 部署走查 |
| NFR-19 | 兼容 | `PluginType` / `BlockType` / `PluginLimitType` / `LimitWatchType` 枚举值与上游完全一致 | 对比测试 |
| NFR-20 | 兼容 | `plugin_info` 表字段名与上游一致 | Schema 比对 |
| NFR-21 | 可移植 | 支持 Python 3.11 及以上 | CI 矩阵 |
| NFR-22 | 可测 | 核心管道须具备单元测试覆盖 ≥ 80% | 覆盖率报告 |

---

## 8. 数据实体需求

以下实体为必须持久化的数据，字段语义继承上游。

| 实体 | 关键字段 | 说明 |
|---|---|---|
| `plugin_info` | module, module_path, name, status, block_type, load_status, author, version, level, default_status, limit_superuser, menu_type, plugin_type, cost_gold, admin_level, ignore_prompt, is_delete, parent, is_show, ignore_statistics, impression | 插件主表，26 字段继承 |
| `plugin_limit` | plugin_key, type, status, check_type, watch_type, result, cd, max_count, period, target_id | 限制记录，`period` 为本次新增 |
| `group_console` | group_id, group_name, member_count, level, status, last_active | 群信息 |
| `user_console` | user_id, username, full_name, gold, impression, platform | 用户主表，`platform` 退化为常量 |
| `user_gold_log` | user_id, amount, reason, create_time | 金币流水 |
| `user_impression_log` | user_id, amount, reason, create_time | 好感度流水 |
| `group_plugin_switch` | group_id, plugin_key, status | 群级插件开关 |
| `task_record` | task_key, group_id, status, last_run | 被动任务群级开关 |
| `statistics` | plugin_key, user_id, group_id, count, create_time | 调用统计 |
| `join_request` / `fg_request` | request_id, user_id, group_id, type, handle_type, create_time | 入群/好友请求记录 |
| `migration_record` | plugin_key, version, applied_time | 迁移版本 |

---

## 9. 验收标准（可量化）

| # | 验收项 | 通过标准 |
|---|---|---|
| A1 | 最小启动 | 仅设置 Token，`python -m zxtg` 可正常收发消息 |
| A2 | 命令冲突 | 构造 key 冲突插件，必须启动失败并打印冲突双方 |
| A3 | 配置不复活 | 群内关闭某插件 → 重启 → 该插件在该群仍为关闭 |
| A4 | 100 命令降级 | 构造 120 条命令，第 101 条降级为文本触发但功能完整 |
| A5 | 限流保护 | 单群连发 50 条不出 429，自动退避且最终全部送达 |
| A6 | 权限失败可见 | Bot 无禁言权限时执行禁言，返回明确失败而非静默 |
| A7 | 渲染降级 | 卸载指定渲染引擎后，相关功能降级到下一档且不中断 |
| A8 | 第三方插件 | 按规范放入 `plugins_ext/` 后重启即可用，主仓库零改动 |
| A9 | 异常隔离 | 注入必然抛异常的插件，其他插件功能不受影响 |
| A10 | 体积达标 | 默认 extras 安装后 `.venv` ≤ 150 MB |
| A11 | 启动达标 | 40 插件下冷启动 ≤ 3 秒 |
| A12 | 内存达标 | 稳定运行 24 小时后 RSS ≤ 150 MB |
| A13 | 日志安全 | 全量日志中搜索不到 Token 片段 |
| A14 | WebUI 安全 | 未显式配置时外网无法访问管理端口 |
| A15 | 契约一致 | 枚举值与 `plugin_info` 字段名与上游对比无差异 |
| A16 | 代码度量 | 权限逻辑 ≤ 700 行；核心 ≤ 6,000 行 |

---

## 10. 里程碑与交付物

| 阶段 | 交付物 | 完成判据 | 人日 |
|---|---|---|---:|
| M0 奠基 | 项目骨架、UnifiedEvent、CallContext、管道骨架、SQLite 模型 | Bot 可响应心跳命令 | 3 |
| M1 内核 | 注册器、校验器、配置三级、限制器、任务调度、命令广播 | 插件可装载并可查 | 5 |
| M2 平台 | TG 适配器、编解码、限流器、`setMyCommands` 作用域 | **双轨命令跑通** | 4 |
| M3 服务 | 用户/群/金币/好感度服务 | 业务逻辑可用 | 4 |
| M4 内置插件 | 完成全部 Must 级插件（FR-BIP-01~06） | 验收 A1–A9 通过 | 10–14 |
| M5 可选层 | Pillow 渲染 + WebUI | 默认档可用，D2/D3 达成 | 3 |
| M6 收尾 | 依赖瘦身、冒烟、文档 | A10–A16 通过 | 3 |
| | | **合计** | **32–36** |

**关键检查点**：M2 结束时必须验证「中文命令可触发 + 斜杠命令可补全」，这是本方案风险最集中的地方。

---

## 11. 风险与依赖

| # | 风险 | 影响 | 应对 |
|---|---|---|---|
| R1 | Slash 命令 100 条上限 | 插件增多后补全被截断 | 命名空间命名 + 优先级截断 + 降级为文本 |
| R2 | 中文 pattern 前缀误命中 | 命令路由错乱 | 注册期前缀冲突检测，强制显式处理 |
| R3 | SQLite 写竞争 | 高并发签到丢数据 | WAL + busy_timeout + 内存缓冲批量落盘 |
| R4 | 广播触发 TG 限流 | Bot 被限速数分钟 | 强制所有发送走统一 per-chat 令牌桶 |
| R5 | D2/D3 默认开启导致体积膨胀 | 轻量化目标失效 | 默认降档 Pillow + 不解绑 `lite` extras（见 §3） |
| R6 | WebUI 默认开启带来暴露面 | 安全风险 | 强制 `127.0.0.1` 默认 + 令牌过期 |
| R7 | 路线 C 前期无可见产出 | 进度感知差 | M2 强制里程碑演示 |
| R8 | 与上游 diverge | 无法合并上游更新 | 已接受，仅同步数据契约，不同步代码 |
| R9 | 上游 `scipy` 等依赖真实用途未明 | 删除导致功能缺失 | 移植前逐个 grep 确认调用点 |

---

## 12. 需求追溯矩阵

| 需求组 | 对应设计章节 | 对应验收项 |
|---|---|---|
| FR-CORE | 设计 §2.1 / §2.3 / §5.11 | A1, A11, A12 |
| FR-PLG | 设计 §5.2 / §5.3 / §5.11 / §5.13 | A2, A3, A8 |
| FR-CMD | 设计 §5.4 / §5.5 | A4 |
| FR-AUTH | 设计 §5.6 | A9, A16 |
| FR-LIM | 设计 §5.8 | A9 |
| FR-CFG | 设计 §5.7 | A3 |
| FR-TG | 设计 §4.1 / §4.3 / §4.4 | A5, A6 |
| FR-SVC | 设计 §2.1 L3 | A1 |
| FR-BIP | 设计 §6 P4 | 各插件自身验收 |
| FR-RND | 设计 §3.3 | A7, A10 |
| FR-WEB | 设计 §3.3 | A14 |
| FR-DATA | 设计 §3.4 / §2.1 L0 | A15 |
| FR-TSK | 设计 §5.9 | A5 |
| NFR | 设计 §7 | A10–A16 |

---

## 附录 A：相对上游的契约变更登记

| 变更 | 类型 | 理由 |
|---|---|---|
| 新增 `requires_core` | 新增字段 | 第三方插件版本兼容的前提 |
| 新增 `requires` | 新增字段 | 取代隐式 import 顺序依赖 |
| 新增 `bot_permissions` | 新增字段 | TG 下 Bot 需具备对应管理员权限 |
| 新增 `period`（限制器） | 新增字段 | 上游 `PluginCountBlock` 缺周期语义 |
| `arg_parser: Callable` → `type + choices + 范围` | 修改 | Callable 不可序列化，阻碍 WebUI 与配置校验 |
| 删除 `sql_list` | 移除 | 插件裸 SQL 为注入面，改由 DAO 提供 |
| `PluginSetting` 扁平化 | 结构变更 | 降低注册器复杂度，字段语义不变 |
| `version` 改 SemVer | 修改 | 支持范围比较 |
| `platform` 字段退化为常量 | 简化 | TG 单平台无需分支 |

## 附录 B：本期明确不做的功能（源自 v2.0 分析）

| 功能 | 原因 |
|---|---|
| 合并转发的解析 | TG 无此概念（发送侧改为长图渲染） |
| 戳一戳 / Poke | TG 无此概念 |
| 好友请求 / 好友列表 | TG 无好友体系，语义替换为「已知用户」 |
| 枚举全部群 / 全部成员 | TG Bot API 无对应能力，改为事件驱动 + 按需查询 |
| QQ 协议的各项特有行为 | 平台已移除 |
