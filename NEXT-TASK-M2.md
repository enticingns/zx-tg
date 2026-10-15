# NEXT-TASK-M2：Telegram 平台层（适配器 / 编解码 / 限流 / setMyCommands 作用域）

> 当前唯一权威指令。细节见 `docs/zx-tg-design-v3.md` §2.1 L1 / §4.1 / §4.3 / §4.4 / §5.5 与 `docs/zx-tg-requirements-v1.0.md` FR-TG-01~16、FR-CMD-02/06。
> M0/M1 已完成并入库（最新 commit `369e947`）。本轮只做 M2。

---

## 0. 重要限制：**不要用真实 Telegram 网络**

- **禁止**在代码或测试里使用任何真实 bot token 发请求。
- **禁止**使用宿主 gateway 正在用的 bot（`@esmodtnq_bot`）——两个 poller 抢同一个 token 会互相吞更新，属于事故。
- 本轮所有验证一律走**假传输层（fake transport）**注入：Adapter 必须把「HTTP 调用 TG API」抽到一个可替换的 client 接口后面。
- **真实 TG 端到端（长轮询收消息 / `setMyCommands` 真的注册成功）一律标 BLOCKED**，原因写「需专用测试 bot token，避免与宿主 gateway bot 冲突，待用户提供」。

---

## 1. 本轮交付物

### 1.1 TG Bot API 客户端（薄）
`src/zxtg/core/platform/tg/client.py`
- 用 **`httpx`（async）** 直接打 Bot API，**不要**引入 aiogram / python-telegram-bot / nonebot2（架构主张：内核不感知平台、插件不碰平台层；薄客户端最可控）。
- 抽象 `TelegramClient` 协议 + `HttpTelegramClient` 实现 + `FakeTelegramClient`（测试用）。
- 方法至少覆盖：`get_updates`、`send_message`、`edit_message_text`、`delete_message`、`answer_callback_query`、`set_my_commands`、`get_chat`、`get_chat_member`、`get_chat_administrators`、`restrict_chat_member`、`ban_chat_member`、`unban_chat_member`、`leave_chat`。
- **Token 只从配置读，绝不落日志/异常/URL 打印**（NFR-09）。错误信息里如含 token 必须脱敏。

### 1.2 适配器
`src/zxtg/core/platform/tg/adapter.py`
- 实现 M0 的 `PlatformAdapter` 抽象。**默认长轮询**（FR-TG-01），webhook 仅留接口。
- 断线自动退避重连，退避上限 60 秒（FR-CORE-04）。
- 单条 handler 异常不得让进程退出（FR-CORE-05）；优雅停机（FR-CORE-06）。

### 1.3 编解码 `codec.py`（设计 §2.3 / §4.1 / §4.2）
`update → UnifiedEvent`：
- `message` / `edited_message` → kind=text；`callback_query` → kind=callback；`new_chat_members` → join；`left_chat_member` → leave；`chat_member` → member_update；`chat_join_request` → join_request。
- 角色映射（§4.2 逐字）：`creator→OWNER(100)`、`administrator→ADMINISTRATOR(10)`、`member/restricted→MEMBER(0)`。
- `Actor.username` 为 None 时必须能回退 `full_name`（FR-TG-08）。
- 群类型 private/group/supergroup 映射；`message_id` 必须带出（撤回用，设计 §2.3）。
- **平台层不得出现业务语义词汇**（签到/金币等）——边界 B2。

### 1.4 限流器 `rlmgr.py`（FR-TG-02/03/04 / §4.1）
- **per-chat 令牌桶**，群内约 **20 条/分钟**；私聊可放宽。
- 收到 `Retry-After`（429）必须按其指示退避并重试（FR-TG-03）。
- **所有主动发送（含广播）必须走同一限流器**，无旁路（FR-TG-04）——在发送出口强制，而不是靠调用方自觉。
- 提供可测试的时钟注入（不要 `sleep` 真等，用 fake clock）。

### 1.5 成员/群缓存（FR-TG-05/06/07）
- `get_chat_member` 结果 **≤60 秒缓存**。
- 群信息：事件驱动入库 + `get_chat` 按需补全（不得枚举全量群）。
- `get_chat_administrators` 按需同步。

