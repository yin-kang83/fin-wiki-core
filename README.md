# Fin-Wiki

> A deterministic, evidence-traceable finance computation core.
> 中文定位：**知识/证据层与确定性财务计算层分离的最小参考实现。**

## 这是什么

Fin-Wiki 不是一个聊天机器人，也不是一个“LLM 算财务”的项目。

它解决的是四个问题：

1. 文档里的财务事实，如何变成**可追溯**的结构化事实；
2. 事实被修正、重述、税法换版时，如何**不覆盖历史**；
3. 计算如何只走**纯 Decimal 算子**，不让模型算数；
4. 准则/规则换版时，如何按**业务日、报表期、过渡条款**选择适用版本，而不是永远取最新版。

## 不是什麼

- 不包含真实年报、题库、客户资料；
- 不包含生产级 LLM/MCP 适配器；
- 不构成审计、税务或法律意见；
- 不是“自动化合规判定器”。

## 核心能力

| 模块 | 能力 |
|---|---|
| `models.py` | `SourceSpan` / `FactCandidate` / `FactRecord` / `DerivedRecord` |
| `store.py` | 追加式双时态事实账本、修正、哈希链 |
| `wiki.py` | 证据索引，候选事实必须能回指原文 |
| `compiler.py` | 确定性文档编译：结构化条目 → `SourceSpan` → `FactCandidate` |
| `adapter.py` | Wiki → 账本：全部候选校验通过才提交 |
| `operators.py` | 纯 Decimal 算子（一阶差分） |
| `dag.py` | 事实/算子 DAG、血缘、循环检测 |
| `watchdog.py` | 版本化规则 |
| `resolver.py` | 按业务日/报表期/过渡条款/提前适用选版本 |
| `case_study.py` | 披露版本 vs 适用版本比对（研究用，不判“违规”） |
| `annual_report.py` | 年报文本 → 采用年份/未采用 → 案例评估 |

## 快速开始

```bash
python -m pip install -e .
python -m pytest fin_wiki/tests -q
python examples/demo.py
```

要求 Python 3.11+、pydantic 2.x。

## 核心不变量

- 事实只追加，修正走 `supersedes`；
- 双时态：`valid_from/valid_to` + `recorded_at`；
- 来源必须可回指原文切片，hash 一致；
- 缺参/冲突 → 拒绝，不默认、不取最新版；
- 派生值必须记录输入 `fact_id`、算子、公式；
- LLM 只允许产出候选事实，不允许直接入账或计算。

## 架构

见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 设计说明

见 [docs/DESIGN.md](docs/DESIGN.md)：为什么这样分层、放弃了哪些方案、如何从失败模式反推不变量。

## 测试

```bash
python -m pytest fin_wiki/tests -q
```

测试使用合成数据，不依赖真实年报/内部数据。

## 开源范围

见 [docs/OPEN_SOURCE_SCOPE.md](docs/OPEN_SOURCE_SCOPE.md)。

本仓库只包含核心与合成测试；真实年报、题库、客户数据、生产适配器不在开源范围。

## 许可证

MIT，见 [LICENSE](LICENSE)。
