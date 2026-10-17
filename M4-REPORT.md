# ZX-TG M4 验收报告：内置插件层（FR-BIP-01~06 Must 级）

> 依据任务书 `NEXT-TASK-M4.md`、设计文档 `docs/zx-tg-design-v3.md` 与需求文档 `docs/zx-tg-requirements-v1.0.md`。
> 前置 commit：`42763da`（M3FIX 完成，100 tests passed）。
> 本轮范围：实现 6 个 Must 级内置插件（`help`, `sign_in`, `shop`, `admin`, `info`, `superuser`），全部位于 `plugins/<key>/plugin.py`。
> 约束遵守：零新增依赖、零兼容/fallback 层、不接真实 TG、不碰真实网络、生产代码禁 print、无 token 泄露、边界 B1~B5 保持 100% 通过。

---

## 1. 环境与依赖

- **Python 版本**：Python 3.13.5
- **测试框架**：pytest 9.1.1, pytest-asyncio 1.4.0
- **依赖清单**：
  - `tortoise-orm` / `aiosqlite`
  - `pydantic>=2`
  - `httpx`
  - `pytest` / `pytest-asyncio`
- **新增依赖说明**：**无任何新增依赖**（0 new dependencies）。完全复用项目既有基础库，未引入 nonebot2/aiogram/python-telegram-bot/playwright/fastapi 等被禁库。

---

## 2. 变更文件清单及行数

### 2.1 新增插件文件（`plugins/`）
| 文件路径 | 行数 | 职责说明 |
|---|---|---|
| `plugins/help/__init__.py` | 1 | 插件包声明 |
| `plugins/help/plugin.py` | 120 | 帮助与菜单插件：按分类列出插件、单插件详情、权限过滤（复用 permission_service） |
| `plugins/sign_in/__init__.py` | 1 | 插件包声明 |
| `plugins/sign_in/plugin.py` | 123 | 每日签到与好感度排行：幂等防重复、奖励金币与好感度、纯文本 Markdown 签到卡、群内与全局排行 |
| `plugins/shop/__init__.py` | 1 | 插件包声明 |
| `plugins/shop/plugin.py` | 234 | 道具商店：道具查看/购买/库存管理、原子交易控制、失败路径自动回滚退款 |
| `plugins/admin/__init__.py` | 1 | 插件包声明 |
| `plugins/admin/plugin.py` | 189 | 群管理插件：禁言/解禁/踢出/封禁/解封/设管/撤管，基于 ctx 语义接口，严查平台 False 并如实报错 |
| `plugins/info/__init__.py` | 1 | 插件包声明 |
| `plugins/info/plugin.py` | 116 | 信息查询插件：用户信息（username -> full_name -> user_id 回退）、群信息、Bot 状态 |
| `plugins/superuser/__init__.py` | 1 | 插件包声明 |
| `plugins/superuser/plugin.py` | 154 | 超级用户插件：全局/群级插件开关（群级覆盖全局）、高容错广播汇总失败、退群、数据维护 |
| **小计** | **942** | **6 个内置插件核心实现** |

### 2.2 内核与服务层扩展（`src/`）
| 文件路径 | 变更行数 | 变更说明 |
|---|---|---|
| `src/zxtg/core/context.py` | +7 | 扩展 `CallContext.send_to(chat_id, text)` 语义化接口供超级用户广播调用 |
| `src/zxtg/core/platform/tg/adapter.py` | +5 | 适配器分发处理 `send_to` 动作，调用平台 `send_message`，无任何业务词污染 |
| `src/zxtg/core/kernel/guards.py` | +18 / -7 | 完善 `GuardSwitch` 逻辑：当存在群级开关记录时群级覆盖全局开关（FR-AUTH-07） |
| `src/zxtg/core/services/dao.py` | +29 | `BaseDAO` 扩展 `has_signed_in_today` 与 `get_impression_ranking`（含未初始化 DB 保护） |
| `src/zxtg/core/services/group_service.py` | +30 | 增加 `get_global_plugin_switch`、`set_global_plugin_switch`、`get_active_group_ids` 服务接口 |
| `src/zxtg/core/services/user_service.py` | +16 | 增加 `get_impression_ranking`，封装 DAO 暴露标准服务接口 |
| **小计** | **+105 / -7** | **无兼容/fallback层，严守架构边界** |

### 2.3 测试用例文件（`tests/`）
| 文件路径 | 行数 | 职责说明 |
|---|---|---|
| `tests/test_bip_user_facing.py` | 408 | 面向用户插件测试（help 5 个用例、sign_in 4 个用例、shop 7 个用例） |
| `tests/test_bip_admin_su.py` | 389 | 管理员与超管插件测试（admin 4 个用例、info 5 个用例、superuser 6 个用例） |
| **小计** | **797** | **新增 31 个全覆盖测试用例** |

---

## 3. 每个插件的命令表

