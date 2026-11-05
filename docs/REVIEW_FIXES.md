# Codex 审查报告修复记录（v0.1.3）

> 审查来源：外部 Codex 逻辑审查报告（提交 `5ab9907`）。
> 处理原则：先修 P1 的账本/证据问题，再修 P2 的规则与命名空间问题；每条都转为回归测试。

## 修复对照

| # | 问题 | 修复 | 回归测试 |
|---:|---|---|---|
| 1 | 调用方可原地修改已入账事实 | `SourceSpan/FactCandidate/FactRecord/DerivedRecord` 冻结；嵌套来源冻结 | `test_public_record_cannot_be_mutated` |
| 2 | 同一事实不能连续修正两次 | 冲突检测跳过已替代祖先；F1←F2←F3 可连续修正 | `test_second_correction_is_accepted` |
| 3 | 批量入账失败留半批数据 | 新增 `commit_many`，异常整批回滚；适配器使用批量提交 | `test_batch_failure_leaves_store_unchanged` |
| 4 | 年报抽取把错误证据变成结论 | 去掉无准则名的“首次执行”；否定披露优先；多年份不猜，直接拒绝 | `test_other_standard_is_not_lease_adoption`、`test_subsidiary_year_is_not_guessed` |
| 5 | 常量静默覆盖事实输入且血缘错位 | 拒绝 `inputs` 与 `params` 同名；派生记录保存 params/input_mapping | `test_constant_cannot_shadow_fact_input` |
| 6 | 提前适用绕过主体范围 | 提前适用复用 entity_scope；多候选冲突拒绝 | `test_early_adoption_respects_entity_scope` |
| 7 | 不同准则同名版本互相覆盖 | 版本索引改为 `(standard_id, version)`；重复不一致报冲突 | `test_case_version_lookup_is_namespaced_by_standard` |
| 8 | 同版本原文被覆盖后旧候选仍可入账 | 文档版本内容不可变；入账边界再次校验来源 | `test_document_replacement_is_rejected` |

## 测试

```text
fin_wiki/tests: 36 passed
```

## 说明

- 修复没有改变核心 API 的方向；
- 新增的批量提交是账本层能力，未来接数据库时可替换为事务；
- 年报抽取仍只做“披露文本初筛”，不替代人工/审计判断；
- 审查报告中的真实公司会计处理、数据库/并发/权限不在本次范围。
