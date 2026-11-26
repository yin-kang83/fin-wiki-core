# Super-agent 架构（v0.2）

`fin_wiki.superagent` 是 Fin-Wiki Core 的四模块参考骨架：

```text
StateStore    SQLite 底稿池，只追加事实/快照，带 hash chain 与禁改触发器
Worker        LLMParserWorker / MathOperatorWorker，无状态、返回 dict
Watchdog      写库前强校验；失败熔断
Router        DAG 调度、Worker 替换、积压恢复
```

## 关键不变量

```text
业务事实只追加，不 UPDATE/DELETE
每条事实有 prev_hash / fact_hash
快照保存完整状态，重启后可 load_state
Watchdog 在 StateStore 提交之前运行
Worker 不能直接写状态
Router 不计算金额
```

## 用法

```python
from fin_wiki.superagent import (
    LLMParserWorker, MathOperatorWorker, Router, StateStore, mock_llm,
)

store = StateStore("data/superagent.db")
router = Router(
    store,
    parser_factory=lambda: LLMParserWorker(mock_llm),
    math_factory=lambda: MathOperatorWorker(),
)
router.submit("2026年A公司...")
print(router.run_pending())
print(store.load_state())
```

## 长投实验

```text
成本法转权益法
 原账面 900 + 新增 3000 = 3900
 应享净资产份额 4500
 营业外收入 600
 调整后成本 4500

后续
 净利润 2000 × 30% = 600
 OCI 500 × 30% = 150
 现金股利 300 × 30% = 90

账面价值 4500 + 600 + 150 - 90 = 5160
```

减值转回请求会由 Watchdog 拦截并返回 `BLOCKED`，不写入事实/快照。

## LLM Adapter

`fin_wiki.adapters` 提供：

```text
LLMAdapter         callable + 超时 + 重试 + JSON 提取
CallableAdapter    包装普通 callable
OpenAICompatibleAdapter   OpenAI-compatible Chat Completions
```

密钥只从环境变量读取：

```text
FINWIKI_LLM_BASE_URL
FINWIKI_LLM_API_KEY
FINWIKI_LLM_MODEL
```

## 边界

```text
这是参考骨架，不是生产调度系统
SQLite 单机，不是分布式
不包含客户数据
不构成审计/税务/法律意见
```