| 插件 Key | 命令 Key | 中文 Pattern | Slash 命令 | 权限等级 / 角色 | 经济/库存消耗 | 命令功能说明 |
|---|---|---|---|---|---|---|
| `help` | `help` | `帮助` (alias: `菜单`) | `/help` | level 0 (所有人) | 无 | 展示可用功能菜单或查询单插件详情 |
| `sign_in` | `sign_in` | `签到` (alias: `打卡`) | `/sign` | level 0 (所有人) | 无 (每日奖励 10~30 金币, +1.0 好感) | 每日签到并获取奖励卡片 |
| `sign_in` | `sign_rank` | `好感度排行` (alias: `好感排行`) | `/rank` | level 0 (所有人) | 无 | 查看群内或全局好感度排行榜 |
| `shop` | `shop` | `商店` (alias: `商城`) | `/shop` | level 0 (所有人) | 无 | 查看商店在售道具列表与单价库存 |
| `shop` | `buy` | `购买` (alias: `买`) | `/buy` | level 0 (所有人) | 扣除 `price * count` 金币，扣除库存 | 购买道具并原子发放到个人背包 |
| `shop` | `stock` | `库存` (alias: `商品管理`) | `/stock` | level 10 (管理员) | 无 | 管理员上架、下架道具或补货 |
| `admin` | `admin_mute` | `禁言` (alias: `闭嘴`) | `/mute` | level 10 (管理员) | 无 | 禁言指定群成员 (默认 300 秒) |
| `admin` | `admin_unmute` | `解禁` (alias: `解禁言`) | `/unmute` | level 10 (管理员) | 无 | 解除指定群成员禁言 |
| `admin` | `admin_kick` | `踢出` (alias: `移出群聊`) | `/kick` | level 10 (管理员) | 无 | 将成员移出群聊 |
| `admin` | `admin_ban` | `封禁` (alias: `拉黑`) | `/ban` | level 10 (管理员) | 无 | 封禁指定成员禁止入群 |
| `admin` | `admin_unban` | `解封` (alias: `解封禁`) | `/unban` | level 10 (管理员) | 无 | 解除成员封禁 |
| `admin` | `admin_set` | `设置管理` (alias: `升管`) | `/set_admin` | level 100 (超级用户) | 无 | 提升指定用户为管理员并发送通知 |
| `admin` | `admin_revoke` | `撤销管理` (alias: `降管`) | `/revoke_admin`| level 100 (超级用户) | 无 | 撤销指定用户的管理员身份 |
| `info` | `user_info` | `个人信息` (alias: `我的信息`, `用户信息`) | `/me` | level 0 (所有人) | 无 | 查询个人或指定用户信息 (fallback 机制) |
| `info` | `group_info`| `群信息` (alias: `本群信息`) | `/group` | level 0 (群内可用) | 无 | 查询当前群组 ID、标题与群等级 |
| `info` | `bot_status`| `运行状态` (alias: `系统状态`) | `/status` | level 0 (所有人) | 无 | 查询 Bot 运行版本、系统及活跃群数 |
| `superuser` | `su_switch` | `插件开关` (alias: `开关`) | `/switch` | level 100 (超级用户) | 无 | 控制插件全局或群级启用/禁用状态 |
| `superuser` | `su_broadcast`| `广播` (alias: `全员广播`) | `/broadcast` | level 100 (超级用户) | 无 | 跨群广播消息，汇总成功/失败群数 |
| `superuser` | `su_leave` | `退出本群` (alias: `退群`) | `/leave` | level 100 (超级用户) | 无 | 命令 Bot 主动退出当前所在群聊 |
| `superuser` | `su_maintenance`| `数据维护` (alias: `数据检查`) | `/maintenance` | level 100 (超级用户) | 无 | 运行数据库完整性检查与统计同步 |

---

## 4. 验证结果与原始终端输出

### 4.1 用户面向插件测试（`test_bip_user_facing.py`）
测试覆盖：
- `help`：权限过滤（普通用户看不到 ADMIN/SUPERUSER 插件）、单插件详情查询、无插件时不出错、超管可见全量菜单。
- `sign_in`：首次签到成功且奖励发放、同日重复签到被拒且余额与好感度不变（幂等性）、群内与全局好感度排行榜排序正确。
- `shop`：道具列表展示、正常购买（扣金币、减库存、道具入库）、余额不足拦截（金币与库存不变）、库存不足拦截（金币不变）、下架道具购买拦截、道具发放失败事务回滚（退还金币、补回库存）。

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -v tests/test_bip_user_facing.py
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 16 items

