# M2 阶段总结报告：Telegram 平台层

> 本报告依据 `NEXT-TASK-M2.md` 要求编写，记录 M2 阶段（Telegram 平台层）的设计落地、验证结果、架构边界与 BLOCKED 清单。
> M2 阶段任务完成后即停，未提前进入 M3。

---

## 1. 环境与依赖

- **运行环境**：Linux x86_64, Python 3.13.5
- **新增依赖**：`httpx == 0.28.1`
  - **安装体积**：Wheel 包 73 KB，解压安装体积约 609.8 KB (624,423 字节)。
  - **引入必要性**：用于直接与 Telegram Bot API 进行异步 HTTP 交互。架构主张“薄客户端最可控”，避免引入庞大的第三方 bot 框架（如 aiogram / python-telegram-bot / nonebot2），确保内核与服务层零平台感知。
  - **依赖约束**：未引入任何禁止依赖（aiogram / python-telegram-bot / nonebot2 / playwright / fastapi / uvicorn）。

---

## 2. 变更文件清单及行数

| 文件路径 | 变更属性 | 行数 | 职责说明 |
|---|---|---|---|
| `pyproject.toml` | 修改 | 37 | 增加 `httpx` 依赖 |
| `src/zxtg/core/context.py` | 修改 | 173 | `CallContext` 支持 `action_fn` 动作委托（mute/kick 等） |
| `src/zxtg/core/kernel/commands.py` | 修改 | 303 | `broadcast_commands` scope 接线与截断后索引同步 |
| `tests/test_boundaries.py` | 修改 | 144 | 增加 `httpx` 仅限平台层扫描及 B2 平台层无业务词汇校验 |
| `src/zxtg/core/platform/tg/__init__.py` | 新增 | 41 | 平台层导出符号 |
| `src/zxtg/core/platform/tg/protocol.py` | 新增 | 145 | `TelegramClient` 协议定义、脱敏工具与异常类 |
| `src/zxtg/core/platform/tg/client.py` | 新增 | 253 | `HttpTelegramClient`（薄 Bot API 客户端，httpx 异步实现） |
| `src/zxtg/core/platform/tg/fake_client.py` | 新增 | 214 | `FakeTelegramClient`（测试打点与状态模拟客户端） |
| `src/zxtg/core/platform/tg/codec.py` | 新增 | 157 | Update → UnifiedEvent 编解码、6 类 kind、角色映射、username 回退 |
| `src/zxtg/core/platform/tg/rlmgr.py` | 新增 | 143 | per-chat 令牌桶限流器、429 Retry-After 退避、FakeClock 注入 |
| `src/zxtg/core/platform/tg/cache.py` | 新增 | 123 | `MemberCache`（60s TTL）与 `ChatCache`（事件驱动入库与补全） |
| `src/zxtg/core/platform/tg/adapter.py` | 新增 | 422 | `TgPlatformAdapter` 长轮询、断线退避、异常隔离、分页与降级 |
| `tests/test_tg_adapter.py` | 新增 | 277 | 适配器无旁路限流、>4096 分页、>10MB 图片降级、平台动作与停机测试 |
| `tests/test_tg_cache.py` | 新增 | 101 | 成员 60s 缓存命中、事件驱动群同步与管理员按需获取测试 |
| `tests/test_tg_codec.py` | 新增 | 153 | 编解码 6 类 kind、角色映射 100/10/0、username 回退测试 |
| `tests/test_tg_commands.py` | 新增 | 115 | setMyCommands scope 分组与 >100 截断项双轨测试 |
| `tests/test_tg_rate_limiter.py` | 新增 | 78 | 令牌桶节流、429 Retry-After 离线 A5 全送达测试 |
| **总计** | - | **2879** | - |

- **代码行数约束检查**：
  - 权限与限制逻辑（`guards.py` 268 行 + `pipeline.py` 66 行 + `limit_service.py` 213 行）：共 **547 行**（<= 700 行硬约束）。
  - `src/zxtg` 核心总代码量：共 **4,443 行**（<= 6,000 行硬约束）。
  - 单文件函数/方法数：全库文件最高为 23 个，均满足 **<= 30 个**。
  - 生产代码全局扫描 `print()`：**0 处**。

---

## 3. 核心结构与设计落点

1. **薄客户端与脱敏隔离（`client.py` / `protocol.py`）**：
   - 提取 `TelegramClient` 协议，提供 `HttpTelegramClient` 与 `FakeTelegramClient`。
   - 实现 `mask_token` 与 `sanitize_text`，Token 仅从配置读取，URL 与异常中的 Token 自动替换为 `***`，彻底阻断日志泄露（NFR-09）。
2. **适配器生命周期与健壮性（`adapter.py`）**：
   - 继承 `PlatformAdapter`，默认采用 `getUpdates` 长轮询（FR-TG-01）。
   - 网络断线以指数退避重连（1s → 2s → 4s ... 上限 60s，FR-CORE-04）。
   - 单条 update 在 handler/pipeline 中的异常被隔离记录，不导致轮询退出（FR-CORE-05）。
   - `stop()` 优雅取消后台轮询协程并安全释放 httpx 连接池（FR-CORE-06）。
