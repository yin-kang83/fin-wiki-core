# Fin-Wiki 框架设计说明

## ——从“LLM 读文档”到“证据—账本—算子—规则”的确定性框架

> 本文说明 Fin-Wiki 为什么这样分层、每个模块解决什么失败模式、哪些方案被放弃，以及后续如何扩展。
> 目标读者：准备参与开源、审计代码、或把这套框架接入自己业务系统的人。

## 一、设计起点：原方案解决什么问题，又漏了什么

最初的设想是四层：

```text
语义编译层 → 契约感知层 → 快照执行层 → 语义风控层
```

方向是对的：

- 用 Wiki/证据层解决“LLM 读长文档会漏”；
- 用确定性计算解决“LLM 算数会错”；
- 用版本/引用解决“结论没有依据”。

但把原始骨架落到代码时，发现了几个结构性问题：

| 原骨架问题 | 后果 |
|---|---|
| 一个 key 只存一个值，重复提交直接拒绝 | 无法处理修正、重述、税法换版 |
| 只有 `valid_from/valid_to` | 无法回答“当时系统知道什么” |
| 来源只是字符串 | 审计时无法回指原文 |
| 派生值没有输入血缘 | 算错了不知道用了哪条事实 |
| DAG 只是写死的一个节点 | 无法表达依赖关系 |
| 规则靠 LLM 判断 | 会把“解释”当成“依据” |
| 没有“来源不合法/冲突”的拒绝路径 | 错数据可能被静默接受 |
| LLM 可以产出事实并直接入账 | 幻觉进入账本 |

因此，Fin-Wiki 的设计不是“把四层画出来”，而是**从失败模式反推不变量，再由不变量决定模块边界**。

## 二、设计目标与约束

### 2.1 四个目标

1. **可追溯**：每个数字都能回到原文片段；
2. **可修正**：事实变更不覆盖历史，能回答“当时/现在分别是什么”；
3. **可复算**：计算只走纯 Decimal 算子，输入相同结果相同；
4. **可拒绝**：缺参、冲突、来源不合法时，系统拒绝输出，而不是猜。

### 2.2 五条硬约束

```text
① LLM 只读、只抽参，不写账、不算数
② 事实只追加，修正走 supersedes
③ 双时态：业务时间 + 记录时间
④ 派生值必须有输入 fact_id、算子、公式
⑤ 规则有版本，按业务时点/过渡条款选版本
```

## 三、设计方法：失败模式 → 不变量 → 模块

| 失败模式 | 不变量 | 落到的模块 |
|---|---|---|
| LLM 编造事实 | 候选事实必须过 schema + 来源校验 | `models.py` / `adapter.py` |
| 合同改了，旧数被覆盖 | 账本只追加；修正用 `supersedes` | `store.py` |
| 税法换版后算错旧账 | 查询按 `valid_from/to` + `recorded_at` | `store.py` |
| 引用是假的 | `SourceSpan` 回指原文 + hash | `models.py` / `wiki.py` |
| 缺一个参数还继续算 | 缺参/冲突 → 拒绝 | `adapter.py` / `store.py` |
| 派生数说不清来源 | `DerivedRecord` 记录输入 | `dag.py` |
| 永远取最新准则 | 按业务日/报表期/过渡条款选版本 | `resolver.py` |
| 把“披露不足”判成“违规” | 只输出“疑似/需核”，人工复核 | `case_study.py` |

这条链是本文最重要的设计方法：

> **不要先画模块，先列失败模式；每个失败模式必须对应一个可测试的不变量。**

## 四、分层架构

```text
┌─────────────────────────────────────────────┐
│ 分析层   case_study.py / annual_report.py    │
│ 披露版本 vs 适用版本；只做初筛               │
├─────────────────────────────────────────────┤
│ 规则层   watchdog.py / resolver.py           │
│ 规则版本、业务日、报表期、过渡条款           │
├─────────────────────────────────────────────┤
│ 计算层   operators.py / dag.py               │
│ 纯 Decimal 算子、依赖、血缘                  │
├─────────────────────────────────────────────┤
│ 账本层   store.py                            │
│ 追加式双时态事实、修正、哈希链               │
├─────────────────────────────────────────────┤
│ 证据层   wiki.py / compiler.py               │
│ 原文 → SourceSpan → FactCandidate            │
├─────────────────────────────────────────────┤
│ 契约层   models.py / adapter.py              │
│ 强类型事实、来源校验、全量通过才提交         │
└─────────────────────────────────────────────┘
```