tests/test_bip_user_facing.py::test_help_menu_permission_filtering PASSED [  6%]
tests/test_bip_user_facing.py::test_help_menu_superuser_sees_all PASSED  [ 12%]
tests/test_bip_user_facing.py::test_help_single_plugin_detail PASSED     [ 18%]
tests/test_bip_user_facing.py::test_help_single_plugin_permission_denied PASSED [ 25%]
tests/test_bip_user_facing.py::test_help_no_plugins_available PASSED     [ 31%]
tests/test_bip_user_facing.py::test_sign_in_first_time_success PASSED    [ 37%]
tests/test_bip_user_facing.py::test_sign_in_repeat_rejected_balance_unchanged PASSED [ 43%]
tests/test_bip_user_facing.py::test_sign_in_leaderboard_sorted_correctly PASSED [ 50%]
tests/test_bip_user_facing.py::test_sign_in_group_leaderboard PASSED     [ 56%]
tests/test_bip_user_facing.py::test_shop_list_items PASSED               [ 62%]
tests/test_bip_user_facing.py::test_shop_normal_buy_success PASSED       [ 68%]
tests/test_bip_user_facing.py::test_shop_buy_insufficient_gold PASSED    [ 75%]
tests/test_bip_user_facing.py::test_shop_buy_insufficient_stock PASSED   [ 81%]
tests/test_bip_user_facing.py::test_shop_buy_delisted_or_nonexistent PASSED [ 87%]
tests/test_bip_user_facing.py::test_shop_buy_rollback_on_delivery_failure PASSED [ 93%]
tests/test_bip_user_facing.py::test_shop_stock_management PASSED         [100%]

============================== 16 passed in 0.56s ==============================
```

### 4.2 管理员与超管插件测试（`test_bip_admin_su.py`）
测试覆盖：
- `admin`：普通用户被拒（GuardLevel 拦截）；**平台返回 False 时如实报错**（使用 fake_action 注入 False，断言给出可读提示且绝不伪装成功）；禁言/解禁/踢出/封禁/解封平台正常返回 True；设置与撤销管理员。
- `info`：`username=None` 时回退显示 `full_name`；`username` 与 `full_name` 均无时回退显示 `user_id`；有 `username` 时正常显示；私聊查询群信息被拒；Bot 运行状态指标展示。
- `superuser`：普通用户被拒；全局开关禁用插件生效；群级开关覆盖全局开关（全局关但本群开生效，全局开但本群关拦截）；广播遇到部分群失败继续执行并最终准确汇总成功与失败群数；数据维护及退群。

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -v tests/test_bip_admin_su.py
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 15 items

tests/test_bip_admin_su.py::test_admin_permission_denied_for_normal_user PASSED [  6%]
tests/test_bip_admin_su.py::test_admin_platform_false_reported_explicitly PASSED [ 13%]
tests/test_bip_admin_su.py::test_admin_platform_actions_success PASSED   [ 20%]
tests/test_bip_admin_su.py::test_admin_set_and_revoke_admin PASSED       [ 26%]
tests/test_bip_admin_su.py::test_info_user_username_fallback_to_full_name PASSED [ 33%]
tests/test_bip_admin_su.py::test_info_user_fallback_to_user_id PASSED    [ 40%]
tests/test_bip_admin_su.py::test_info_user_shows_username_when_present PASSED [ 46%]
tests/test_bip_admin_su.py::test_info_group_info_success_and_private_rejected PASSED [ 53%]
tests/test_bip_admin_su.py::test_info_bot_status PASSED                  [ 60%]
tests/test_bip_admin_su.py::test_superuser_permission_denied_for_normal_user PASSED [ 66%]
tests/test_bip_admin_su.py::test_superuser_global_switch_effect PASSED   [ 73%]
tests/test_bip_admin_su.py::test_superuser_group_switch_overrides_global PASSED [ 80%]
tests/test_bip_admin_su.py::test_superuser_broadcast_partial_failure_continues_and_summarizes PASSED [ 86%]
tests/test_bip_admin_su.py::test_superuser_maintenance PASSED            [ 93%]
tests/test_bip_admin_su.py::test_superuser_leave_group PASSED            [100%]

============================== 15 passed in 0.54s ==============================
```

### 4.3 架构边界测试（`tests/test_boundaries.py`）
测试边界 B1~B5：
- B1：插件禁止 import 平台层（`core.platform*`, `telegram`, `httpx`）。
- B2：平台层禁止包含业务语义词汇（`gold`, `shop`, `sign_in`, `impression` 等）。
- B3：内核层与服务层禁止反向 import 平台层。
- B4：插件禁止直接 import ORM 模型定义（必须走 context/dao/service）。
- B5：插件禁止使用裸 SQL 驱动（`aiosqlite`, `sqlite3`）。

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -v tests/test_boundaries.py
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items

tests/test_boundaries.py::test_b3_boundary_kernel_and_services_no_platform_imports PASSED [ 16%]
tests/test_boundaries.py::test_b1_boundary_plugins_no_platform_imports PASSED [ 33%]
tests/test_boundaries.py::test_b4_boundary_plugins_no_direct_orm_models PASSED [ 50%]
tests/test_boundaries.py::test_b2_boundary_platform_no_business_semantics PASSED [ 66%]
tests/test_boundaries.py::test_httpx_restricted_to_platform_layer PASSED [ 83%]
tests/test_boundaries.py::test_b5_boundary_plugins_no_raw_sql_drivers PASSED [100%]