3. **事件编解码（`codec.py`）**：
   - 完整映射 6 类 Telegram 更新到 `UnifiedEvent`：
     - `message`/`edited_message` → `kind="text"`
     - `callback_query` → `kind="callback"`
     - `new_chat_members` → `kind="join"`
     - `left_chat_member` → `kind="leave"`
     - `chat_member`/`my_chat_member` → `kind="member_update"`
     - `chat_join_request` → `kind="join_request"`
   - 角色严格归一化：`creator` → `OWNER` (100)、`administrator` → `ADMINISTRATOR` (10)、`member`/`restricted` → `MEMBER` (0)。
   - 用户名为空时自动以 `first_name` + `last_name` 填充 `full_name`，`Actor.display` 正确回退（FR-TG-08）。
   - 提炼 `message_id` 用于撤回与编辑；保留 `raw` 用于平台逃生舱。
4. **统一限流器与 Retry-After 退避（`rlmgr.py`）**：
   - 实现 per-chat 令牌桶：群聊 20 条/分钟（容量 20，速率 1/3 token/s），私聊 60 条/分钟。
   - 所有发送通过 `RateLimiter.execute` 调度，捕获 `TelegramRetryAfterError` 后自动记录冷却期并依 fake clock 重试，直至消息完全送达（FR-TG-03）。
   - 发送出口强制接流，无任何旁路直接调用（FR-TG-04）。
5. **成员与群缓存（`cache.py`）**：
   - `MemberCache`：`get_chat_member` 结果以 60s TTL 缓存，命中时不发网络请求（FR-TG-05）。
   - `ChatCache`：事件驱动将群信息入库 `GroupConsole`，群名称缺失时按需单次调 `get_chat` 补全，禁止全量枚举群列表（FR-TG-06）。
   - 群管理员信息按需同步并以 TTL 缓存（FR-TG-07）。
6. **平台动作语义与缺权告警（`adapter.py` / `context.py`）**：
   - `mute`, `unmute`, `kick`, `ban`, `unban`, `leave`, `recall` 一律返回 `bool`，禁止静默 no-op（FR-TG-12）。
   - 比对群内 Bot 实际管理员权限（如 `can_restrict_members`、`can_delete_messages`），缺权时动作返回 `False` 并打印降级 Warning（FR-TG-13）。
   - 撤回他人消息严格校验权限且限定时间不超过 48 小时（FR-TG-15）。
7. **命令广播与作用域接线（`commands.py`）**：
   - `broadcast_commands` 将已注册命令按 scope 分组推送至 `TelegramClient.set_my_commands`：
     - `all_group_chats`: `NORMAL` 命令
     - `all_chat_administrators`: `ADMIN` 命令
     - `all_private_chats`: `NORMAL` 命令
     - `chat_member` / `chat`: `SUPERUSER` 命令
   - 超过 100 条的截断项不参与 `set_my_commands` 注册，但通过文本轨仍可正常匹配触发（FR-CMD-04）。
8. **分页与媒体降级**：
   - 文本超过 4096 字符自动调用 `split_message_text` 拆分为分段依次发送（FR-CMD-10）。
   - 图片二进制体超过 10MB 时触发 Warning 并降级为 `send_document` 发送（FR-TG-16）。

---

## 4. §3 验证原始输出

### 4.1 全量测试套件（84 项测试全绿，原 64 项 + 新增 20 项）

```text
$ . .venv/bin/activate && python -m pytest -q
........................................................................ [ 85%]
............                                                             [100%]
84 passed in 0.74s
```

### 4.2 架构边界检查（5 项全绿）

```text
$ . .venv/bin/activate && python -m pytest -q tests/test_boundaries.py
.....                                                                    [100%]
5 passed in 0.06s
```

### 4.3 平台层逐项验证详细输出