### 各层职责

| 层 | 输入 | 输出 | 不做什么 |
|---|---|---|---|
| 证据层 | 文档、结构化条目 | 候选事实 + 原文片段 | 不入账、不计算 |
| 契约层 | 候选事实 | 校验后的 `FactRecord` | 不默认补参 |
| 账本层 | 事实记录 | 按时点可见的事实 | 不覆盖历史 |
| 计算层 | 事实 + 算子 | `DerivedRecord` | 不读 Wiki、不写事实 |
| 规则层 | 规则版本 + 业务日期 | `ApplicableVersion` | 不取“最新版”了事 |
| 分析层 | 披露 + 适用版本 | `CaseFinding` | 不直接判“违规” |

## 五、数据模型

### 5.1 SourceSpan：来源必须是可校验的

```text
SourceSpan
  doc_id / doc_version
  start / end / text
  sha256(text)
```

约束：

- `end - start == len(text)`；
- Wiki 索引中的 `doc[start:end]` 必须等于 `text`；
- hash 必须一致。

这样“引用”不是一段字符串，而是一个可以被程序重新验证的切片。

### 5.2 FactCandidate / FactRecord

```text
entity / key / value / unit
valid_from / valid_to
source
recorded_at          # 系统何时知道
supersedes           # 修正哪条旧事实
prev_hash / record_hash
```

关键区别：

- `FactCandidate` 是“候选”，可以来自编译器或 LLM；
- `FactRecord` 是“已入账”，不可变；
- 修正=新记录指向旧记录，旧记录不被删除；
- 查询按“业务日 + 记录时间”取可见版本。

### 5.3 DerivedRecord

```text
key / value / unit
operator / operator_version
input_fact_ids[]
formula
valid_at / computed_at
```

派生值不是“另一个事实”，它必须能回答：

- 用了哪些事实？
- 用了哪个算子版本？
- 公式是什么？

### 5.4 RuleVersion / ApplicableVersion

```text
RuleVersion
  rule_id / version
  valid_from / valid_to
  transition        # prospective / retrospective / modified
  early_adoption_allowed
  entity_scope
  citation

ApplicableVersion
  rule
  basis             # transaction / comparative_restated / modified / early_adoption
  reason
```

### 5.5 CompanyDisclosure / CaseFinding

这是研究层模型，不是核心账本模型：

- `CompanyDisclosure`：公司披露的采用版本 + 报告期 + 来源；
- `CaseFinding`：一致 / 疑似未及时 / 提前采用 / 证据不足。

分析层不直接改账本，也不输出“违规”结论。

## 六、运行流程

### 6.1 文档入账

```text
文档
  → 结构化条目（SpanSpec）
  → SourceSpan（校验区间/hash）
  → FactCandidate
  → WikiAwareAdapter（全部候选校验）
  → TemporalFactStore（追加）
```

设计要点：

- 适配器**先校验全部候选，再逐条提交**；缺一个则一条都不写；
- 来源对不上 → 拒绝，不做“修一修再用”；
- 同一 key 有效期重叠且没有 `supersedes` → 冲突拒绝。

### 6.2 计算

```text
FactRecord
  → DAG fact/operator 节点
  → Decimal 算子
  → DerivedRecord（记录输入与公式）
```

设计要点：

- 算子不读 Wiki、不写账本；
- DAG 做依赖解析、循环检测、结果缓存；
- 派生记录带输入 `fact_id`，审计可回放。

### 6.3 规则适用

```text
业务发生日 / 报表期
  + RuleVersion 表
  + 过渡条款 / 提前适用 / 主体范围
  → ApplicableVersion
```