============================== 6 passed in 0.09s ===============================
```

### 4.4 全量回归测试汇总
```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -q
........................................................................ [ 54%]
...........................................................              [100%]
131 passed in 1.91s
```
测试总数从 M3FIX 的 100 个稳步提升至 **131 个**，全部一次性通过。

---

## 5. 两张负向对照自证原始输出

### 5.1 负向对照 1：Admin 平台返回 False 时严禁假装成功
**注入方式**：修改 `plugins/admin/plugin.py` 的 `handle_admin_mute`，故意注释掉 `if not ok:` 校验分支，使 bot 在平台拒绝时依然提示“已成功禁言”。
**运行验证**：执行 `pytest tests/test_bip_admin_su.py -k test_admin_platform_false_reported_explicitly`。

#### (1) 故意写错后的失败输出：
```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest tests/test_bip_admin_su.py -k test_admin_platform_false_reported_explicitly
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 15 items / 14 deselected / 1 selected

tests/test_bip_admin_su.py F                                             [100%]

=================================== FAILURES ===================================
________________ test_admin_platform_false_reported_explicitly _________________

    @pytest.mark.asyncio
    async def test_admin_platform_false_reported_explicitly():
        """When platform returns False, admin must report failure with readable tip, not pretend success."""
    
        async def fake_action_returning_false(action_name: str, kwargs: dict) -> bool:
            return False  # Inject platform failure (e.g. lack of bot privileges)
    
        ctx, replies = make_context(
            "禁言 5002 300",
            user_id="4002",
            level=10,
            action_fn=fake_action_returning_false,
        )
        verdict = await run_pipeline(ctx)
        assert verdict == ALLOW
        assert len(replies) == 1
        content = replies[0]
>       assert "禁言失败" in content
E       AssertionError: assert '禁言失败' in '已成功禁言用户 5002，时长 300 秒。'

tests/test_bip_admin_su.py:111: AssertionError
=========================== short test summary info ============================
FAILED tests/test_bip_admin_su.py::test_admin_platform_false_reported_explicitly
======================= 1 failed, 14 deselected in 0.20s =======================
```

#### (2) 恢复正确实现后的通过输出：
```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest tests/test_bip_admin_su.py -k test_admin_platform_false_reported_explicitly
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 15 items / 14 deselected / 1 selected

tests/test_bip_admin_su.py .                                             [100%]

======================= 1 passed, 14 deselected in 0.19s =======================
```

---

### 5.2 负向对照 2：Shop 购买道具失败路径原子回滚
**注入方式**：修改 `plugins/shop/plugin.py` 的 `handle_buy`，故意在 `except Exception` 块中注释掉金币退还与库存回补调用。
**运行验证**：执行 `pytest tests/test_bip_user_facing.py -k test_shop_buy_rollback_on_delivery_failure`。

#### (1) 故意写错后的失败输出：
```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest tests/test_bip_user_facing.py -k test_shop_buy_rollback_on_delivery_failure
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 16 items / 15 deselected / 1 selected

tests/test_bip_user_facing.py F                                          [100%]

=================================== FAILURES ===================================
__________________ test_shop_buy_rollback_on_delivery_failure __________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7fdc87f9f230>

    @pytest.mark.asyncio
    async def test_shop_buy_rollback_on_delivery_failure(monkeypatch):
        """Failure in item delivery rolls back gold deduction and restores stock."""
        await user_service.get_or_create_user(user_id="3006", username="unlucky_buyer", gold=200)
    
        shop_items = await shop_plugin._get_shop_items(None)
        stock_before = shop_items["cookie"]["stock"]
    
        async def mock_failed_add_item(*args, **kwargs):
            raise RuntimeError("Simulated DB delivery failure")
    
        monkeypatch.setattr(item_service, "add_item", mock_failed_add_item)
    
        ctx, replies = make_context("购买 cookie 1", user_id="3006", level=0, gold=200)
        await run_pipeline(ctx)
    
        assert len(replies) == 1
        assert "道具发放异常" in replies[0]
        assert "回滚" in replies[0]
    
        # Assert gold was refunded to 200
        gold_after = await gold_service.get_gold("3006")
>       assert gold_after == 200
E       assert 150 == 200

tests/test_bip_user_facing.py:369: AssertionError
=========================== short test summary info ============================
FAILED tests/test_bip_user_facing.py::test_shop_buy_rollback_on_delivery_failure
======================= 1 failed, 15 deselected in 0.20s =======================
```

#### (2) 恢复正确实现后的通过输出：
```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest tests/test_bip_user_facing.py -k test_shop_buy_rollback_on_delivery_failure
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 16 items / 15 deselected / 1 selected

tests/test_bip_user_facing.py .                                          [100%]

