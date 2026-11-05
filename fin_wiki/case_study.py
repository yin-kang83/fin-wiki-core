# -*- coding: utf-8 -*-
"""上市公司准则采用案例评估器（研究用，不直接下“违规”结论）。

用途：
  输入公司年报披露的“采用版本 + 报告期”，与版本化准则解析结果比对，
  输出：一致 / 疑似未及时采用 / 提前采用 / 证据不足 / 需人工判断。

边界：
  · 只根据“披露文本 + 版本表”做初筛；
  · 不替代审计/法律判断；
  · 披露不清、过渡条款复杂、主体范围不明时，必须转人工。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import FactConflictError, MissingParameterError
from .resolver import ApplicabilityResolver
from .watchdog import RuleVersion


@dataclass(frozen=True)
class CompanyDisclosure:
    ticker: str
    company: str
    standard_id: str
    version_disclosed: str
    period_start: date
    period_end: date
    source: str
    early_adoption: bool = False


@dataclass(frozen=True)
class CaseFinding:
    ticker: str
    standard_id: str
    status: str
    disclosed: str
    applicable: str
    reason: str


class CaseEvaluator:
    def __init__(self, rules: list[RuleVersion]) -> None:
        self.rules = rules
        self.resolver = ApplicabilityResolver(rules)
        self._by_version = {r.version: r for r in rules}

    def evaluate(self, case: CompanyDisclosure) -> CaseFinding:
        try:
            applicable = self.resolver.resolve(
                case.standard_id,
                event_date=case.period_start,
                reporting_period_end=case.period_end,
                early_adoption=case.early_adoption,
            )
        except (MissingParameterError, FactConflictError) as exc:
            return CaseFinding(case.ticker, case.standard_id, "证据不足/版本冲突",
                               case.version_disclosed, "", str(exc))
        disclosed_rule = self._by_version.get(case.version_disclosed)
        if disclosed_rule is None:
            return CaseFinding(case.ticker, case.standard_id, "证据不足",
                               case.version_disclosed, applicable.rule.version,
                               "披露版本不在版本表中")
        if disclosed_rule.version == applicable.rule.version:
            return CaseFinding(case.ticker, case.standard_id, "一致",
                               case.version_disclosed, applicable.rule.version,
                               f"披露与解析一致（{applicable.basis}）")
        if disclosed_rule.valid_from > applicable.rule.valid_from:
            return CaseFinding(case.ticker, case.standard_id, "提前采用/需核",
                               case.version_disclosed, applicable.rule.version,
                               "披露版本晚于解析适用版本，可能是提前采用或版本表不全")
        if case.period_end >= applicable.rule.valid_from:
            return CaseFinding(case.ticker, case.standard_id, "疑似未及时采用",
                               case.version_disclosed, applicable.rule.version,
                               "报告期已进入新准则适用期，披露仍是旧版本")
        return CaseFinding(case.ticker, case.standard_id, "一致",
                           case.version_disclosed, applicable.rule.version,
                           "报告期尚未进入新准则适用期")