设计要点：

- 交易时点与报表时点分开；
- 追溯 → 比较期按新版本；
- 未来适用 → 交易仍按旧版本；
- 无版本/多版本 → 拒绝。

### 6.4 案例评估

```text
披露版本
  + ApplicableVersion
  → CaseFinding
```

设计要点：

- 只输出“一致/疑似/提前/证据不足”；
- 不输出“违规”；
- 披露不足不参与统计，但保留证据。

## 七、关键设计决策

| 决策 | 选择 | 放弃的方案 | 原因 |
|---|---|---|---|
| 事实存储 | 追加式账本 | 可变 dict | 要支持修正/重述 |
| 时间模型 | 双时态 | 单一有效日期 | 要回答“当时知道什么” |
| 来源 | `SourceSpan` + hash | 引用字符串 | 要可审计 |
| LLM 角色 | 只产候选 | 直接入账 | 防幻觉 |
| 入账控制 | 全量通过才提交 | 逐条提交 | 防半本底稿 |
| 计算 | 纯 Decimal 算子 | LLM 算数 | 确定性 |
| 规则 | 版本解析器 | 取最新版 | 过渡条款/比较期 |
| 分析 | 初筛 + 人工 | 自动判违规 | 避免误伤 |
| 开源 | 核心 + 合成测试 | 全仓公开 | 数据/业务/版权风险 |

## 八、失败模式与拒绝策略

| 情况 | 系统行为 |
|---|---|
| 来源切片对不上 | `CitationError` / 拒绝 |
| 缺事实 | `MissingParameterError` |
| 同一 key 有效期重叠且无 `supersedes` | `FactConflictError` |
| 同一时点多条有效 | `FactConflictError` |
| 规则缺失 | `MissingParameterError` |
| 规则版本冲突 | `FactConflictError` |
| 年报多年份/无披露 | 不猜，转“披露不足/需人工” |
| 派生输入缺失 | 拒绝，不生成派生值 |

核心原则：

> **拒绝输出比输出一个可能错的数字更安全。**

## 九、测试设计

测试不是“覆盖率”，而是围绕不变量：

| 测试 | 验证的不变量 |
|---|---|
| 双时态修正 | 旧知识看旧值，新知识看新值 |
| 重叠冲突 | 无 `supersedes` 不允许覆盖 |
| 来源 hash | 切片/hash 不一致必须拒绝 |
| 缺参 | 缺一个事实不生成结果 |
| DAG 血缘 | 派生记录能回溯输入 fact_id |
| 规则版本 | 追溯/未来适用/提前适用 |
| 规则冲突 | 多版本同时生效必须拒绝 |
| 案例评估 | 未披露不判“未采用” |
| 年报措辞 | 多种“执行/实施/施行/首次执行”表述 |

当前开源核心：**26 passed**。

## 十、边界与扩展

### 10.1 当前开源核心不包含

- LLM/MCP/Preflight/WorkingPaper 生产适配器；
- 真实年报/题库/业务数据；
- 数据库/并发/权限；
- 生产部署配置。

### 10.2 扩展点

```text
LLM 编译器：实现 Extractor 接口，输出 LLMPayload → FactCandidate
MCP 查询：只返回规则版本 + 引用，不返回自由结论
数据库：实现 TemporalFactStore 的持久化接口
年报解析：文本 → CompanyDisclosure，不进入核心账本
```

原则：**扩展层可以接外部系统，但不能破坏核心不变量。**

## 十一、设计原则总结

1. **先列失败模式，再定不变量，最后才是模块。**
2. **LLM 只做感知，不做状态和计算。**
3. **事实是账本，不是缓存；只能追加，不能覆盖。**
4. **每个数字都要有来源、版本、时间和血缘。**
5. **缺参/冲突/来源不合法，一律拒绝。**
6. **分析层只做初筛，不替人下结论。**
7. **开源核心，闭源数据和生产适配器。**

一句话：

> **Fin-Wiki 的设计不是“让 LLM 更聪明”，而是“让确定性系统在 LLM 旁边安全工作”。**