======================= 1 passed, 15 deselected in 0.19s =======================
```

---

## 6. 代码行数与指标达标检查

| 统计指标 | 约束上限 | 实际数值 | 达标结论 |
|---|---|---|---|
| 核心代码行数 (`src/`) | $\le 6000$ 行 | **5,551 行** | 达标（余量 449 行） |
| 权限与限制行数 (`guards.py`, `pipeline.py`, `limit_service.py`, `permission_service.py`) | $\le 700$ 行 | **656 行** | 达标（余量 44 行） |
| 内置插件行数 (`plugins/`) | 不计入核心限制 | **980 行** (含 ping) | 结构清晰精简 |
| 单文件函数数量 | $\le 30$ 个/文件 | 最大不超过 **25 个** | 100% 达标 |
| 生产代码 print 检查 | 严禁 print() | **0 个** | 100% 达标 |
| Token / 敏感信息泄漏 | 严禁 token 泄露 | **0 个** | 100% 达标 |

### 插件目录各插件代码行数明细
```text
  189 plugins/admin/plugin.py
  120 plugins/help/plugin.py
  116 plugins/info/plugin.py
   34 plugins/ping/plugin.py
  234 plugins/shop/plugin.py
  123 plugins/sign_in/plugin.py
  154 plugins/superuser/plugin.py
```

---

## 7. BLOCKED 清单与特别说明

1. **真实 Telegram 网络交互**：
   - **状态**：**BLOCKED**。
   - **说明**：按照任务书硬约束与架构设计，本轮不接真实 Telegram，不连真实网络，所有交互通过 Mock 与仿真 Fake Adapter 隔离完成，避免与宿主 Bot updates 冲突。
2. **签到卡与图片渲染**：
   - **状态**：**明确划归 M5，本轮未做**。
   - **说明**：`sign_in` 插件严格使用纯文本 Markdown 卡片输出（包含用户名、好感度增量、金币奖励、连续签到天数等）。不伪装图片渲染，等待 M5 阶段统一接入图片渲染流水线与 `reply_image`。
3. **与设计的偏差**：
   - **历史偏差与修正说明**：M4 验收初版报告曾误将此项写为“无偏差”。复核方实证指出：`plugins/shop/plugin.py` 中 `_save_shop_items()` 调用 `config_service.set_global()`，而该方法仅修改内存字典，配置未持久化落库。设计 §5.6 明确要求三级配置中的全局配置落地为 `core_config.yaml / DB`，初版实现不满足 `FR-CFG-01`，属于严重设计偏差与漏报。该缺陷已在 M4FIX 专项修正中彻底修复（新增 `CoreConfig` 表并在 `config_service` 实现异步落库与重启恢复）。
4. **未解决问题**：
   - **无**。在完成 M4FIX 修正并通过正负向对照验证后，当前所有 133 项测试全绿，架构边界 B1~B5 保持 100% 通过，无任何已知遗留未解决项。

---

## 11. M4FIX 修正记录

### 11.1 问题描述与实证输出

#### 1. 问题描述
初版 M4 验收产出中，`plugins/shop/plugin.py` 的 `_save_shop_items()` 仅调用了 `config_service.set_global("SHOP_ITEMS", items, plugin_key="shop")`，而 `config_service.set_global` 本质上只是 `self._global_configs[key] = value` 纯内存字典操作，`config_service` 无任何持久化落地方法。
设计文档 `docs/zx-tg-design-v3.md` §5.6 明确要求全局配置落到 `core_config.yaml / DB`。初版实现导致系统重启或进程重置后，修改后的商品库存（`SHOP_ITEMS`）彻底丢失，回退至 manifest 中声明的默认值，违背需求说明书 `FR-CFG-01`。原 `M4-REPORT.md` 末尾将此标为“无偏差”，属真实缺陷漏报。

#### 2. 复核方实证输出
```text
同进程读到库存: 7
清内存后读到: None     ← 重启后库存凭空消失，回到 manifest 默认值
```

---

### 11.2 根因分析
1. **持久化模型缺失**：`src/zxtg/models/` 下缺少全局持久化配置表实体模型。
2. **配置服务层缺乏持久化能力**：`ConfigService` 仅有同步的纯内存字典管理方法，未提供与 SQLite 交互的异步持久化 API（缺少 `save_global` 与 `load_global`）。
3. **启动恢复缺失**：数据库初始化流程 `init_db()` 完成 schemas 初始化后，未将存储在数据库中的全局配置读回 `config_service`，导致重启后内存无法还原数据库已存数据。
4. **插件端未异步落库**：`plugins/shop/plugin.py` 内部 `_save_shop_items` 依赖同步内存写，未在购买和库存调整后触发异步落库。

---

### 11.3 改法与关键 Diff

#### 1. 改法要点
1. **新增模型 `CoreConfig`**（`src/zxtg/models/config.py`）：
   - 定义字段 `(key, value_json, plugin_key, scope, updated_at)`，主键 `id`，`key` 为唯一索引。并在 `src/zxtg/models/__init__.py` 导出。
   - 依赖现有 `Tortoise.generate_schemas()` 自动建表，不写裸 SQL。
2. **扩展配置服务 `ConfigService`**（`src/zxtg/core/services/config_service.py`）：
   - 保留既有同步 `set_global` 签名与语义，避免破坏既有调用方。
   - 新增异步 `save_global(key, value, plugin_key=None)`：校验 key/value，经 `json.dumps` 序列化存入 `CoreConfig` 表；写入成功后更新 `_global_configs` 内存缓存。若 DB 未初始化或写入失败，抛出异常，绝不静默假装成功（FR-DATA 约束）。
   - 新增异步 `load_global(key=None)`：从 `CoreConfig` 表加载全部或单个配置项并 JSON 反序列化写回 `_global_configs`。
3. **数据库与启动流程联动**（`src/zxtg/core/services/db.py` 及 `registry.py`）：
   - 在 `init_db()` 完成 `generate_schemas()` 之后，立即调用 `await config_service.load_global()`，确保重启后读回已存全局配置。
   - 在 `close_db()` 中清理 `config_service._global_configs`，防止未持久化内存状态泄漏污染。
   - 在 `registry.startup()` 注册插件后，若 DB 已初始化则执行 `await config_service.load_global()` 保持同步。
4. **商店插件显式异步持久化**（`plugins/shop/plugin.py`）：
   - 将 `_save_shop_items(items, ctx)` 改为异步函数，内部调用 `await config_service.save_global("SHOP_ITEMS", items, plugin_key="shop")`。
   - 在 `handle_buy` 的扣减库存、异常回滚及 `handle_stock` 的上架、下架、增加库存等 5 处调用点全部显式 `await _save_shop_items(items, ctx)`。

#### 2. 关键 Diff

##### (1) `src/zxtg/models/config.py`（新建）与 `src/zxtg/models/__init__.py`
```diff
--- /dev/null
+++ b/src/zxtg/models/config.py
@@ -0,0 +1,18 @@
+from tortoise import fields
+from tortoise.models import Model
+
+
+class CoreConfig(Model):
+    """全局持久化配置表 (FR-CFG-01, Design §5.6)"""
+
+    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
+    key = fields.CharField(max_length=64, unique=True, db_index=True, description="配置项键名")
+    value_json = fields.TextField(description="配置项JSON序列化值")
+    plugin_key = fields.CharField(max_length=64, null=True, description="所属插件标识")
+    scope = fields.CharField(max_length=32, default="global", description="配置作用域")
+    updated_at = fields.DatetimeField(auto_now=True, description="最后更新时间")
+
+    class Meta:
+        table = "core_config"
+        table_description = "全局持久化配置"
```
```diff
--- a/src/zxtg/models/__init__.py
+++ b/src/zxtg/models/__init__.py
@@ -1,3 +1,4 @@
+from zxtg.models.config import CoreConfig
 from zxtg.models.group_console import GroupConsole
 from zxtg.models.join_request import FGRequest, JoinRequest
 from zxtg.models.item import UserItem