```text
$ . .venv/bin/activate && python -m pytest -v tests/test_tg_*.py
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 18 items                                                             

tests/test_tg_adapter.py::test_all_sends_go_through_rate_limiter_without_bypass PASSED [  5%]
tests/test_tg_adapter.py::test_message_paging_over_4096 PASSED           [ 11%]
tests/test_tg_adapter.py::test_image_over_10mb_degradation PASSED        [ 16%]
tests/test_tg_adapter.py::test_platform_actions_return_bool_and_degrade_on_lack_of_perm PASSED [ 22%]
tests/test_tg_adapter.py::test_recall_48h_limit_and_permissions PASSED   [ 27%]
tests/test_tg_adapter.py::test_polling_reconnect_backoff_and_graceful_shutdown PASSED [ 33%]
tests/test_tg_adapter.py::test_single_handler_exception_does_not_crash_poller PASSED [ 38%]
tests/test_tg_cache.py::test_get_chat_member_60s_cache_hit PASSED        [ 44%]
tests/test_tg_cache.py::test_chat_cache_event_driven_sync_and_get_chat_complement PASSED [ 50%]
tests/test_tg_cache.py::test_chat_administrators_sync_on_demand_with_caching PASSED [ 55%]
tests/test_tg_codec.py::test_codec_6_kinds_of_updates PASSED             [ 61%]
tests/test_tg_codec.py::test_role_mapping PASSED                         [ 66%]
tests/test_tg_codec.py::test_actor_username_fallback PASSED              [ 72%]
tests/test_tg_commands.py::test_set_my_commands_scope_grouping_parameters PASSED [ 77%]
tests/test_tg_commands.py::test_100_command_truncation_not_in_scope_and_text_track_still_works PASSED [ 83%]
tests/test_tg_rate_limiter.py::test_token_bucket_burst_and_throttle PASSED [ 88%]
tests/test_tg_rate_limiter.py::test_retry_after_backoff_and_eventual_delivery PASSED [ 94%]
tests/test_tg_rate_limiter.py::test_offline_a5_batch_delivery_under_burst_and_retry_after PASSED [100%]

============================== 18 passed in 0.34s ==============================
```

---

## 5. 架构边界（B1 / B2 / B3 / B4）实现与结果

| 边界 | 规则要求 | 实现与自动检查方式 | 检查结果 |
|---|---|---|---|
| **B1** | `plugins/` 不得引用平台层符号 | AST 静态扫描 `plugins/`，禁止 import `core.platform`、`httpx` 及平台底层库 | **PASSED** |
| **B2** | 平台层不得出现业务语义词汇 | 静态扫描 `src/zxtg/core/platform/tg/`，禁止出现“签到/金币/checkin/sign_in/coin/gold/impression/好感度” | **PASSED** |
| **B3** | 内核/服务层不得感知 Telegram 平台 | AST 静态扫描 `core/kernel` 与 `core/services`，禁止 import `core.platform`、`httpx`、`telegram` 等 | **PASSED** |
| **B4** | 插件不得直接操作 ORM 模型 | AST 静态扫描 `plugins/`，禁止 direct import `zxtg.models` 或 `tortoise.models` | **PASSED** |
| **HTTPX** | `httpx` 仅允许在 platform 层使用 | AST 静态扫描全仓库非平台层，禁止在平台层外 import `httpx` | **PASSED** |

---

## 6. BLOCKED 清单

依据任务书要求，本轮**禁止接触真实 Telegram 网络**，避免与宿主 gateway bot（`@esmodtnq_bot`）发生更新争夺事故。以下涉及真实网络的场景如实标记为 BLOCKED：

| 项目 | 状态 | 阻塞原因 | 解锁条件 |
|---|---|---|---|
| 真实 Telegram 长轮询收发更新 | **BLOCKED** | 需专用测试 Bot Token，避免与宿主 gateway bot 争夺 updates 产生事故 | 用户提供独立测试 Bot Token 并在隔离环境部署 |
| 真实 Bot API `setMyCommands` 注册验证 | **BLOCKED** | 需真实 API Token 打点验证 Telegram 服务端实际回显 | 待用户提供测试 Bot Token |
| 真实 Telegram 429 Retry-After 触发与退避 | **BLOCKED** | 真实网络触发 429 需向 live API 狂发请求，存在账号封禁风险 | 仅离线通过 FakeTelegramClient 与 FakeClock 验证 |
| 真实 Telegram 群权限探测（实测比对） | **BLOCKED** | 需向真实 Telegram 群添加 Bot 并实测管理员权限回显 | 待真实联调环境具备 |

---

## 7. 与设计的偏差与实现决策

1. **单文件函数数约束拆分（`protocol.py` / `fake_client.py`）**：
   - Telegram Bot API 接口方法较多（>15 个）。若将协议抽象、异常定义、Fake 实现及 Http 实现写在单一文件，函数/方法数将超过 30。
   - 实现决策：将 `TelegramClient` 协议及异常剥离至 `protocol.py`，Fake 实现剥离至 `fake_client.py`，`client.py` 仅保留 `HttpTelegramClient` 并做统一对外 re-export。各文件函数数均严格控制在 <=20。
2. **`CallContext` 动作解耦注入（`action_fn`）**：
   - L4 插件通过 `ctx.mute(...)` / `ctx.kick(...)` 调用平台动作，为遵守 B1 边界（插件不 import 平台层），在 `CallContext` 中增加 `action_fn` 回调注入，由平台适配器在分发事件时绑定 `adapter.dispatch_action`，实现无感知委托。
3. **截断后命令索引同步**：
   - 在 `CommandRegistry.recalculate_truncation` 执行后，重新构建 `_by_key`、`_by_slash`、`_by_pattern` 索引映射，确保降级至文本轨的命令在运行时匹配时能正确携带 `registered_to_telegram=False` 标识。

---

## 8. 未解决问题

- 无。M2 所需功能（薄客户端、长轮询适配器、编解码、限流器、60s 缓存、命令作用域广播、4096 分页、10MB 降级）均已完备实现并通过全量断言验证。
