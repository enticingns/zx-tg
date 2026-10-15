# NEXT-TASK-M1FIX：契约对齐修正（M1 收尾）

> 窄范围修正任务。**只修下列问题**，不要做 M2，不要重构已通过的部分。

## 1. 问题（独立复核发现）

`plugin_info` 模型仍未与上游逐字对齐：
- 上游 `zhenxun/models/plugin_info.py` 实测 = **id + 21 个业务字段 + 1 个反向关联 `plugin_limit` = 23 项**。
- 本项目 `src/zxtg/models/plugin_info.py` 当前 = **24 项**，多出 **`description`**（`fields.TextField`）。
- 上游**没有** `description` 列（它属于上游 `PluginExtraData`/`PluginMetadata` 的**声明式元数据**，不入 `plugin_info` 表）。
- M1 已把 `usage` / `superuser_help` 移除，但**漏了 `description`**；且 `M1-REPORT.md` §2.1 把它当成上游字段计数（写成「id + 22 业务字段 + 1 反向关联 = 24」），**计数错误**。

## 2. 必须做的修正

1. **从 `PluginInfo` 模型移除 `description` 字段**，使其与上游逐字一致（23 项：id + 21 + 反向关联）。
2. **同步改 `registry.py` 的 `register_to_db`**：`existing.description = manifest.description` 与 `PluginInfo.create(description=...)` 都要去掉（否则会写不存在的列）。
3. `description` **保留在 `PluginManifest` 中**（它是 manifest 的声明式元数据，必须存在，只是不入库）。
4. **更新 `tests/test_models.py`** 的字段断言为 **23 项**（id + 21 + 反向关联），并确保 CRUD 测试不再传 `description`。
5. **修正 `M1-REPORT.md`**：
   - §2.1 的计数改正为：上游 = id + 21 业务字段 + 1 反向关联 = **23**；本项目修正后同为 **23**。
   - §2.2 契约变更登记补一行：`description` 已从模型移除（结构修正，理由同 usage/superuser_help）。
6. 全量复跑测试，确认仍然全绿（M0+M1 全部用例，之前是 64 passed）。

## 3. 自检清单（必须逐条真跑）

```bash
. .venv/bin/activate
python -m pytest -q          # 全绿
# 字段数核对（应为 23）
python - <<'PY'
import re
s=open('src/zxtg/models/plugin_info.py').read()
a=set(re.findall(r'^\s{4}([a-z_]+)\s*(?::[^\n=]*)?\s*=\s*fields\.',s,re.M))
b=set(re.findall(r'^\s{4}([a-z_]+)\s*:\s*fields\.',s,re.M))
print(len(a|b), sorted(a|b))
PY
```

## 4. 约束
- 不改 `docs/`、`NEXT-TASK-M1.md`、`NEXT-TASK-M1FIX.md`。
- 不引入新依赖；不放宽既有断言；不引入 fallback/patch 层。
- 不动 M0/M1 其它已通过内容。

## 5. 交付
把上面命令的**原始输出**追加到 `M1-REPORT.md` 末尾（§「M1FIX 复核输出」），并简述改了什么。写完即停。