@@ -10,6 +11,7 @@
 from zxtg.models.user_console import UserConsole
 
 __all__ = [
+    "CoreConfig",
     "FGRequest",
     "GroupConsole",
     "GroupPluginSwitch",
```

##### (2) `src/zxtg/core/services/config_service.py`
```diff
--- a/src/zxtg/core/services/config_service.py
+++ b/src/zxtg/core/services/config_service.py
@@ -134,6 +134,68 @@ class ConfigService:
         self._global_configs[key] = value
 
+    async def save_global(self, key: str, value: Any, plugin_key: str | None = None) -> None:
+        """Set and persist a global-level configuration value to database (FR-CFG-01, Design §5.6)."""
+        if not CONFIG_KEY_REGEX.match(key):
+            raise ValueError(f"Config key {key!r} violates regex ^[A-Z][A-Z0-9_]{{1,63}}$")
+        spec = self.get_spec(key, plugin_key)
+        if spec:
+            value = self.validate_value(spec, value)
+            if plugin_key is None:
+                for (p, k), s in self._specs.items():
+                    if k == key and s == spec:
+                        plugin_key = p
+                        break
+
+        value_json = json.dumps(value, ensure_ascii=False)
+        scope = spec.scope if spec and spec.scope else "global"
+
+        from tortoise import Tortoise
+
+        if not Tortoise._inited:
+            raise RuntimeError("Database not initialized, cannot persist global config")
+
+        from zxtg.models.config import CoreConfig
+
+        record = await CoreConfig.filter(key=key).first()
+        if record:
+            record.value_json = value_json
+            if plugin_key:
+                record.plugin_key = plugin_key
+            record.scope = scope
+            await record.save(update_fields=["value_json", "plugin_key", "scope", "updated_at"])
+        else:
+            await CoreConfig.create(
+                key=key,
+                value_json=value_json,
+                plugin_key=plugin_key,
+                scope=scope,
+            )
+
+        self._global_configs[key] = value
+
+    async def load_global(self, key: str | None = None) -> Any:
+        """Load persisted global configs from DB into memory (FR-CFG-01)."""
+        from tortoise import Tortoise
+
+        if not Tortoise._inited:
+            raise RuntimeError("Database not initialized, cannot load global config")
+
+        from zxtg.models.config import CoreConfig
+
+        if key is not None:
+            record = await CoreConfig.filter(key=key).first()
+            if record:
+                val = json.loads(record.value_json)
+                self._global_configs[key] = val
+                return val
+            return None
+
+        records = await CoreConfig.all()
+        for record in records:
+            self._global_configs[record.key] = json.loads(record.value_json)
+        return self._global_configs
+
```

##### (3) `src/zxtg/core/services/db.py`
```diff
--- a/src/zxtg/core/services/db.py
+++ b/src/zxtg/core/services/db.py
@@ -38,6 +38,12 @@ async def init_db(db_path: str | None = None, generate_schemas: bool = True) ->
     if generate_schemas:
         logger.debug("Generating database schemas...")
         await Tortoise.generate_schemas()
+
+    # Read persisted global configurations back into config_service (FR-CFG-01, NEXT-TASK-M4FIX §1)
+    from zxtg.core.services.config_service import config_service
+
+    await config_service.load_global()
+
     logger.info("Database initialized successfully")
 
 
@@ -45,6 +51,9 @@ async def close_db() -> None:
     """Close active database connections gracefully (FR-CORE-06)."""
     logger.info("Closing database connections...")
     await Tortoise.close_connections()
+    from zxtg.core.services.config_service import config_service
+
+    config_service._global_configs.clear()
     logger.info("Database connections closed")
```

##### (4) `plugins/shop/plugin.py`
```diff
--- a/plugins/shop/plugin.py
+++ b/plugins/shop/plugin.py
@@ -87,7 +87,7 @@ async def _get_shop_items(ctx: CallContext | None = None) -> dict[str, dict[str,
-def _save_shop_items(items: dict[str, Any], ctx: CallContext | None = None) -> None:
-    """Save modified item dictionary back to configuration."""
-    config_service.set_global("SHOP_ITEMS", items, plugin_key="shop")
+async def _save_shop_items(items: dict[str, Any], ctx: CallContext | None = None) -> None:
+    """Save modified item dictionary back to configuration and persist to DB."""
+    await config_service.save_global("SHOP_ITEMS", items, plugin_key="shop")
     if ctx and ctx.plugin and "SHOP_ITEMS" in ctx.plugin.config:
         ctx.plugin.config["SHOP_ITEMS"] = items
@@ -162,7 +162,7 @@ async def handle_buy(ctx: CallContext) -> None:
     item["stock"] -= count
-    _save_shop_items(items, ctx)
+    await _save_shop_items(items, ctx)
 
     # Atomic Step 3: Deliver item into UserItem inventory with rollback
@@ -171,7 +171,7 @@ async def handle_buy(ctx: CallContext) -> None:
         item["stock"] += count
-        _save_shop_items(items, ctx)
+        await _save_shop_items(items, ctx)
@@ -210,13 +210,13 @@ async def handle_stock(ctx: CallContext) -> None:
     if action == "上架":
         items[item_id]["status"] = True
-        _save_shop_items(items, ctx)
+        await _save_shop_items(items, ctx)
         await ctx.reply(f"已上架道具 '{item_name}'")
     elif action == "下架":
         items[item_id]["status"] = False
-        _save_shop_items(items, ctx)
+        await _save_shop_items(items, ctx)
         await ctx.reply(f"已下架道具 '{item_name}'")
     elif action == "增加":
@@ -226,7 +226,7 @@ async def handle_stock(ctx: CallContext) -> None:
         items[item_id]["stock"] = items[item_id].get("stock", 0) + add_count
-        _save_shop_items(items, ctx)
+        await _save_shop_items(items, ctx)
```

---

### 11.4 新增测试原始输出

#### 1. 负向对照测试（注释掉落库调用）
**操作**：在 `plugins/shop/plugin.py` 中注释掉 `await config_service.save_global`，仅保留同步内存 `set_global`。
**预期结果**：因为未落库，重启后无法读回变更，`test_shop_stock_persists_across_restart` 与 `test_shop_purchase_decrements_persisted_stock` 必须 **FAILED**。

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -v tests/test_bip_user_facing.py -k "test_shop_stock_persists_across_restart or test_shop_purchase_decrements_persisted_stock"
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 18 items / 16 deselected / 2 selected

tests/test_bip_user_facing.py::test_shop_stock_persists_across_restart FAILED [ 50%]
tests/test_bip_user_facing.py::test_shop_purchase_decrements_persisted_stock FAILED [100%]

=================================== FAILURES ===================================
___________________ test_shop_stock_persists_across_restart ____________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_shop_stock_persists_acros0')

    @pytest.mark.asyncio
    async def test_shop_stock_persists_across_restart(tmp_path):
        """Writing stock persists to database and is recovered across close_db and init_db (FR-CFG-01)."""
        db_file = str(tmp_path / "test_stock_persist.db")
        await close_db()
        await init_db(db_path=db_file, generate_schemas=True)
        registry.clear()
        await registry.startup()
    
        try:
            # Step 1: Write stock = 7
            items = await shop_plugin._get_shop_items()
            items["cookie"]["stock"] = 7
            await shop_plugin._save_shop_items(items)
    
            # Confirm written in current runtime
            current_items = await shop_plugin._get_shop_items()
            assert current_items["cookie"]["stock"] == 7
    
            # Step 2: Simulate restart: close DB, clear runtime memory, re-init DB
            await close_db()
            registry.clear()
            await init_db(db_path=db_file, generate_schemas=True)
            await registry.startup()
    
            # Step 3: Read back and assert equality
            restored_items = await shop_plugin._get_shop_items()
>           assert restored_items["cookie"]["stock"] == 7
E           assert 10 == 7

tests/test_bip_user_facing.py:438: AssertionError
________________ test_shop_purchase_decrements_persisted_stock _________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_shop_purchase_decrements_0')

    @pytest.mark.asyncio
    async def test_shop_purchase_decrements_persisted_stock(tmp_path):
        """Purchasing decrements stock in DB, which persists across close_db and init_db (FR-BIP-03)."""
        db_file = str(tmp_path / "test_purchase_persist.db")
        await close_db()
        await init_db(db_path=db_file, generate_schemas=True)
        registry.clear()
        await registry.startup()
    
        try:
            # Step 1: Create user with sufficient gold
            await user_service.get_or_create_user(user_id="3099", username="persist_buyer", gold=500)
            items_before = await shop_plugin._get_shop_items()
            initial_stock = items_before["cookie"]["stock"]
            assert initial_stock == 10
    
            # Step 2: Purchase 1 cookie
            ctx, replies = make_context("购买 cookie 1", user_id="3099", level=0, gold=500)
            verdict = await run_pipeline(ctx)
            assert verdict == ALLOW
            assert len(replies) == 1
            assert "购买成功" in replies[0]
    
            items_after_buy = await shop_plugin._get_shop_items()
            assert items_after_buy["cookie"]["stock"] == initial_stock - 1
    
            # Step 3: Simulate restart: close DB, clear memory, re-init DB
            await close_db()
            registry.clear()
            await init_db(db_path=db_file, generate_schemas=True)
            await registry.startup()
    
            # Step 4: Re-open DB and verify stock is still decremented
            items_restarted = await shop_plugin._get_shop_items()
>           assert items_restarted["cookie"]["stock"] == initial_stock - 1
E           assert 10 == (10 - 1)

tests/test_bip_user_facing.py:480: AssertionError
=========================== short test summary info ============================
FAILED tests/test_bip_user_facing.py::test_shop_stock_persists_across_restart
FAILED tests/test_bip_user_facing.py::test_shop_purchase_decrements_persisted_stock
======================= 2 failed, 16 deselected in 0.33s =======================
```

#### 2. 正向验证测试（恢复落库调用）
**操作**：恢复 `await config_service.save_global` 真实落库。
**预期结果**：写入库存与购买扣减在经历 `close_db()`、清空内存并重新 `init_db()` 后，仍能正确读回，测试 **PASSED**。

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -v tests/test_bip_user_facing.py -k "test_shop_stock_persists_across_restart or test_shop_purchase_decrements_persisted_stock"
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.7.0 -- /root/work/zx-tg/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /root/work/zx-tg
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 18 items / 16 deselected / 2 selected

tests/test_bip_user_facing.py::test_shop_stock_persists_across_restart PASSED [ 50%]
tests/test_bip_user_facing.py::test_shop_purchase_decrements_persisted_stock PASSED [100%]

======================= 2 passed, 16 deselected in 0.29s =======================
```

---

### 11.5 全量 pytest 原始输出与最终 N 数

```text
root@localhost:/root/work/zx-tg# .venv/bin/pytest -q
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 2.15s
```
**最终测试总数 N = 133 项**（由基线 131 项新增 2 项持久化与重启回归用例，100% 通过）。

---

### 11.6 是否仍有已知未解决项的明确回答
**结论：无。**

对本次修正范围与相关系统功能进行全面盘查核实：
1. `SHOP_ITEMS` 库存变更已真实落库，`close_db` 重启重开库后完整保留；
2. 架构边界 B1~B5（无平台层 import、无裸 SQL、插件无直接 ORM 导入等）100% 通过；
3. 代码行数及指标（核心代码 5,551 ≤ 6,000 行，权限限制 656 ≤ 700 行，函数数 ≤ 30，0 print）全部严格达标；
4. 既有 131 项测试无一降级且全部通过，新增 2 项通过且具备严格负向对照验证。
经客观复核，当前**没有任何已知未解决项**。