### 1.6 平台动作语义（FR-TG-12/13/15）
- `mute/unmute/kick/ban/unban/leave` 返回 **bool**，**禁止静默 no-op**；失败要有可读结果。
- bot 缺权时相关命令在该群**自动降级关闭 + 告警**（FR-TG-13）；`bot_permissions` 与实测群权限比对。
- 撤回他人消息需 bot 有权限且 ≤48h（FR-TG-15）。

### 1.7 命令广播 `core/kernel/commands.py` 接线（§5.5 / FR-CMD-02/04/06）
- 把 M1 算好的 scope 分组**真正喂给** `TelegramClient.set_my_commands`（**用 fake client 断言调用参数**）。
- scope 映射：`all_private_chats` / `all_group_chats` / `chat_administrators` / `chat_member`。
- 100 条截断顺序 NORMAL > ADMIN > SUPERUSER > HIDDEN，超出降级 Text 轨且功能不丢（M1 已有，接上广播）。
- `cmd` 格式必须匹配 `^[a-z0-9_]{1,32}$`。

### 1.8 消息长度与图片（FR-CMD-10 / FR-TG-16）
- 输出 >4096 字符自动分页/分段。
- 图片发送前检查 ≤10MB，超限压缩或降级。

---

## 2. 硬性约束
1. Python ≥ 3.11；依赖仅 `tortoise-orm, aiosqlite, pydantic>=2, pytest, pytest-asyncio` + **新增 `httpx`**（异步 HTTP，打 Bot API 用；必须在报告里说明并确认体积）。**不得**引入 aiogram / python-telegram-bot / nonebot2 / playwright / fastapi / uvicorn。
2. 边界必须继续为真：**B3**——`core/kernel` 与 `core/services` 不得 import `core.platform` 或任何平台库；**B2**——`core/platform/tg/` 不得出现业务语义词汇；**B1**——`plugins/` 不得 import `core.platform`。现有 `tests/test_boundaries.py` 必须继续通过，并把 TG 相关新的违规面（如 `httpx` 只允许出现在 platform 层）纳入。
3. 不引入任何 fallback / patch / guard-of-guard 层。
4. 权限与限制逻辑仍 ≤700 行（不要因为 M2 破坏它）；核心 ≤6000 行。
5. 生产代码禁 `print()`；日志不得含 token 或其片段；单文件函数数 ≤30。
6. 不改 `docs/`、`NEXT-TASK-M0.md`、`NEXT-TASK-M1.md`、`NEXT-TASK-M1FIX.md`、`NEXT-TASK-M2.md`；不得回退 M0/M1 已通过内容或放宽断言。
7. 不提交 `data/`、`.venv/`、`*.db`、`*.log`。

---

## 3. 真跑真验证（原始输出抄进报告）

```bash
. .venv/bin/activate
python -m pytest -q                       # 全绿（此前 64，现应增加）
python -m pytest -q tests/test_boundaries.py
```

**必须新增并验证**（全部用 fake client / fake clock，不碰真实网络）：
- codec：6 类 kind 的 update → UnifiedEvent 映射正确；角色 100/10/0 映射正确；`username=None` 回退 `full_name`
- 限流：per-chat 令牌桶——连发 N 条会被节流；注入 `Retry-After` 后按 fake clock 退避并**最终全部送达**（验收 A5 的离线版）
- **所有发送都经限流器**：断言不存在绕过路径（例如直接在 client 上打点计数）
- `setMyCommands`：断言按 scope 分组的调用参数正确；>100 条时被截断项**不进** scope 且仍可走 Text 轨
- `get_chat_member` 60s 缓存命中（第二次不重复调用 client）
- 平台动作返回 bool；无权限时返回 False 并触发该群降级告警（不静默）
- 消息 >4096 分页；图片 >10MB 降级/压缩路径

---

## 4. 如实标 BLOCKED
- **真实 Telegram**：长轮询真实收消息、真实 `setMyCommands` 注册、真实 429 退避、真实群权限探测 → 全部 BLOCKED（需专用测试 token）。
- 不许假装测过。不许用宿主 gateway 的 bot。

---

## 5. 交付格式
写 **`M2-REPORT.md`**：环境（含 httpx 版本与体积）、变更文件清单（含行数）、核心结构落点、§3 每条验证的**原始输出**、边界 B1/B2/B3 的实现与结果、BLOCKED 清单、与设计的偏差/实现决策、未解决问题。报告写完即停，**不要开始 M3**。
