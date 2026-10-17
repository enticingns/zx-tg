# NEXT-TASK-M4FIX：M4 缺陷修正（库存持久化 + 报告诚实性）

> 当前唯一权威指令。基线：`42763da` + M4 工作区产出（131 tests passed）。
> **只做下面 2 项**，不得扩大范围、不得重构已通过模块。

---

## 1. 问题 1（必修，功能缺陷）：商店库存不持久化

### 实证
复核方脚本（先 `set_global` 写入库存 7，再清空内存模拟重启）：

```
同进程读到库存: 7
清内存后读到: None     ← 重启后库存凭空消失，回到 manifest 默认值
```

### 根因
`plugins/shop/plugin.py` 的 `_save_shop_items()` 调用 `config_service.set_global()`，而该方法只是 `self._global_configs[key] = value`——**纯内存字典**。`config_service` 没有任何持久化方法（已核实无 `save/load/persist/flush`）。

设计 §5.6 明确要求三级配置落地为 `全局配置 core_config.yaml / DB`，当前实现不满足 `FR-CFG-01` 的"全局配置"层级（重启即丢，等于没有全局层）。

### 要求
1. 让商店库存（`SHOP_ITEMS`）**真正落库**，重启后仍然保留。
   - **推荐**：新增 `src/zxtg/models/config.py` 里的 `CoreConfig(key, value_json, plugin_key, scope, updated_at)` 模型，并给 `config_service` 加**异步** `save_global()` / `load_global()`（或等价命名），用 JSON 序列化存值。
   - 若你判断有更简单的既有承载物（例如复用某张表），可以，但必须在报告里论证，且不得塞进语义不符的表。
2. `set_global` 是同步 API，不要为了持久化把它改成 async 而破坏既有调用方。**新增异步落库方法**，由插件在写完后显式调用；或在 `_save_shop_items` 中改为异步并传 `ctx`。
3. **启动时加载**：`init_db()` 之后要能把已存的全局配置读回 `config_service`，否则重启后仍是默认值。
4. **失败的写入必须报错**：落库失败不得静默返回成功（M3 的教训）。
5. 迁移/建表走既有 `generate_schemas` 或显式迁移机制，不得写裸 SQL。

### 必须的验证（原始输出抄进报告）
- `test_shop_stock_persists_across_restart`：写库存 → `close_db()` → 重新 `init_db()` → 读回库存，断言等于写入值。
- `test_shop_purchase_decrements_persisted_stock`：购买后库存 -1，重开库仍是减少后的值。
- **负向对照**：把落库调用注释掉 → 上述测试必须 FAILED → 改回 → PASSED。贴两段原始输出。

---

## 2. 问题 2（必修，诚实性）：报告漏报缺陷

`M4-REPORT.md` 末尾写：

```
3. 与设计的偏差：**无偏差**。
4. 未解决问题：**无**。
```

但库存不持久化是真实偏差，属于漏报。要求：
1. 修正该段，如实列出本条问题（或修正后的结论）。
2. 新增 `## 11. M4FIX 修正记录`，包含：问题描述与实证输出、根因、改法（贴关键 diff）、新增测试原始输出、全量 pytest 原始输出与最终 N 数。
3. 明确回答：本次修正后**是否还有已知未解决项**。有就列，没有写"无"，但不得为了"好看"写无。

---

## 3. 硬约束（不放松）

- 依赖仍仅 `tortoise-orm` / `aiosqlite` / `pydantic>=2` / `httpx` / `pytest` / `pytest-asyncio`。
- **不得引入 fallback / patch / 兼容层**；不得有"库没初始化就假装成功"的分支。
- 插件仍不得 import 平台层；不得裸写 SQL；边界 B1–B5 必须继续通过。
- 既有 131 项测试必须仍全绿，不得放宽任何断言。
- 权限+限制 ≤700 行；核心 ≤6000 行（当前 5457，注意别超）；单文件函数数 ≤30；生产代码禁 `print()`。
- 不接真实 Telegram。
- 不改 `docs/`、`README.md`、既有 `NEXT-TASK-*.md`。
- 不提交 `data/` / `.venv/` / `*.db` / `*.log` / `.env` / `*token*`。

---

## 4. 完成标准

1. 库存重启后不丢（用负向对照证明）。
2. 报告已修正漏报，并有 §11 修正记录含真实输出。
3. 全量 `pytest -q` 全绿且数字 > 131。
4. 报告写完即停，**不要开始 M5**。
