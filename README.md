# ZX-TG

绪山真寻 Telegram 版 — **内核重写 + 数据契约继承 + 功能平移**（设计路线 C）。

上游基线：`zhenxun-org/zhenxun_bot` @ main。本项目为**契约级 fork**：不同步上游代码，仅继承数据模型字段名 / 枚举值 / 配置键 / 命令语义。

## 文档（权威）

| 文件 | 内容 |
|---|---|
| `docs/zx-tg-design-v3.md` | 架构与插件体系设计（分层、插件契约、调用管道、命令双轨、生命周期） |
| `docs/zx-tg-requirements-v1.0.md` | 需求规格说明书 SRS（FR/NFR/验收标准/里程碑） |
| `NEXT-TASK-M*.md` | 各里程碑任务书（当前权威指令，逐轮下发） |
| `M*-REPORT.md` | 各里程碑完成报告（开发方产出，供独立复核） |

## 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | 奠基：骨架、UnifiedEvent、CallContext、管道骨架、SQLite 模型 | 进行中 |
| M1 | 内核：注册/校验/配置三级/限制器/任务/命令广播 | — |
| M2 | 平台：TG 适配器、编解码、限流器、setMyCommands 作用域 | — |
| M3 | 服务：用户/群/金币/好感度 | — |
| M4 | 内置插件（Must 级） | — |
| M5 | 可选层：Pillow 渲染 + WebUI | — |
| M6 | 收尾：依赖瘦身、冒烟、文档 | — |

## 开发与协作

开发由**零重力（Antigravity CLI，`agy`）**执行；编排、任务书、独立复核与 Git 同步由 Momo 负责。

```bash
# 运行某一里程碑（后台）
bash scripts/run-m0.sh
```
