# Fin-Wiki 架构说明（开源草稿）

> 目标：把“知识/证据”与“确定性财务计算”分开。LLM 只读、只抽参，不写账、不算数。
> 本文件是开源仓库的主架构说明，后续可拆成 README + docs/architecture.md。

## 1. 一句话

```text
文档 → 证据片段 → 候选事实 → 双时态账本 → 前置断言 → 纯算子 DAG → 派生血缘
                         ↘ 版本化规则 → 适用性解析 → 案例评估
```

## 2. 分层

| 层 | 模块 | 职责 | 不做什么 |
|---|---|---|---|
| 证据层 | `wiki.py` / `compiler.py` | 文档 → `SourceSpan` → `FactCandidate` | 不直接入账、不计算 |
| 账本层 | `store.py` | 追加式双时态事实、修正、哈希链 | 不覆盖历史、不默认补参 |
| 契约层 | `models.py` | 强类型事实、来源校验 | 不把 LLM 输出当事实 |
| 计算层 | `operators.py` / `dag.py` | 纯 Decimal 算子、DAG、派生血缘 | 不读 Wiki、不写事实 |
| 规则层 | `watchdog.py` / `resolver.py` | 规则版本、按业务时点/过渡条款选版本 | 不取“最新版”了事 |
| 分析层 | `case_study.py` | 披露版本 vs 适用版本比对 | 不直接下“违规”结论 |

## 3. 核心不变量

1. **LLM 不写账**：只输出 `FactCandidate` 或 `LLMPayload`，入账前必须校验。
2. **事实不可变**：账本只追加，修正走 `supersedes`。
3. **双时态**：`valid_from/valid_to`（业务时间）+ `recorded_at`（录入时间）。
4. **来源可校验**：`SourceSpan` 必须能回指原文切片，hash 一致。
5. **缺参/冲突即拒绝**：不默认、不猜测、不取最新版。
6. **派生有血缘**：`DerivedRecord` 记录输入 `fact_id`、算子、版本、公式。
7. **规则有版本**：按业务日/报表期/过渡条款/提前适用/主体范围解析。

## 4. 数据流

```text
合同/法规/年报
  → DocumentCompiler（确定性）
  → SourceSpan（doc_id, version, start, end, text, sha256）
  → FactCandidate（entity, key, value, unit, valid_from/to, source）
  → WikiAwareAdapter（全部候选校验通过才提交）
  → TemporalFactStore（append-only；同一 key 有效期重叠必须 supersedes）
  → ExecutionEngine（fact/operator 节点、Decimal 算子）
  → DerivedRecord（输入 fact_id、operator、formula）
```

规则与案例：

```text
RuleVersion（生效日/废止日/transition/early_adoption/entity_scope）
  → ApplicabilityResolver（业务日 + 报表期 + 过渡条款 + 提前适用 + 主体范围）
  → CaseEvaluator（披露版本 vs 适用版本）
  → 一致 / 疑似未及时 / 提前采用需核 / 证据不足
```

## 5. 关键实现

### 5.1 双时态账本

- 每条事实是 `FactRecord`，字段含 `valid_from/valid_to/recorded_at/supersedes/prev_hash/record_hash`；
- 查询 `get(entity, key, as_of=业务日, knowledge_at=录入时点)`：
  - 先按业务有效期筛；
  - 再按录入时点筛“当时是否已知”；
  - 被 `supersedes` 的旧记录在修正后不可见；
  - 同一时点多条有效 → `FactConflictError`。

### 5.2 证据校验

- `SourceSpan` 要求 `end-start == len(text)`；
- `CompiledWiki.add_candidate` 检查 `doc[ start:end ] == span.text`，以及 sha256；
- 确定性编译器校验来源切片；LLM 适配器不在本开源仓内，见开源边界。

### 5.3 计算与 DAG

- 算子只接收 `Decimal` 参数，返回 `Decimal`；
- DAG 节点分 `fact` / `operator`，执行时递归解析依赖；
- 循环检测、结果缓存、派生记录血缘；
- 输出量化到分，避免二进制浮点。

### 5.4 规则适用性

`ApplicabilityResolver` 的判定顺序：

1. 业务发生日 → 交易适用版本；
2. 报表期/比较期 → 报表适用版本；
3. 过渡条款：追溯/修改 → 比较期新版本；未来适用 → 旧版本；
4. 提前适用开关；
5. 主体范围；
6. 无版本/多版本 → 拒绝。

### 5.5 案例评估

`CaseEvaluator` 只做初筛：

- 一致；
- 疑似未及时采用；
- 提前采用/需核；
- 证据不足。

**不输出“违规”结论**；必须人工复核原文。

## 6. 模块地图

```text
fin_wiki/
├─ models.py          # SourceSpan / FactCandidate / FactRecord / DerivedRecord
├─ store.py           # 双时态账本、哈希链、派生记录
├─ wiki.py            # 证据索引
├─ compiler.py        # 确定性编译
├─ adapter.py         # Wiki → 账本适配器
├─ operators.py       # 纯 Decimal 算子
├─ dag.py             # DAG 执行器
├─ watchdog.py        # RuleBook / RuleVersion
├─ resolver.py        # ApplicabilityResolver
├─ case_study.py      # CaseEvaluator
└─ annual_report.py   # 年报披露 → 采用版本 → CaseEvaluator
```

## 7. 测试

- `fin_wiki/tests`：26 passed；
- 覆盖：双时态修正、来源 hash、缺参、重叠冲突、DAG 血缘、规则版本/冲突、案例分类。

## 8. 开源边界（待讨论）

建议先开源：

- 账本、Resolver、CaseEvaluator、compiler 接口、测试；
- 合成示例数据。

暂不开源：

- 生产实现/内部题库/经验库；
- 真实年报 PDF/客户数据；
- 题库原题/真题答案；
- 内部部署配置。

## 9. 后续

1. 补 `ARCHITECTURE.md` 图示与端到端示例；
2. 补 `OPEN_SOURCE_SCOPE.md`（开源程度、许可证、发布流程）；
3. 清历史、扫密钥/版权，另建 public repo；
4. 首个 tag `v0.1.0`。
